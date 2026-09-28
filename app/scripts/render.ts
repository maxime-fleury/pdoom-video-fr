#!/usr/bin/env -S node --experimental-strip-types
// Offline renderer. Drives the app in headless Chrome (?export=1) and either
//   stills:  bun scripts/render.ts stills --t 1.5,23,40.2 [--only id1,id2] [--out dir]
//   sheet:   bun scripts/render.ts sheet --from 20 --to 35 [--n 12] [--cols 4] [--only ids] [--out file.png]   (or --times a,b,c | --cuts)
//   plates:  bun scripts/render.ts plates   (renders one representative JPEG per plate into public/plates/ (used by the outro's rewind), times from plates.json or entry midpoints)
//   perf:    bun scripts/render.ts perf --from 20 --to 25 [--only ids] [--samples 1] [--shutter 0.5]   (avg ms per frame incl. GPU sync and the export's pixel readback)
//   video:   bun scripts/render.ts video [--from 0] [--to 156.65] [--fps 60] [--crf 16] [--x264 aq-mode=3] [--samples 1] [--shutter 0.5] [--out ../out/pdoom.mp4] [--noaudio]
//            --samples N averages N sub-frames per frame over shutter×(1/fps): motion blur + temporal AA;
//            --samples auto picks the count per frame (4, 12, 36, 108 or 324, see Engine.render)
//   --scale N (all modes): render at N× the 1920x1080 layout (--scale 2 = true 3840x2160,
//            --scale 1.3333 = true 2560x1440); stills are then saved full-res from the pixel
//            buffer, videos are encoded at the physical size.
// Uses the Vite dev server at --url (default http://localhost:5173); starts a private one if unreachable.
//
// Run it with node. playwright-core cannot drive Chrome from Bun (its CDP transport never
// completes the handshake), and this script therefore uses only node: built-ins — spawn,
// fs, http — plus its own minimal WebSocket server, so `bun scripts/render.ts` still works
// for everything except the browser.
import { chromium, type Browser, type Page } from 'playwright-core';
import { spawn } from 'node:child_process';
import { mkdirSync, existsSync, writeFileSync, readFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import type { Socket } from 'node:net';
import path from 'node:path';

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const HERE = import.meta.dirname ?? path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'));

const argv = process.argv.slice(2);
const mode = argv[0] ?? 'stills';
const opt = (k: string, d?: string) => { const i = argv.indexOf(`--${k}`); return i >= 0 ? argv[i + 1] : d; };
const flag = (k: string) => argv.includes(`--${k}`);
const APP = path.resolve(HERE, '..');
// --scale may be fractional: 1.3333 gives a native 2560x1440 (2K) render out of the same
// 1920x1080 layout. The physical size is rounded to whole pixels.
const SCALE = Math.max(1, Math.min(4, +opt('scale', '1')!));
const OW = Math.round(1920 * SCALE), OH = Math.round(1080 * SCALE); // output size
// --samples N (fixed) or --samples auto [--min-samples 4] [--max-samples 324] [--tol 3] (adaptive, see Engine.render)
const SAMPLES = opt('samples', '1') === 'auto'
  ? { min: +opt('min-samples', '4')!, max: +opt('max-samples', '324')!, tol: +opt('tol', '3')! }
  : +opt('samples', '1')!;
const hist = (h: Record<string, number>) => Object.entries(h).sort((a, b) => +a[0] - +b[0]).map(([k, v]) => `${k}:${v}`).join(' ');
const ROOT = path.resolve(APP, '..');
// vite is started through the same package manager that launched us (bunx under bun, npx under node)
const VITE = process.versions.bun ? 'bunx vite' : 'npx --no-install vite';

async function reachable(url: string) {
  try { const r = await fetch(url, { signal: AbortSignal.timeout(1500) }); return r.ok; } catch { return false; }
}

/**
 * Minimal WebSocket server: the page pushes one raw RGBA frame per message and we answer one
 * text message per frame as an ack. Hand-rolling it keeps the script on node: built-ins only
 * (it has to run under node, see the note at the top) with no dependency on `ws`.
 */
function makeWsServer(onMessage: (msg: Buffer) => void) {
  const sockets = new Set<Socket>();
  const http = createServer((_req, res) => { res.writeHead(400); res.end('websocket only'); });
  http.on('upgrade', (req, socket: Socket) => {
    const key = req.headers['sec-websocket-key'];
    if (!key) { socket.destroy(); return; }
    const accept = createHash('sha1').update(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
    socket.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
      + `Sec-WebSocket-Accept: ${accept}\r\n\r\n`);
    socket.setNoDelay(true);
    sockets.add(socket);
    socket.on('error', () => sockets.delete(socket));
    socket.on('close', () => sockets.delete(socket));

    // frame assembler: chunks stay in a queue and are only copied when a whole frame is here
    const chunks: Buffer[] = [];
    let size = 0;
    let frags: Buffer[] = [];
    const peek = (n: number): Buffer | null => {
      if (size < n) return null;
      const out = Buffer.allocUnsafe(n);
      let off = 0;
      for (const c of chunks) { if (off >= n) break; const t = Math.min(c.length, n - off); c.copy(out, off, 0, t); off += t; }
      return out;
    };
    const take = (n: number): Buffer | null => {
      if (size < n) return null;
      const out = Buffer.allocUnsafe(n);
      let off = 0;
      while (off < n) {
        const c = chunks[0]!;
        const t = Math.min(c.length, n - off);
        c.copy(out, off, 0, t);
        if (t === c.length) chunks.shift(); else chunks[0] = c.subarray(t);
        off += t;
      }
      size -= n;
      return out;
    };
    const send = (op: number, payload: Buffer) => {
      const n = payload.length;
      const head = n < 126 ? Buffer.from([0x80 | op, n])
        : n < 65536 ? Buffer.from([0x80 | op, 126, n >> 8, n & 0xff])
        : (() => { const b = Buffer.alloc(10); b[0] = 0x80 | op; b[1] = 127; b.writeBigUInt64BE(BigInt(n), 2); return b; })();
      socket.write(Buffer.concat([head, payload]));
    };
    socket.on('data', (chunk: Buffer) => {
      chunks.push(chunk); size += chunk.length;
      for (;;) {
        const h = peek(2);
        if (!h) return;
        const fin = (h[0]! & 0x80) !== 0, op = h[0]! & 0x0f, masked = (h[1]! & 0x80) !== 0;
        let len = h[1]! & 0x7f, hdr = 2;
        if (len === 126) { const e = peek(4); if (!e) return; len = e.readUInt16BE(2); hdr = 4; }
        else if (len === 127) { const e = peek(10); if (!e) return; len = Number(e.readBigUInt64BE(2)); hdr = 10; }
        if (size < hdr + (masked ? 4 : 0) + len) return;
        take(hdr);
        const mask = masked ? take(4) : null;
        const pay = take(len)!;
        if (mask) for (let i = 0; i < pay.length; i++) pay[i]! ^= mask[i & 3]!;
        if (op === 8) { socket.end(); return; }
        if (op === 9) { send(0xa, pay); continue; }
        if (op === 0 || op === 1 || op === 2) {
          frags.push(pay);
          if (fin) { const msg = frags.length === 1 ? frags[0]! : Buffer.concat(frags); frags = []; onMessage(msg); }
        }
      }
    });
  });
  const iface = {
    port: 0,
    listen: () => new Promise<void>((r) => http.listen(0, '127.0.0.1', () => {
      iface.port = (http.address() as { port: number }).port;
      r();
    })),
    send: (text: string) => { for (const s of sockets) s.write(textFrame(text)); },
    close: () => { for (const s of sockets) s.destroy(); http.close(); },
  };
  return iface;
}

function textFrame(text: string) {
  const payload = Buffer.from(text, 'utf8');
  return payload.length < 126
    ? Buffer.concat([Buffer.from([0x81, payload.length]), payload])
    : Buffer.concat([Buffer.from([0x81, 126, payload.length >> 8, payload.length & 0xff]), payload]);
}

async function ensureServer(): Promise<{ url: string; stop: () => void }> {
  const url = opt('url', 'http://localhost:5173')!;
  if (await reachable(url)) return { url, stop: () => {} };
  const port = 5300 + Math.floor(Math.random() * 500);
  // no live reload: a file saved mid-render must not reload the page
  const proc = spawn(VITE, ['--port', String(port), '--strictPort'], { cwd: APP, stdio: 'ignore', shell: true, env: { ...process.env, PDOOM_NO_HMR: '1' } });
  const u = `http://localhost:${port}`;
  // a cold `npx vite` on Windows can take a while before it answers: wait up to a minute
  for (let i = 0; i < 300 && !(await reachable(u)); i++) await sleep(200);
  return { url: u, stop: () => proc.kill() };
}

// `--use-angle=metal` is macOS-only: pick the native backend per platform.
const ANGLE = process.platform === 'darwin' ? '--use-angle=metal'
  : process.platform === 'win32' ? '--use-angle=d3d11' : '--use-angle=vulkan';
const GPU_ARGS = [ANGLE, '--enable-gpu-rasterization', '--ignore-gpu-blocklist',
  '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows'];
const CHROME_EXE = process.env.PDOOM_CHROME ?? path.join(
  process.env.PROGRAMFILES ?? 'C:\\Program Files', 'Google/Chrome/Application/chrome.exe');

/**
 * playwright drives Chrome itself (channel: 'chrome'). Where that CDP handshake never
 * completes — playwright-core older than the installed Chrome, typically on Windows — it
 * would just hang for the whole launch timeout, so we start Chrome on a debugging port and
 * attach to it instead. Same browser, same page API.
 */
async function launchBrowser(): Promise<{ browser: Browser; cdp: boolean; stop: () => void }> {
  if (!flag('cdp')) {
    try {
      const browser = await chromium.launch({ channel: 'chrome', headless: !flag('headed'), args: GPU_ARGS, timeout: 30000 });
      return { browser, cdp: false, stop: () => {} };
    } catch (e) {
      console.error(`playwright could not drive Chrome (${String(e).split('\n')[0]}); starting it on a debugging port`);
    }
  }
  const port = 9400 + Math.floor(Math.random() * 400);
  const proc = spawn(CHROME_EXE, [flag('headed') ? '--new-window' : '--headless=new',
    `--remote-debugging-port=${port}`, `--user-data-dir=${path.join(tmpdir(), `pdoom-chrome-${port}`)}`,
    '--no-first-run', '--no-default-browser-check', '--no-sandbox', '--hide-scrollbars', '--mute-audio',
    // Chrome 111+ rejects a CDP WebSocket from an origin it doesn't know about
    '--remote-allow-origins=*',
    '--window-size=1920,1080', ...GPU_ARGS], { stdio: 'ignore' });
  const url2 = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 200; i++) {
    if (!(await reachable(`${url2}/json/version`))) await sleep(150);
    else break;
  }
  const browser = await chromium.connectOverCDP(url2);
  return { browser, cdp: true, stop: () => proc.kill() };
}

