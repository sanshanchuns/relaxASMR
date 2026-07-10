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
ENCODER="auto"  # auto (detect gpu) | cpu = libx264 (multi-thread) | nvenc = h264_nvenc (GPU)
THREADS="0"     # 0 = libx264 auto (use all cores)

format_elapsed() {
  local s=${1%.*}
  if [[ -z "$s" || ! "$s" =~ ^[0-9]+$ ]]; then s=0; fi
  if [[ "$s" -lt 0 ]]; then s=0; fi
  printf '%02d:%02d:%02d' $((s / 3600)) $((s % 3600 / 60)) $((s % 60))
}

format_remaining() {
  local s=${1%.*}
  if [[ -z "$s" || ! "$s" =~ ^[0-9]+$ ]]; then s=0; fi
  if [[ "$s" -lt 0 ]]; then s=0; fi
  printf '%02d:%02d:%02d' $((s / 3600)) $((s % 3600 / 60)) $((s % 60))
}

is_uint() {
  [[ "${1:-}" =~ ^[0-9]+$ ]]
}

probe_duration_sec() {
  local path="$1"
  local d
  d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$path" 2>/dev/null || true)
  if [[ -z "$d" || "$d" == "N/A" ]]; then
    return 1
  fi
  awk "BEGIN {printf \"%.3f\", $d}"
}

probe_video_width() {
  local path="$1"
  local w
  w=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$path" 2>/dev/null || true)
  if [[ "$w" =~ ^[0-9]+$ ]]; then
    printf '%s' "$w"
    return 0
  fi
  return 1
}

resolution_suffix_from_width() {
  local w="$1"
  if [[ "$w" -ge 3840 ]]; then
    printf '_4k'
  elif [[ "$w" -ge 1920 ]]; then
    printf '_fhd'
  elif [[ "$w" -ge 1280 ]]; then
    printf '_720p'
  else
    printf '_%sp' "$w"
  fi
}

strip_resolution_suffix() {
  local stem="$1"
  local token
  for token in _4k _fhd _1080p _720p _hd; do
    if [[ "$stem" == *"$token" ]]; then
      stem="${stem%"$token"}"
    fi
  done
  printf '%s' "$stem"
}

default_output_path() {
  local audio="$1"
  local video="$2"
  local dir base stem suffix width
  dir=$(dirname "$audio")
  base=$(basename "$audio")
  stem=$(strip_resolution_suffix "${base%.*}")
  
  # Ensure MVI_ prefix if stem is just numbers
  if [[ "$stem" =~ ^[0-9]+$ ]]; then
    stem="MVI_${stem}"
  fi
  
  local dur_suffix=""
  if [[ ! "$stem" =~ _[0-9]+(h|hr|min|m)$ ]]; then
    local d
    if d=$(probe_duration_sec "$audio" 2>/dev/null); then
      local d_int=${d%.*}
      if [[ -n "$d_int" && "$d_int" -gt 0 ]]; then
        local h=$(( (d_int + 1800) / 3600 ))
        if [[ "$h" -gt 0 ]]; then
          dur_suffix="_${h}h"
        else
          local m=$(( (d_int + 30) / 60 ))
          dur_suffix="_${m}min"
        fi
      fi
    fi
  fi

  if width=$(probe_video_width "$video"); then
    suffix=$(resolution_suffix_from_width "$width")
    printf '%s/%s%s%s.mp4' "$dir" "$stem" "$dur_suffix" "$suffix"
  else
    echo "Warning: could not probe video width; output name has no resolution suffix" >&2
    printf '%s/%s%s.mp4' "$dir" "$stem" "$dur_suffix"
  fi
}

run_ffmpeg_with_progress() {
  local target_sec="$1"
  shift
  local progress_file
  progress_file=$(mktemp)
  trap 'rm -f "$progress_file"' RETURN

  ffmpeg -nostats -loglevel error -progress "$progress_file" "$@" &
  local ffmpeg_pid=$!

  while kill -0 "$ffmpeg_pid" 2>/dev/null; do
    local now elapsed out_us remain_sec pct
    now=$(date +%s)
    elapsed=$((now - START_TS))
    out_us=0
    if [[ -f "$progress_file" ]]; then
      local raw
      raw=$(grep -E '^out_time_us=' "$progress_file" | tail -1 | cut -d= -f2)
      if is_uint "$raw"; then
        out_us=$raw
      fi
    fi

    remain_sec=0
    pct=0
    if awk -v t="$target_sec" 'BEGIN {exit (t > 0) ? 0 : 1}'; then
      local target_us
      target_us=$(awk -v t="$target_sec" 'BEGIN {printf "%d", t * 1000000}')
      if is_uint "$out_us" && is_uint "$target_us" && [[ "$out_us" -gt 0 && "$target_us" -gt 0 ]]; then
        pct=$((out_us * 100 / target_us))
        if [[ "$pct" -gt 100 ]]; then pct=100; fi
        local remain_us=$((target_us - out_us))
        if [[ "$remain_us" -lt 0 ]]; then remain_us=0; fi
        remain_sec=$((elapsed * remain_us / out_us))
      fi
    fi

    printf "\r  Elapsed: %s  Remaining: ~%s  (%d%%)  " \
      "$(format_elapsed "$elapsed")" \
      "$(format_remaining "$remain_sec")" \
      "$pct"
    sleep 1
  done

  wait "$ffmpeg_pid"
  local exit_code=$?
  printf "\n"
  return "$exit_code"
}

