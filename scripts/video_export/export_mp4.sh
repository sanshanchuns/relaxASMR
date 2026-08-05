#!/usr/bin/env bash
# Mux looped 60fps video + audio → MP4 (H.264 + AAC).
# Default: quality mode (CRF/CQ) — bitrate varies with scene complexity / noise.
# Fixed bitrate: pass --video-bitrate. Output duration follows audio unless --duration.

set -euo pipefail

if [[ "$(uname -s)" == "Darwin" ]]; then
  export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH}"
fi

VIDEO=""
AUDIO=""
OUTPUT=""
DURATION=""
ENCODE_MODE="quality"   # quality (CRF/CQ) | bitrate (fixed -b:v)
VIDEO_CRF=""
VIDEO_CQ=""
VIDEO_BITRATE=""
MAXRATE=""
BUFSIZE=""
PROGRESS_ESTIMATE=""
VIDEO_BITRATE_MANUAL=false
CRF_MANUAL=false
AUDIO_BITRATE="192k"
PRESET="medium"
ENCODER="auto"  # auto | cpu (libx264) | nvenc (NVIDIA) | videotoolbox (macOS GPU)
THREADS="0"     # 0 = libx264 auto (use all cores)
VIDEO_FADE_IN="5"  # seconds; 0 = off. Matches Reaper Group 5s fade-in.

cpu_count() {
  if command -v nproc >/dev/null 2>&1; then
    nproc
  elif [[ "$(uname -s)" == "Darwin" ]]; then
    sysctl -n hw.ncpu 2>/dev/null || echo 4
  else
    getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4
  fi
}

ffmpeg_has_encoder() {
  local name="$1"
  ffmpeg -hide_banner -encoders 2>/dev/null | grep -q " ${name} "
}

build_encoder_list() {
  ENCODER_LIST=()
  case "$ENCODER" in
    cpu)
      ENCODER_LIST=("cpu")
      ;;
    nvenc)
      ENCODER_LIST=("nvenc" "cpu")
      ;;
    videotoolbox|vt)
      ENCODER_LIST=("videotoolbox" "cpu")
      ;;
    auto)
      if [[ "$(uname -s)" == "Darwin" ]] && ffmpeg_has_encoder "h264_videotoolbox"; then
        ENCODER_LIST=("videotoolbox" "cpu")
      elif ffmpeg_has_encoder "h264_nvenc"; then
        ENCODER_LIST=("nvenc" "cpu")
      else
        ENCODER_LIST=("cpu")
      fi
      ;;
    *)
      ENCODER_LIST=("$ENCODER" "cpu")
      ;;
  esac
}

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

apply_quality_for_width() {
  local w="$1"
  ENCODE_MODE="quality"
  if [[ "$w" -ge 3840 ]]; then
    VIDEO_CRF="20"
    VIDEO_CQ="20"
    MAXRATE="25M"
    BUFSIZE="50M"
    PROGRESS_ESTIMATE="15M"
  elif [[ "$w" -ge 1920 ]]; then
    VIDEO_CRF="22"
    VIDEO_CQ="22"
    MAXRATE="10M"
    BUFSIZE="20M"
    PROGRESS_ESTIMATE="6M"
  elif [[ "$w" -ge 1280 ]]; then
    VIDEO_CRF="23"
    VIDEO_CQ="23"
    MAXRATE="6M"
    BUFSIZE="12M"
    PROGRESS_ESTIMATE="4M"
  else
    VIDEO_CRF="24"
    VIDEO_CQ="24"
    MAXRATE="4M"
    BUFSIZE="8M"
    PROGRESS_ESTIMATE="2M"
  fi
}

apply_bitrate_for_width() {
  local w="$1"
  ENCODE_MODE="bitrate"
  if [[ "$w" -ge 3840 ]]; then
    VIDEO_BITRATE="20M"
    MAXRATE="25M"
    BUFSIZE="40M"
  elif [[ "$w" -ge 1920 ]]; then
    VIDEO_BITRATE="8M"
    MAXRATE="10M"
    BUFSIZE="16M"
  elif [[ "$w" -ge 1280 ]]; then
    VIDEO_BITRATE="5M"
    MAXRATE="6M"
    BUFSIZE="10M"
  else
    VIDEO_BITRATE="3M"
    MAXRATE="4M"
    BUFSIZE="6M"
  fi
  PROGRESS_ESTIMATE="$VIDEO_BITRATE"
}