async function openPage(url: string) {
  const { browser, cdp, stop } = await launchBrowser();
  let page: Page;
  if (cdp) {
    // connectOverCDP attaches to Chrome's own default context: no new context to make.
    const ctx = browser.contexts()[0] ?? (await browser.newContext());
    page = await ctx.newPage();
    await page.setViewportSize({ width: 1920, height: 1080 }).catch(() => {});
    page.on('close', stop);
  } else {
    page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  }
  const logs: string[] = [];
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') logs.push(`[${m.type()}] ${m.text()}`); });
  page.on('pageerror', (e) => logs.push(`[pageerror] ${e.message}`));
  const only = opt('only');
  await page.goto(`${url}/?export=1${only ? `&only=${only}` : ''}${SCALE !== 1 ? `&scale=${SCALE}` : ''}`);
  await page.waitForFunction(() => (window as any).__pdoom?.ready || (window as any).__pdoom?.error, null, { timeout: 120000 });
  const err = await page.evaluate(() => (window as any).__pdoom.error);
  if (err) throw new Error(`app failed to boot:\n${err}\n${logs.join('\n')}`);
  const size: [number, number] = await page.evaluate(() => [(window as any).__pdoom.width ?? 1920, (window as any).__pdoom.height ?? 1080]);
  if (size[0] !== OW || size[1] !== OH) throw new Error(`app renders ${size[0]}x${size[1]}, expected ${OW}x${OH} (--scale ${SCALE})`);
  const sceneErrors: string[] = await page.evaluate(() => (window as any).__pdoom.errors);
  if (sceneErrors.length) console.error('SCENE ERRORS:\n' + sceneErrors.join('\n'));
  return { browser, page, logs };
}

