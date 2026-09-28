#!/usr/bin/env bash
# Renders the song in N parallel chunks (one headless Chrome + one ffmpeg each) and
# concatenates the result.
#
# Why: the offline render is CPU-bound on the per-sub-frame scene work — an image at 1080p
# costs about as much as the same image at 4K (roughly 35-80 ms per sub-frame, see `perf`),
# so a single `render.ts video` leaves every other core idle. Independent time ranges scale
# nearly linearly: 16 chunks on an 8-core/16-thread desktop finish the whole song in about
# a tenth of the wall clock of one instance.
#
#   bash scripts/render-chunks.sh [--chunks 16] [--fps 60] [--dur 199.9333]
#                                [--url http://localhost:5173] [--out ../out/pdoom.mp4]
#                                [--stagger 1.5] [-- <flags for render.ts>]
#
# Flags after `--` go to render.ts (`--samples`, `--shutter`, `--crf`, `--preset`, `--scale`).
# Chunks are rendered with --noaudio (AAC priming at every seam clicks) and the audio is
# muxed once, at the end, from audio/pdoom.mp3 (`--audio` to point elsewhere).
#
# A dozen pages loading at once makes a cold Vite dev server refuse connections or time out,
# so launches are staggered and failed chunks are retried (--stagger 0 to hammer it instead).
#
# Run it with bash; render.ts itself must run under node (see its header).
set -euo pipefail

CHUNKS=16
FPS=60
DUR=199.9333
URL=http://localhost:5173
STAGGER=1.5
ATTEMPTS=3
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
    --stagger) STAGGER=$2; shift 2 ;;
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

# boundaries on whole frames, as evenly as possible: chunk i covers frames F0[i] .. F1[i]-1
FROM=(); TO=()
for i in $(seq 0 $((CHUNKS - 1))); do
  read -r f0 f1 <<EOF
$(awk "BEGIN{
  base = int($FRAMES / $CHUNKS); rem = $FRAMES % $CHUNKS; f0 = 0;
  for (i = 0; i < $i; i++) f0 += base + (i < rem ? 1 : 0);
  f1 = f0 + base + ($i < rem ? 1 : 0);
  printf \"%d %d\", f0, f1
}")
EOF
  FROM[$i]=$(awk "BEGIN{printf \"%.6f\", $f0 / $FPS}")
  TO[$i]=$(awk "BEGIN{printf \"%.6f\", $f1 / $FPS}")
  echo "  chunk $i: frames $f0..$((f1 - 1))  (${FROM[$i]} -> ${TO[$i]} s)"
done

PENDING=($(seq 0 $((CHUNKS - 1))))
for attempt in $(seq 1 "$ATTEMPTS"); do
  [ ${#PENDING[@]} -gt 0 ] || break
  echo "attempt $attempt: ${#PENDING[@]} chunk(s)"
  PIDS=(); IDX=()
  for i in "${PENDING[@]}"; do
    NAME="$(printf 'chunk_%02d' "$i")"   # padded: the concat list must not sort 10 before 2
    ( cd "$HERE/.." && node scripts/render.ts video --url "$URL" --fps "$FPS" --noaudio \
        --from "${FROM[$i]}" --to "${TO[$i]}" --out "$DIR/$NAME.mp4" "${EXTRA[@]}" \
        > "$DIR/$NAME.log" 2>&1 ) &
    PIDS+=($!); IDX+=("$i")
    [ "$i" = "${PENDING[-1]}" ] || sleep "$STAGGER"
  done
  FAILED=()
  for k in "${!PIDS[@]}"; do wait "${PIDS[$k]}" || FAILED+=("${IDX[$k]}"); done
  PENDING=(${FAILED[@]+"${FAILED[@]}"})
  if [ ${#PENDING[@]} -gt 0 ]; then echo "  failed: ${PENDING[*]} (log in $DIR/chunk_<i>.log)"; fi
done
grep -h '^wrote' "$DIR"/chunk_*.log || true
[ ${#PENDING[@]} -eq 0 ] || { echo "chunk(s) ${PENDING[*]} still failing after $ATTEMPTS attempts" >&2; exit 1; }

# concatenate: same encoder settings everywhere, so the video stream can be copied as-is
cd "$DIR"
for i in $(seq 0 $((CHUNKS - 1))); do printf "file '%s'\n" "$(printf 'chunk_%02d' "$i").mp4"; done > list.txt
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
