#!/usr/bin/env bash
# Mux looped 60fps video + audio → MP4 (H.264 constrained VBR 30M + AAC).
# Output duration follows audio length unless --duration is set.

set -euo pipefail

VIDEO=""
AUDIO=""
OUTPUT=""
DURATION=""
VIDEO_BITRATE="30M"
MAXRATE="38M"
BUFSIZE="60M"
AUDIO_BITRATE="192k"
PRESET="medium"
ENCODER="cpu"   # cpu = libx264 (multi-thread) | nvenc = h264_nvenc (GPU)
THREADS="0"     # 0 = libx264 auto (use all cores)

format_elapsed() {
  local s=$1
  printf '%02d:%02d:%02d' $((s / 3600)) $((s % 3600 / 60)) $((s % 60))
}

usage() {
  cat <<'EOF'
Usage: export_mp4.sh -v VIDEO -a AUDIO -o OUTPUT [options]

  -v, --video PATH       Video source (looped to match audio)
  -a, --audio PATH       Audio source (WAV etc.; sets duration)
  -o, --output PATH      Output .mp4
  -d, --duration SEC     Cap output length (default: full audio)
      --encoder MODE     cpu (libx264, default) | nvenc (GPU h264_nvenc)
      --threads N        libx264 thread count, 0=auto (default: 0)
      --video-bitrate B   Default: 30M (4K 60fps)
      --maxrate B         Default: 38M
      --bufsize B         Default: 60M
      --audio-bitrate B   Default: 192k
      --preset NAME       cpu: x264 preset (default: medium)
                          nvenc: p1–p7 (default: p5)
  -h, --help

Example:
  ./scripts/export_mp4.sh \
    -v "Audio Files/stream_loop_video.mp4" \
    -a output/stream_bgm_2min.wav \
    -o output/stream_heal_2min_vbr.mp4

  # GPU encode (RTX, much faster):
  ./scripts/export_mp4.sh ... --encoder nvenc
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -v|--video) VIDEO="$2"; shift 2 ;;
    -a|--audio) AUDIO="$2"; shift 2 ;;
    -o|--output) OUTPUT="$2"; shift 2 ;;
    -d|--duration) DURATION="$2"; shift 2 ;;
    --encoder) ENCODER="$2"; shift 2 ;;
    --threads) THREADS="$2"; shift 2 ;;
    --video-bitrate) VIDEO_BITRATE="$2"; shift 2 ;;
    --maxrate) MAXRATE="$2"; shift 2 ;;
    --bufsize) BUFSIZE="$2"; shift 2 ;;
    --audio-bitrate) AUDIO_BITRATE="$2"; shift 2 ;;
    --preset) PRESET="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "$VIDEO" || -z "$AUDIO" || -z "$OUTPUT" ]]; then
  echo "Error: -v, -a, -o are required." >&2
  usage >&2
  exit 1
fi

if [[ ! -f "$VIDEO" ]]; then
  echo "Error: video not found: $VIDEO" >&2
  exit 1
fi

if [[ ! -f "$AUDIO" ]]; then
  echo "Error: audio not found: $AUDIO" >&2
  exit 1
fi

case "$ENCODER" in
  cpu|nvenc) ;;
  *)
    echo "Error: --encoder must be cpu or nvenc (got: $ENCODER)" >&2
    exit 1
    ;;
esac

mkdir -p "$(dirname "$OUTPUT")"

ffmpeg_args=(
  -y
  -stream_loop -1 -i "$VIDEO"
  -i "$AUDIO"
)

if [[ -n "$DURATION" ]]; then
  ffmpeg_args+=(-t "$DURATION")
else
  ffmpeg_args+=(-shortest)
fi

ffmpeg_args+=(-map 0:v:0 -map 1:a:0)

case "$ENCODER" in
  cpu)
    ffmpeg_args+=(
      -c:v libx264 -preset "$PRESET"
      -threads "$THREADS"
      -b:v "$VIDEO_BITRATE" -maxrate "$MAXRATE" -bufsize "$BUFSIZE"
      -pix_fmt yuv420p
    )
    if [[ "$THREADS" == "0" ]]; then
      ENCODE_DESC="libx264 preset=${PRESET} threads=auto ($(nproc) cores)"
    else
      ENCODE_DESC="libx264 preset=${PRESET} threads=${THREADS}"
    fi
    ;;
  nvenc)
    # Map x264-style preset names to NVENC p-level if user didn't pass pN
    nvenc_preset="$PRESET"
    case "$PRESET" in
      ultrafast|superfast|veryfast|fast) nvenc_preset="p3" ;;
      medium) nvenc_preset="p5" ;;
      slow) nvenc_preset="p6" ;;
      slower|veryslow) nvenc_preset="p7" ;;
      p[1-7]) nvenc_preset="$PRESET" ;;
    esac
    ffmpeg_args+=(
      -c:v h264_nvenc
      -preset "$nvenc_preset"
      -rc:v vbr
      -b:v "$VIDEO_BITRATE" -maxrate "$MAXRATE" -bufsize "$BUFSIZE"
      -pix_fmt yuv420p
    )
    ENCODE_DESC="h264_nvenc preset=${nvenc_preset} (GPU VBR)"
    ;;
esac

ffmpeg_args+=(
  -c:a aac -b:a "$AUDIO_BITRATE" -ar 48000
  -movflags +faststart
)

echo "==> Video:  $VIDEO (looped)"
echo "==> Audio:  $AUDIO"
echo "==> Output: $OUTPUT"
echo "==> Video encode: ${ENCODE_DESC} ${VIDEO_BITRATE} max ${MAXRATE} (60fps source)"
echo "==> Audio encode: aac ${AUDIO_BITRATE}"
echo

START_TS=$(date +%s)
echo "==> Started:  $(date '+%Y-%m-%d %H:%M:%S')"
echo

ffmpeg "${ffmpeg_args[@]}" "$OUTPUT"

END_TS=$(date +%s)
ELAPSED=$((END_TS - START_TS))

echo
echo "==> Done: $OUTPUT"
echo "==> Elapsed: $(format_elapsed "$ELAPSED") (${ELAPSED}s)"
ffprobe -v error -show_entries format=duration,size,bit_rate \
  -show_entries stream=codec_type,width,height,bit_rate \
  -of default=nw=1 "$OUTPUT"

# YouTube material (metadata + thumbnail)
MATERIAL_SCRIPT="$(dirname "${BASH_SOURCE[0]}")/generate_youtube_material.sh"
if [[ -x "$MATERIAL_SCRIPT" ]]; then
  echo
  echo "==> Generating YouTube material ..."
  "$MATERIAL_SCRIPT" "$OUTPUT" || echo "Warning: material generation failed (non-fatal)" >&2
fi