async function stills(page: Page, times: number[], outDir: string) {
  mkdirSync(outDir, { recursive: true });
  const files: string[] = [];
  for (const t of times) {
    const k: number = await page.evaluate(([t, s, sh]) => (window as any).__pdoom.still(t, s, sh), [t, SAMPLES, +opt('shutter', '0.5')!] as const);
    const f = path.join(outDir, `f_${t.toFixed(2).padStart(7, '0')}.png`);
    if (typeof SAMPLES !== 'number') console.log(`t=${t}: ${k} sub-frames`);
    // at scale > 1 the canvas is shown downscaled on the page: save the full-res pixel buffer instead
    if (SCALE !== 1) writeFileSync(f, Buffer.from(await page.evaluate(() => (window as any).__pdoom.png()), 'base64'));
    else await page.screenshot({ path: f, clip: { x: 0, y: 0, width: 1920, height: 1080 } });
    files.push(f);
  }
  return files;
}

async function sheet(page: Page, times: number[], cols: number, out: string) {
  const dataUrl: string = await page.evaluate(async ({ times, cols }) => {
    const P = (window as any).__pdoom;
    const cw = 480, ch = 270, pad = 4, lab = 18;
    const rows = Math.ceil(times.length / cols);
    const cv = document.createElement('canvas');
    cv.width = cols * (cw + pad) + pad; cv.height = rows * (ch + lab + pad) + pad;
    const c = cv.getContext('2d')!;
    c.fillStyle = '#222'; c.fillRect(0, 0, cv.width, cv.height);
    const src = document.getElementById('c') as HTMLCanvasElement;
    times.forEach((t: number, i: number) => {
      P.still(t);
      const x = pad + (i % cols) * (cw + pad), y = pad + Math.floor(i / cols) * (ch + lab + pad);
      c.drawImage(src, x, y + lab, cw, ch);
      c.fillStyle = '#ddd'; c.font = '13px monospace'; c.fillText(`${t.toFixed(2)}s`, x + 2, y + 13);
    });
    return cv.toDataURL('image/png');
  }, { times, cols });
  mkdirSync(path.dirname(out), { recursive: true });
  writeFileSync(out, Buffer.from(dataUrl.split(',')[1]!, 'base64'));
}