usage() {
  cat <<'EOF'
Usage: export_mp4.sh -v VIDEO -a AUDIO [-o OUTPUT] [options]

  -v, --video PATH       Video source (looped to match audio)
  -a, --audio PATH       Audio source (WAV etc.; sets duration)
  -o, --output PATH      Output .mp4 (default: <audio_dir>/<stem>_<res>.mp4;
                         res from video width: _4k ≥3840, _fhd ≥1920, _720p ≥1280)
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
  scripts/video_export/export_mp4.sh \
    -v assets/loop_video/rain_video/MVI_6918/MVI_6918_loop_3_fade_0.5.mp4 \
    -a Reaper/Projects/Rain/subprojects/MVI_6918/output/MVI_6918_3h.wav
  # 4K source => .../MVI_6918_3h_4k.mp4
  # 1080p source => .../MVI_6918_3h_fhd.mp4

  scripts/video_export/export_mp4.sh ... -o custom/path/out.mp4 --encoder nvenc
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

if [[ -z "$VIDEO" || -z "$AUDIO" ]]; then
  echo "Error: -v and -a are required." >&2
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

if [[ -z "$OUTPUT" ]]; then
  OUTPUT=$(default_output_path "$AUDIO" "$VIDEO")
fi

mkdir -p "$(dirname "$OUTPUT")"

TARGET_SEC=""
if [[ -n "$DURATION" ]]; then
  TARGET_SEC="$DURATION"
else
  TARGET_SEC=$(probe_duration_sec "$AUDIO" || echo "0")
fi

ENCODER_LIST=("$ENCODER")
if [[ "$ENCODER" == "auto" || "$ENCODER" == "nvenc" ]]; then
  ENCODER_LIST=("nvenc" "cpu")
fi

echo "==> Video:  $VIDEO (looped)"
if video_w=$(probe_video_width "$VIDEO" 2>/dev/null); then
  echo "==> Video size: ${video_w}px wide ($(resolution_suffix_from_width "$video_w" | tr -d '_') suffix)"
fi
echo "==> Audio:  $AUDIO"
echo "==> Output: $OUTPUT"
echo "==> Audio encode: aac ${AUDIO_BITRATE}"
if [[ -n "$TARGET_SEC" && "$TARGET_SEC" != "0" ]]; then
  echo "==> Target duration: $(format_elapsed "${TARGET_SEC%.*}") (${TARGET_SEC}s)"
fi
echo

START_TS=$(date +%s)
echo "==> Started:  $(date '+%Y-%m-%d %H:%M:%S')"
echo

success=false
for current_enc in "${ENCODER_LIST[@]}"; do
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

  case "$current_enc" in
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

  echo "==> Attempting Video encode: ${ENCODE_DESC} ${VIDEO_BITRATE} max ${MAXRATE} (60fps source)"
  
  if run_ffmpeg_with_progress "$TARGET_SEC" "${ffmpeg_args[@]}" "$OUTPUT"; then
    success=true
    break
  else
    echo "Warning: ffmpeg failed with encoder ${current_enc}." >&2
    echo "Falling back to next encoder if available..." >&2
    echo
  fi
done

if [[ "$success" == "false" ]]; then
  echo "Error: All encoders failed" >&2
  exit 1
fi

END_TS=$(date +%s)
ELAPSED=$((END_TS - START_TS))

echo
echo "==> Done: $OUTPUT"
echo "==> Finished in $(format_elapsed "$ELAPSED")"
ffprobe -v error -show_entries format=duration,size,bit_rate \
  -show_entries stream=codec_type,width,height,bit_rate \
  -of default=nw=1 "$OUTPUT"

TOTAL_ELAPSED=$(( $(date +%s) - START_TS ))
echo "==> All done. Finished in $(format_elapsed "$TOTAL_ELAPSED")"