video_encode_summary() {
  if [[ "$ENCODE_MODE" == "quality" ]]; then
    printf 'CRF/CQ %s (variable bitrate, max %s)' "$VIDEO_CRF" "$MAXRATE"
  else
    printf 'target %s max %s bufsize %s' "$VIDEO_BITRATE" "$MAXRATE" "$BUFSIZE"
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

parse_bitrate_bps() {
  local raw="${1:-0}"
  if [[ "$raw" =~ ^([0-9]+(\.[0-9]+)?)[kK]$ ]]; then
    awk -v n="${BASH_REMATCH[1]}" 'BEGIN {printf "%.0f", n * 1000}'
  elif [[ "$raw" =~ ^([0-9]+(\.[0-9]+)?)[mM]$ ]]; then
    awk -v n="${BASH_REMATCH[1]}" 'BEGIN {printf "%.0f", n * 1000000}'
  elif [[ "$raw" =~ ^[0-9]+$ ]]; then
    printf '%s' "$raw"
  else
    printf '0'
  fi
}

file_size_bytes() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    printf '0'
    return
  fi
  stat -c%s "$path" 2>/dev/null || stat -f%z "$path" 2>/dev/null || printf '0'
}

verify_inputs() {
  local missing=0
  if [[ ! -f "$VIDEO" ]]; then
    echo "Error: video input missing: $VIDEO" >&2
    missing=1
  fi
  if [[ ! -f "$AUDIO" ]]; then
    echo "Error: audio input missing: $AUDIO" >&2
    missing=1
  fi
  return "$missing"
}

encode_part_path() {
  local output="$1"
  local enc="$2"
  printf '%s.%s.part.mp4' "${output%.mp4}" "$enc"
}

cleanup_encode_artifacts() {
  local output="$1"
  rm -f "$output"
  rm -f "${output%.mp4}".*.part.mp4
  rm -f "${output}.faststart.tmp.mp4"
}

apply_faststart() {
  local src="$1"
  local dst="$2"
  local tmp="${dst}.faststart.tmp.mp4"

  if [[ ! -f "$src" ]]; then
    echo "Error: encoded part missing: $src" >&2
    return 1
  fi

  echo "==> Applying faststart remux…"
  if ffmpeg -y -hide_banner -loglevel error -i "$src" -c copy -movflags +faststart "$tmp"; then
    mv -f "$tmp" "$dst"
    rm -f "$src"
    return 0
  fi

  rm -f "$tmp"
  echo "Warning: faststart remux failed; keeping encoded file without faststart." >&2
  mv -f "$src" "$dst"
  return 0
}

