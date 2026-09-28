#!/usr/bin/env bash
# Renders the song in N parallel chunks (one headless Chrome + one ffmpeg each) and
# concatenates the result.
#
# Why: the offline render is CPU-bound on the per-sub-frame scene work — an image at 1080p
# costs about as much as the same image at 4K (roughly 35-80 ms per sub-frame, see `perf`),
# so a single `render.ts video` leaves every other core idle. Independent time ranges scale
# nearly linearly: 16 chunks on an 8-core/16-thread desktop run at ~1/6 the wall clock.
#
#   bash scripts/render-chunks.sh [--chunks 16] [--fps 60] [--dur 199.9333]
#                                [--url http://localhost:5173] [--out ../out/pdoom.mp4]
#                                [-- <flags for render.ts>]
#
# Flags after `--` go to render.ts (`--samples`, `--shutter`, `--crf`, `--preset`, `--scale`).
# Chunks are rendered with --noaudio (AAC priming at every seam clicks) and the audio is
# muxed once, at the end, from audio/pdoom.mp3 (`--audio` to point elsewhere).
#
# Run it with bash; render.ts itself must run under node (see its header).
set -euo pipefail

CHUNKS=16
FPS=60
DUR=199.9333
URL=http://localhost:5173
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="$ROOT/out/pdoom.mp4"
AUDIO="$ROOT/audio/pdoom.mp3"
EXTRA=()

while [ $# -gt 0 ]; do
  case "$1" in
    --chunks) CHUNKS=$2; shift 2 ;;
    --fps) FPS=$2; shift 2 ;;
    --dur) DUR=$2; shift 2 ;;
    --url) URL=$2; shift 2 ;;
    --out) OUT=$2; shift 2 ;;
    --audio) AUDIO=$2; shift 2 ;;
    --) shift; EXTRA=("$@"); break ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

[ "$CHUNKS" -ge 1 ] || { echo "--chunks must be >= 1" >&2; exit 2; }
command -v node >/dev/null || { echo "node is required (playwright-core cannot drive Chrome from bun)" >&2; exit 1; }

# absolute: the concat step runs from the chunk directory
mkdir -p "$(dirname "$OUT")" "$(dirname "$AUDIO")"
OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
AUDIO="$(cd "$(dirname "$AUDIO")" && pwd)/$(basename "$AUDIO")"

FRAMES=$(awk "BEGIN{printf \"%d\", $DUR * $FPS + 0.5}")   # the whole render, in frames
DIR="$ROOT/out/chunks"
rm -rf "$DIR"; mkdir -p "$DIR"
echo "rendering $FRAMES frames at ${FPS}fps in $CHUNKS chunks -> $DIR"

PIDS=()
for i in $(seq 0 $((CHUNKS - 1))); do
  # split the frame range as evenly as possible, boundaries on whole frames
  read -r f0 f1 <<EOF
$(awk "BEGIN{
  base = int($FRAMES / $CHUNKS); rem = $FRAMES % $CHUNKS; f0 = 0;
  for (i = 0; i < $i; i++) f0 += base + (i < rem ? 1 : 0);
  f1 = f0 + base + ($i < rem ? 1 : 0);
  printf \"%d %d\", f0, f1
}")
EOF
  FROM=$(awk "BEGIN{printf \"%.6f\", $f0 / $FPS}")
  TO=$(awk "BEGIN{printf \"%.6f\", $f1 / $FPS}")
  echo "  chunk $i: frames $f0..$((f1 - 1))  ($FROM -> $TO s)"
  ( cd "$HERE/.." && node scripts/render.ts video --url "$URL" --fps "$FPS" --noaudio \
      --from "$FROM" --to "$TO" --out "$DIR/chunk_$i.mp4" "${EXTRA[@]}" > "$DIR/chunk_$i.log" 2>&1 ) &
  PIDS+=($!)
done

FAIL=0
for p in "${PIDS[@]}"; do wait "$p" || FAIL=1; done
grep -h '^wrote' "$DIR"/chunk_*.log || true
[ "$FAIL" -eq 0 ] || { echo "a chunk failed; its log is in $DIR" >&2; exit 1; }

# concatenate: same encoder settings everywhere, so the video stream can be copied as-is
cd "$DIR"
printf "file '%s'\n" chunk_*.mp4 > list.txt
mkdir -p "$(dirname "$OUT")"
set +e
ffmpeg -y -loglevel error -f concat -safe 0 -i list.txt -i "$AUDIO" -map 0:v:0 -map 1:a:0 \
  -c:v copy -c:a aac -b:a 320k -shortest -movflags +faststart "$OUT"
CONCAT=$?
set -e
if [ $CONCAT -ne 0 ]; then
  echo "stream copy failed, re-encoding (this takes a few minutes)" >&2
  ffmpeg -y -loglevel error -f concat -safe 0 -i list.txt -i "$AUDIO" -map 0:v:0 -map 1:a:0 \
    -c:v libx264 -preset fast -crf 17 -pix_fmt yuv420p -tune grain -x264-params aq-mode=3 \
    -c:a aac -b:a 320k -shortest -movflags +faststart "$OUT"
fi

echo "wrote $OUT  ($(du -sh "$OUT" | cut -f1))  chunks in $DIR"
ffprobe -v error -show_entries format=duration,size -show_entries stream=width,height,r_frame_rate,codec_name \
  -of default=nw=1 "$OUT" | sed 's/^/  /'