async function video(page: Page, from: number, to: number, fps: number, out: string) {
  mkdirSync(path.dirname(out), { recursive: true });
  const crf = opt('crf', '16')!;
  const audio = path.join(ROOT, 'audio/pdoom.mp3');
  const args = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', `${OW}x${OH}`, '-r', String(fps), '-i', 'pipe:0'];
  if (!flag('noaudio')) args.push('-ss', String(from), '-t', String(to - from), '-i', audio);
  // Frames are sRGB (toSRGB in the final pass): convert with the BT.709 matrix and tag the stream,
  // otherwise ffmpeg converts with BT.601 while players and YouTube decode untagged HD as BT.709.
  // scale tags the matrix and range; primaries and transfer need setparams (the -color_* output flags don't reach the stream).
  args.push('-vf', 'vflip,scale=out_color_matrix=bt709,setparams=color_primaries=bt709:color_trc=bt709', '-c:v', 'libx264', '-preset', opt('preset', 'slow')!, '-crf', crf, '-pix_fmt', 'yuv420p', '-tune', 'grain', '-x264-params', opt('x264', 'aq-mode=3')!);
  if (!flag('noaudio')) args.push('-c:a', 'aac', '-b:a', '320k', '-shortest');
  args.push('-movflags', '+faststart', out);
  const ff = spawn(args[0]!, args.slice(1), { stdio: ['pipe', 'inherit', 'inherit'] });
  let frames = 0;
  const total = Math.round(to * fps) - Math.round(from * fps);
  const t0 = performance.now();
  const server = makeWsServer((msg) => {
    ff.stdin!.write(msg);
    frames++;
    server.send(String(frames)); // ack: the page keeps at most a few frames ahead of ffmpeg (bounded memory at 4K)
    if (frames % 60 === 0 || frames === total) {
      const el = (performance.now() - t0) / 1000;
      process.stdout.write(`\r${frames}/${total} frames  ${(frames / el).toFixed(1)} fps  eta ${((total - frames) / (frames / el)).toFixed(0)}s   `);
    }
  });
  await server.listen();
  const used: Record<string, number> = await page.evaluate((o) => (window as any).__pdoom.stream(o), { from, to, fps, ws: `ws://127.0.0.1:${server.port}`, samples: SAMPLES, shutter: +opt('shutter', '0.5')!, inflight: 4 });
  // wait for all frames to arrive
  while (frames < total) await sleep(20);
  ff.stdin!.end();
  await new Promise<void>((r) => ff.on('exit', () => r()));
  server.close();
  console.log(`\nwrote ${out} (${frames} frames in ${((performance.now() - t0) / 1000).toFixed(1)}s)`);
  console.log(`sub-frames per frame (count:frames): ${hist(used)}`);
}