run_ffmpeg_with_progress() {
  local target_sec="$1"
  local output_file="$2"
  shift 2
  local progress_file
  progress_file=$(mktemp)
  trap 'rm -f "$progress_file"' RETURN

  local video_bps audio_bps expected_bytes estimate_raw
  estimate_raw="${PROGRESS_ESTIMATE:-$VIDEO_BITRATE}"
  video_bps=$(parse_bitrate_bps "$estimate_raw")
  audio_bps=$(parse_bitrate_bps "$AUDIO_BITRATE")
  expected_bytes=$(awk -v dur="$target_sec" -v vb="$video_bps" -v ab="$audio_bps" \
    'BEGIN {printf "%.0f", dur * (vb + ab) / 8 * 1.05}')

  ffmpeg -nostats -loglevel error -progress "$progress_file" "$@" &
  local ffmpeg_pid=$!

  while kill -0 "$ffmpeg_pid" 2>/dev/null; do
    local elapsed out_us out_sec target_us progress_state speed_val
    elapsed=$(( $(date +%s) - START_TS ))
    out_us=0
    out_sec=0
    progress_state=""
    speed_val=""
    if [[ -f "$progress_file" ]]; then
      local raw
      raw=$(grep -E '^out_time_us=' "$progress_file" | tail -1 | cut -d= -f2)
      if is_uint "$raw"; then
        out_us=$raw
        out_sec=$(( out_us / 1000000 ))
      fi
      progress_state=$(grep -E '^progress=' "$progress_file" | tail -1 | cut -d= -f2 || true)
      raw=$(grep -E '^speed=' "$progress_file" | tail -1 | cut -d= -f2 || true)
      if [[ -n "$raw" ]]; then
        speed_val=$(awk -v s="$raw" 'BEGIN { gsub(/x$/,"",s); if (s+0>0.05) printf "%.4f", s+0 }')
      fi
    fi

    local pct=0 byte_pct=0 display_pct=0 out_bytes remain_sec=0
    local pct_display="…" remain_display="…"

    if awk -v t="$target_sec" 'BEGIN {exit (t > 0) ? 0 : 1}'; then
      target_us=$(awk -v t="$target_sec" 'BEGIN {printf "%d", t * 1000000}')
      out_bytes=$(file_size_bytes "$output_file")

      if is_uint "$out_us" && is_uint "$target_us" && [[ "$out_us" -gt 0 && "$target_us" -gt 0 ]]; then
        pct=$((out_us * 100 / target_us))
        if [[ "$pct" -gt 100 ]]; then pct=100; fi
      fi
      if is_uint "$expected_bytes" && [[ "$expected_bytes" -gt 0 && "$out_bytes" -gt 0 ]]; then
        byte_pct=$((out_bytes * 100 / expected_bytes))
        if [[ "$byte_pct" -gt 100 ]]; then byte_pct=100; fi
      fi

      display_pct=$pct
      if [[ "$byte_pct" -gt 0 && ( "$byte_pct" -lt "$display_pct" || "$pct" -ge 97 ) ]]; then
        display_pct=$byte_pct
      fi

      if [[ "$progress_state" == "end" ]]; then
        pct_display="100%"
        remain_display="00:00:00"
      elif [[ "$display_pct" -gt 0 ]]; then
        local remain_speed=0 remain_linear=0 remain_bytes=0 remain_project=0
        if [[ -n "$speed_val" ]]; then
          remain_speed=$(awk -v t="$target_sec" -v o="$out_sec" -v sp="$speed_val" \
            'BEGIN {printf "%.0f", (t-o)/sp}')
        fi
        if [[ "$out_us" -gt 0 ]]; then
          remain_linear=$(( elapsed * (target_us - out_us) / out_us ))
        fi
        if [[ "$expected_bytes" -gt "$out_bytes" && "$out_bytes" -gt 0 ]]; then
          remain_bytes=$(( (expected_bytes - out_bytes) / 100000000 ))
          if [[ "$byte_pct" -ge 90 ]]; then
            remain_bytes=$(( remain_bytes + 30 ))
          fi
        fi
        if [[ "$display_pct" -ge 5 && "$display_pct" -lt 100 ]]; then
          remain_project=$(( elapsed * (100 - display_pct) / display_pct ))
        fi

        remain_sec=$remain_linear
        for candidate in "$remain_speed" "$remain_bytes" "$remain_project"; do
          if [[ "$candidate" -gt "$remain_sec" ]]; then
            remain_sec=$candidate
          fi
        done

        pct_display="${display_pct}%"
        remain_display=$(format_remaining "$remain_sec")
      fi
    fi

    if [[ -t 1 ]]; then
      printf "\r  Elapsed: %s  Remaining: ~%s  (%s)  " \
        "$(format_elapsed "$elapsed")" \
        "$remain_display" \
        "$pct_display"
    else
      printf "PROGRESS Elapsed: %s  Remaining: ~%s  (%s)\n" \
        "$(format_elapsed "$elapsed")" \
        "$remain_display" \
        "$pct_display"
    fi
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
      --encoder MODE     cpu (libx264) | nvenc (NVIDIA GPU) | videotoolbox (macOS GPU) | auto
      --threads N        libx264 thread count, 0=auto (default: 0)
      --crf N            Quality mode: x264 CRF / NVENC CQ (default: 20=4K, 22=FHD)
      --video-bitrate B  Fixed bitrate mode: 20M (4K) / 8M (FHD) instead of CRF/CQ
      --maxrate B        Peak VBV cap (auto by resolution in quality mode)
      --bufsize B        VBV buffer (auto by resolution)
      --audio-bitrate B   Default: 192k
      --preset NAME       cpu: x264 preset (default: medium)
                          nvenc: p1–p7 (default: p5)
      --video-fade-in SEC  Fade video from black at start (default: 5, matches audio)
      --no-video-fade-in   Disable video fade-in
      --print-output       Print default output path and exit (no encode)
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
    --video-bitrate) VIDEO_BITRATE="$2"; VIDEO_BITRATE_MANUAL=true; ENCODE_MODE="bitrate"; shift 2 ;;
    --crf) VIDEO_CRF="$2"; VIDEO_CQ="$2"; CRF_MANUAL=true; ENCODE_MODE="quality"; shift 2 ;;
    --maxrate) MAXRATE="$2"; shift 2 ;;
    --bufsize) BUFSIZE="$2"; shift 2 ;;
    --audio-bitrate) AUDIO_BITRATE="$2"; shift 2 ;;
    --video-fade-in) VIDEO_FADE_IN="$2"; shift 2 ;;
    --no-video-fade-in) VIDEO_FADE_IN="0"; shift ;;
    --preset) PRESET="$2"; shift 2 ;;
    --print-output) PRINT_OUTPUT_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

