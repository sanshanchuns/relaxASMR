-- @description ASMR · 长时音量包络（正弦 / 余弦）
-- @version 4.2
-- @author relaxASMR
-- @about
--   对指定轨 Volume 包络写入 dB 偏移曲线（0 dB = 轨音量不变）。
--   参数：时长、点数、最大/最小 dB、正弦/余弦。

local r = reaper

local function log(msg)
  r.ShowConsoleMsg("[vol_envelope] " .. msg .. "\n")
end

local function clamp(x, lo, hi)
  if x < lo then return lo end
  if x > hi then return hi end
  return x
end

local function parse_num(s, default)
  if type(s) == "number" then return s end
  s = tostring(s or ""):match("^%s*(.-)%s*$") or ""
  local n = tonumber(s)
  if n == nil then return default end
  return n
end

local function db_to_linear(db)
  return 10 ^ (db / 20)
end

local function linear_to_db(lin)
  if lin <= 0 then return -150 end
  return 20 * math.log(lin, 10)
end

local function track_name(tr)
  local _, name = r.GetTrackName(tr)
  return name or ""
end

local function resolve_track(key)
  key = (key or ""):match("^%s*(.-)%s*$") or ""
  if key == "" or key == "0" then
    return r.GetSelectedTrack(0, 0), key
  end
  local n = tonumber(key)
  if n and n > 0 then
    return r.GetTrack(0, n - 1), "track " .. n
  end
  for i = 0, r.CountTracks(0) - 1 do
    local tr = r.GetTrack(0, i)
    local _, name = r.GetTrackName(tr)
    if name == key then return tr, name end
  end
  return nil, key
end

local function normalize_wave(s)
  s = (s or ""):lower():match("^%s*(.-)%s*$") or ""
  if s == "cos" or s == "cosine" or s == "余弦" then
    return "cosine"
  end
  return "sine"
end

local function is_volume_envelope_name(name)
  if not name or name == "" then return false end
  local vol = r.LocalizeString and r.LocalizeString("Volume", "envname") or "Volume"
  return name == "Volume" or name == vol or name:find("Volume", 1, true) ~= nil
end

local function find_volume_envelope(track)
  local env = r.GetTrackEnvelopeByName(track, "Volume")
  if env then return env end

  local vol = r.LocalizeString and r.LocalizeString("Volume", "envname") or "Volume"
  env = r.GetTrackEnvelopeByName(track, vol)
  if env then return env end

  for i = 0, r.CountTrackEnvelopes(track) - 1 do
    env = r.GetTrackEnvelope(track, i)
    local ok, name = r.GetEnvelopeName(env, "")
    if ok and is_volume_envelope_name(name) then
      return env
    end
  end
  return nil
end