const { url, stop } = await ensureServer();
const { browser, page, logs } = await openPage(url);
try {
  if (mode === 'gpu') {
    console.log(await page.evaluate(() => {
      const gl = document.createElement('canvas').getContext('webgl2')!;
      const ext = gl.getExtension('WEBGL_debug_renderer_info');
      return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    }));
  } else if (mode === 'stills') {
    const times = (opt('t') ?? '0').split(',').map(Number);
    const files = await stills(page, times, opt('out', path.join(ROOT, 'out/stills'))!);
    console.log(files.join('\n'));
  } else if (mode === 'sheet') {
    const from = +opt('from', '0')!, to = +opt('to', '10')!, n = +opt('n', '12')!;
    let times = Array.from({ length: n }, (_, i) => from + ((to - from) * i) / Math.max(1, n - 1));
    if (opt('times')) times = opt('times')!.split(',').map(Number);
    if (flag('cuts')) {
      // 4 frames around every timeline boundary: 2 frames before, 2 after
      const tl: { id: string; start: number }[] = await page.evaluate(() => (window as any).__pdoom.timeline);
      times = tl.slice(1).flatMap((e) => [e.start - 0.1, e.start - 1 / 60, e.start + 1 / 60, e.start + 0.1]);
    }
    const out = opt('out', path.join(ROOT, `out/sheets/sheet_${from}-${to}.png`))!;
    await sheet(page, times, +opt('cols', '4')!, out);
    console.log(out);
  } else if (mode === 'plates') {
    const tl: { id: string; start: number; end: number }[] = await page.evaluate(() => (window as any).__pdoom.timeline);
    const figs = ['open', 'loss', 'room', 'shoggoth', 'spacetime', 'ascent', 'bureau', 'leftturn', 'paperclips', 'fuse', 'stack', 'dense', 'loom', 'ilya'];
    const overrides: Record<string, number> = existsSync(path.join(APP, 'plates.json'))
      ? JSON.parse(readFileSync(path.join(APP, 'plates.json'), 'utf8')) : {};
    const dir = path.join(APP, 'public/plates');
    mkdirSync(dir, { recursive: true });
    await page.evaluate(() => { (window as any).__pdoom.engine.hudOff = true; });
    for (let i = 0; i < figs.length; i++) {
      const e = tl.find((x) => x.id === figs[i]);
      if (!e) continue;
      const t = overrides[figs[i]!] ?? (e.start + e.end) / 2;
      await page.evaluate((t) => (window as any).__pdoom.still(t, 4, 0.2), t);
      const f = path.join(dir, `fig${String(i + 1).padStart(2, '0')}.jpg`);
      await page.screenshot({ path: f, type: 'jpeg', quality: 90, clip: { x: 0, y: 0, width: 1920, height: 1080 } });
      console.log(f, t.toFixed(2));
    }
  } else if (mode === 'perf') {
    const from = +opt('from', '0')!, to = +opt('to', '5')!;
    const r = await page.evaluate(async ({ from, to, samples, shutter }) => {
      const P = (window as any).__pdoom;
      const ms: number[] = [];
      const buf = new Uint8Array(P.width * P.height * 4);
      P.still(from);
      const used: Record<number, number> = {};
      for (let t = from; t < to; t += 1 / 60) {
        const a = performance.now();
        const k = P.engine.render(t, 1 / 60, false, samples, shutter);
        used[k] = (used[k] ?? 0) + 1;
        await P.engine.readPixelsAsync(buf);
        ms.push(performance.now() - a);
      }
      ms.sort((a, b) => a - b);
      return { n: ms.length, avg: ms.reduce((a, b) => a + b, 0) / ms.length, p50: ms[ms.length >> 1], p95: ms[Math.floor(ms.length * 0.95)], max: ms[ms.length - 1], used };
    }, { from, to, samples: SAMPLES, shutter: +opt('shutter', '0.5')! });
    console.log(`frames ${r.n}  avg ${r.avg.toFixed(1)}ms  p50 ${r.p50.toFixed(1)}  p95 ${r.p95.toFixed(1)}  max ${r.max.toFixed(1)}  sub-frames ${hist(r.used)}`);
  } else if (mode === 'video') {
    const dur: number = await page.evaluate(() => (window as any).__pdoom.duration);
    await video(page, +opt('from', '0')!, +opt('to', String(dur))!, +opt('fps', '60')!, path.resolve(opt('out', path.join(ROOT, 'out/pdoom.mp4'))!));
  }
  if (logs.length) console.error('BROWSER LOG:\n' + logs.slice(0, 40).join('\n'));
} finally {
  await browser.close();
  stop();
}