PRINT_OUTPUT_ONLY="${PRINT_OUTPUT_ONLY:-0}"

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

video_w=""
if ! video_w=$(probe_video_width "$VIDEO" 2>/dev/null); then
  echo "Warning: could not probe video width; assuming FHD (1920)" >&2
  video_w=1920
fi

if [[ "$VIDEO_BITRATE_MANUAL" == true ]]; then
  user_br="$VIDEO_BITRATE"
  apply_bitrate_for_width "$video_w"
  VIDEO_BITRATE="$user_br"
  PROGRESS_ESTIMATE="$user_br"
  if [[ -z "$MAXRATE" || -z "$BUFSIZE" ]]; then
    local_bps=$(parse_bitrate_bps "$VIDEO_BITRATE")
    if [[ "$local_bps" -gt 0 ]]; then
      MAXRATE=$(awk -v b="$local_bps" 'BEGIN {printf "%.0fM", b * 1.25 / 1000000}')
      BUFSIZE=$(awk -v b="$local_bps" 'BEGIN {printf "%.0fM", b * 2 / 1000000}')
    fi
  fi
elif [[ "$CRF_MANUAL" == true ]]; then
  saved_crf="$VIDEO_CRF"
  apply_quality_for_width "$video_w"
  VIDEO_CRF="$saved_crf"
  VIDEO_CQ="$saved_crf"
else
  apply_quality_for_width "$video_w"
fi

if [[ -z "$OUTPUT" ]]; then
  OUTPUT=$(default_output_path "$AUDIO" "$VIDEO")
fi

if [[ "$PRINT_OUTPUT_ONLY" == "1" ]]; then
  printf '%s\n' "$OUTPUT"
  exit 0
fi

mkdir -p "$(dirname "$OUTPUT")"

TARGET_SEC=""
if [[ -n "$DURATION" ]]; then
  TARGET_SEC="$DURATION"
else
  TARGET_SEC=$(probe_duration_sec "$AUDIO" || echo "0")
fi

ENCODER_LIST=()
build_encoder_list

echo "==> Video:  $VIDEO (looped)"
res_label=$(resolution_suffix_from_width "$video_w" | tr -d '_')
echo "==> Video size: ${video_w}px wide (${res_label} suffix)"
echo "==> Audio:  $AUDIO"
echo "==> Output: $OUTPUT"
echo "==> Video encode: $(video_encode_summary)"
echo "==> Audio encode: aac ${AUDIO_BITRATE}"
if awk -v f="$VIDEO_FADE_IN" 'BEGIN {exit (f+0 > 0) ? 0 : 1}'; then
  fade_d="$VIDEO_FADE_IN"
  if [[ -n "$TARGET_SEC" && "$TARGET_SEC" != "0" ]]; then
    fade_d=$(awk -v f="$VIDEO_FADE_IN" -v t="$TARGET_SEC" \
      'BEGIN {printf "%.3f", (f+0 < t+0 ? f+0 : t+0)}')
  fi
  echo "==> Video fade-in: ${fade_d}s (black → content)"
fi
if [[ -n "$TARGET_SEC" && "$TARGET_SEC" != "0" ]]; then
  echo "==> Target duration: $(format_elapsed "${TARGET_SEC%.*}") (${TARGET_SEC}s)"
fi
echo

START_TS=$(date +%s)
echo "==> Started:  $(date '+%Y-%m-%d %H:%M:%S')"
echo