local function ensure_volume_envelope(track)
  local env = find_volume_envelope(track)
  if not env then
    local prev_sel = {}
    for i = 0, r.CountSelectedTracks(0) - 1 do
      prev_sel[#prev_sel + 1] = r.GetSelectedTrack(0, i)
    end
    r.SetOnlyTrackSelected(track)
    r.Main_OnCommand(40406, 0) -- Track: Toggle show volume envelope
    env = find_volume_envelope(track)
    r.Main_OnCommand(40297, 0)
    for _, tr in ipairs(prev_sel) do
      r.SetTrackSelected(tr, true)
    end
  end
  if not env then return nil end

  if r.SetEnvelopeInfo_Value then
    r.SetEnvelopeInfo_Value(env, "I_ACTIVE", 1)
    r.SetEnvelopeInfo_Value(env, "I_VISIBLE", 1)
  end
  return env
end

local function build_curve(points, max_db, min_db, wave)
  points = math.floor(clamp(parse_num(points, 33), 2, 512))
  max_db = parse_num(max_db, 1.0)
  min_db = parse_num(min_db, -1.0)
  if min_db > max_db then
    min_db, max_db = max_db, min_db
  end

  local mid = (max_db + min_db) / 2
  local amp = (max_db - min_db) / 2
  local values = {}
  local n = points - 1

  for i = 0, n do
    local phase = 2 * math.pi * (i / n)
    local factor = wave == "cosine" and math.cos(phase) or math.sin(phase)
    values[#values + 1] = mid + amp * factor
  end

  return values, points, max_db, min_db, wave
end

--- Volume 包络：dB 偏移 → 线性倍率(1.0=0dB) → fader scaling 时再 ScaleToEnvelopeMode
local function db_offset_to_envelope_value(env, db_offset)
  local linear = clamp(db_to_linear(db_offset), 1e-6, 4.0)
  if r.GetEnvelopeScalingMode(env) == 1 then
    return r.ScaleToEnvelopeMode(1, linear)
  end
  return linear
end

local function envelope_value_to_linear(env, stored)
  if r.GetEnvelopeScalingMode(env) == 1 then
    return r.ScaleFromEnvelopeMode(1, stored)
  end
  return stored
end

local function read_inserted_db_range(env)
  local count = r.CountEnvelopePoints(env)
  if count <= 0 then return nil, nil end
  local min_db, max_db = math.huge, -math.huge
  for i = 0, count - 1 do
    local ok, _, val = r.GetEnvelopePoint(env, i)
    if ok then
      local db = linear_to_db(envelope_value_to_linear(env, val))
      if db < min_db then min_db = db end
      if db > max_db then max_db = db end
    end
  end
  if min_db == math.huge then return nil, nil end
  return min_db, max_db
end

local function apply_envelope(track, total_sec, points, max_db, min_db, wave)
  if not track or total_sec <= 0 then
    return false, "无效轨道或时长"
  end

  max_db = parse_num(max_db, 1.0)
  min_db = parse_num(min_db, -1.0)
  if math.abs(max_db - min_db) < 0.001 then
    return false, string.format("最大与最小 dB 相同 (%+.2f)，包络会是平的", max_db)
  end

  local values, used_points, used_max, used_min, used_wave =
    build_curve(points, max_db, min_db, wave)

  local env = ensure_volume_envelope(track)
  if not env then return false, "找不到 Volume 包络" end

  local scaling = r.GetEnvelopeScalingMode(env)
  log(string.format("Volume 包络 scaling=%d（0=linear 1=fader）", scaling))

  r.DeleteEnvelopePointRange(env, -1e12, 1e12)

  local n = #values - 1
  for i, db in ipairs(values) do
    local t = ((i - 1) / n) * total_sec
    local val = db_offset_to_envelope_value(env, db)
    r.InsertEnvelopePoint(env, t, val, 0, 0, false, true)
  end
  r.Envelope_SortPoints(env)

  local got_min, got_max = read_inserted_db_range(env)
  if not got_min then
    return false, "未能写入包络点"
  end
  if got_min <= -140 or got_max <= -140 then
    return false, string.format(
      "写入异常（约 %+.1f ~ %+.1f dB），请 Undo 后重试",
      got_min, got_max
    )
  end
  if math.abs(got_max - got_min) < 0.05 then
    return false, string.format(
      "写入后起伏过小（约 %+.2f ~ %+.2f dB）",
      got_min, got_max
    )
  end

  log(string.format("验证 dB 范围: %+.2f ~ %+.2f", got_min, got_max))

  return true, used_points, used_max, used_min, used_wave, got_min, got_max
end

local function main()
  local sel = r.GetSelectedTrack(0, 0)
  local sel_hint = sel and track_name(sel) or "未选中"

  local ret, key = r.GetUserInputs(
    "音量包络 · 选轨",
    1,
    "0=选中 · 或层 id(1_rain) · 或轨号",
    sel_hint == "未选中" and "0" or sel_hint
  )
  if not ret then return end

  local track, label = resolve_track(key)
  if not track then
    r.ShowMessageBox("找不到轨道: " .. key, "asmr_vol_envelope", 0)
    return
  end
  label = track_name(track) or label

  ret, key = r.GetUserInputs(
    "音量包络 · " .. label,
    5,
    "时长h(0=工程),点数,最大+dB,最小-dB,波形(sine/cosine)",
    "0,33,1.0,-1.0,sine"
  )
  if not ret then return end

  local dur_h, points, max_db, min_db, wave_s =
    key:match("([^,]+),([^,]+),([^,]+),([^,]+),([^,]+)")

  dur_h = parse_num(dur_h, 0)
  points = parse_num(points, 33)
  max_db = parse_num(max_db, 1.0)
  min_db = parse_num(min_db, -1.0)
  local wave = normalize_wave(wave_s)

  local total_sec = dur_h > 0 and dur_h * 3600 or r.GetProjectLength(0)
  if total_sec <= 0 then total_sec = 3 * 3600 end

  r.Undo_BeginBlock()
  r.PreventUIRefresh(1)

  local ok, a, b, c, d, e, f = apply_envelope(track, total_sec, points, max_db, min_db, wave)

  r.PreventUIRefresh(-1)
  r.UpdateArrange()

  if not ok then
    r.Undo_EndBlock("Volume envelope (failed)", -1)
    r.ShowMessageBox(tostring(a), "asmr_vol_envelope", 0)
    return
  end

  r.Undo_EndBlock("Volume envelope " .. label, -1)

  local used_points, used_max, used_min, used_wave, got_min, got_max = a, b, c, d, e, f
  local wave_label = used_wave == "cosine" and "余弦" or "正弦"
  log(string.format(
    "%s · %s · %d pt · 目标 %+.1f/%+.1f dB · 实际 %+.2f/%+.2f dB · %.1fh",
    label, wave_label, used_points, used_max, used_min, got_min, got_max, total_sec / 3600
  ))
  r.ShowMessageBox(
    string.format(
      "%s\n波形: %s\n点数: %d\n目标: %+.1f ~ %+.1f dB\n实际: %+.2f ~ %+.2f dB\n时长: %.1f h",
      label, wave_label, used_points, used_min, used_max, got_min, got_max, total_sec / 3600
    ),
    "asmr_vol_envelope",
    0
  )
end

main()