success=false
for current_enc in "${ENCODER_LIST[@]}"; do
  if ! verify_inputs; then
    echo "Error: cannot continue encoder ${current_enc} without inputs." >&2
    break
  fi

  encode_part=$(encode_part_path "$OUTPUT" "$current_enc")
  cleanup_encode_artifacts "$OUTPUT"

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

  if awk -v f="$VIDEO_FADE_IN" 'BEGIN {exit (f+0 > 0) ? 0 : 1}'; then
    fade_d="$VIDEO_FADE_IN"
    if [[ -n "$TARGET_SEC" && "$TARGET_SEC" != "0" ]]; then
      fade_d=$(awk -v f="$VIDEO_FADE_IN" -v t="$TARGET_SEC" \
        'BEGIN {printf "%.3f", (f+0 < t+0 ? f+0 : t+0)}')
    fi
    ffmpeg_args+=(-vf "fade=t=in:st=0:d=${fade_d}")
  fi

  case "$current_enc" in
    cpu)
      if [[ "$ENCODE_MODE" == "quality" ]]; then
        ffmpeg_args+=(
          -c:v libx264 -preset "$PRESET"
          -threads "$THREADS"
          -crf "$VIDEO_CRF"
          -maxrate "$MAXRATE" -bufsize "$BUFSIZE"
          -pix_fmt yuv420p
        )
        ENCODE_DESC="libx264 preset=${PRESET} crf=${VIDEO_CRF} (quality/VBR)"
      else
        ffmpeg_args+=(
          -c:v libx264 -preset "$PRESET"
          -threads "$THREADS"
          -b:v "$VIDEO_BITRATE" -maxrate "$MAXRATE" -bufsize "$BUFSIZE"
          -pix_fmt yuv420p
        )
        ENCODE_DESC="libx264 preset=${PRESET} ${VIDEO_BITRATE} (fixed)"
      fi
      if [[ "$THREADS" == "0" ]]; then
        ENCODE_DESC+=" threads=auto ($(cpu_count) cores)"
      else
        ENCODE_DESC+=" threads=${THREADS}"
      fi
      ;;
    videotoolbox)
      vt_target="${PROGRESS_ESTIMATE:-$MAXRATE}"
      if [[ "$ENCODE_MODE" == "quality" ]]; then
        ffmpeg_args+=(
          -c:v h264_videotoolbox
          -b:v "$vt_target"
          -maxrate "$MAXRATE" -bufsize "$BUFSIZE"
          -pix_fmt yuv420p
          -allow_sw 1
        )
        ENCODE_DESC="h264_videotoolbox target=${vt_target} max=${MAXRATE} (quality/VBR)"
      else
        ffmpeg_args+=(
          -c:v h264_videotoolbox
          -b:v "$VIDEO_BITRATE" -maxrate "$MAXRATE" -bufsize "$BUFSIZE"
          -pix_fmt yuv420p
          -allow_sw 1
        )
        ENCODE_DESC="h264_videotoolbox ${VIDEO_BITRATE} (fixed)"
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
      if [[ "$ENCODE_MODE" == "quality" ]]; then
        ffmpeg_args+=(
          -c:v h264_nvenc
          -preset "$nvenc_preset"
          -rc vbr
          -cq "$VIDEO_CQ"
          -b:v 0
          -maxrate "$MAXRATE" -bufsize "$BUFSIZE"
          -pix_fmt yuv420p
        )
        ENCODE_DESC="h264_nvenc preset=${nvenc_preset} cq=${VIDEO_CQ} (quality/VBR)"
      else
        ffmpeg_args+=(
          -c:v h264_nvenc
          -preset "$nvenc_preset"
          -rc vbr
          -b:v "$VIDEO_BITRATE" -maxrate "$MAXRATE" -bufsize "$BUFSIZE"
          -pix_fmt yuv420p
        )
        ENCODE_DESC="h264_nvenc preset=${nvenc_preset} ${VIDEO_BITRATE} (fixed)"
      fi
      ;;
  esac

  ffmpeg_args+=(
    -c:a aac -b:a "$AUDIO_BITRATE" -ar 48000
  )

  echo "==> Attempting Video encode: ${ENCODE_DESC} max ${MAXRATE} (60fps source)"
  echo "==> Encode temp: $encode_part (faststart applied after encode)"
  
  if run_ffmpeg_with_progress "$TARGET_SEC" "$encode_part" "${ffmpeg_args[@]}" "$encode_part"; then
    if apply_faststart "$encode_part" "$OUTPUT"; then
      success=true
      break
    fi
    echo "Warning: post-encode finalize failed for encoder ${current_enc}." >&2
  else
    echo "Warning: ffmpeg failed with encoder ${current_enc}." >&2
  fi

  rm -f "$encode_part"
  echo "Falling back to next encoder if available..." >&2
  echo
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
