-- 长时音量包络 · 模拟自然界雨势/风的缓慢起伏（无限循环视频的时间感）
-- 由 asmr_apply_recipe.lua 调用

local M = {}

local function log(msg)
  reaper.ShowConsoleMsg("[vol_envelope] " .. msg .. "\n")
end

--- 确保轨有 Volume 包络并处于可播放状态（标准 API 无 InsertTrackEnvelope，用命令创建）
local function ensure_volume_envelope(track)
  local env = reaper.GetTrackEnvelopeByName(track, "Volume")
  if not env then
    env = reaper.GetTrackEnvelope(track, 0)
  end
  if not env then
    local prev_sel = {}
    for i = 0, reaper.CountSelectedTracks(0) - 1 do
      prev_sel[#prev_sel + 1] = reaper.GetSelectedTrack(0, i)
    end
    reaper.SetOnlyTrackSelected(track)
    -- 40406 = Track: Toggle show volume envelope（不存在时会创建）
    reaper.Main_OnCommand(40406, 0)
    env = reaper.GetTrackEnvelopeByName(track, "Volume")
    if not env then
      env = reaper.GetTrackEnvelope(track, 0)
    end
    reaper.Main_OnCommand(40297, 0) -- Unselect all tracks
    for _, tr in ipairs(prev_sel) do
      reaper.SetTrackSelected(tr, true)
    end
  end
  if not env then return nil end
  if reaper.SetEnvelopeInfo_Value then
    reaper.SetEnvelopeInfo_Value(env, "I_ACTIVE", 1)
    reaper.SetEnvelopeInfo_Value(env, "I_VISIBLE", 1)
  end
  return env
end

--- 单周期正弦波包络（整段时长一个波峰或波谷）
-- depth: 0.06~0.12 为宜；peak_at_center=true → 中段雨势略强，两端略弱
-- peak_at_center=false → 中段略弱（风小/雨歇），两端略强
function M.apply_single_wave(track, total_sec, depth, peak_at_center)
  if not track or total_sec <= 0 then return false end
  depth = math.max(0, math.min(0.2, depth or 0.08))
  local env = ensure_volume_envelope(track)
  if not env then return false end

  reaper.DeleteEnvelopePointRange(env, -1e12, 1e12)

  local scaling = reaper.GetEnvelopeScalingMode(env)
  local n = 33
  for i = 0, n do
    local t = (i / n) * total_sec
    local s = math.sin(math.pi * i / n)
    local mult
    if peak_at_center then
      mult = 1 - depth * (1 - s)
    else
      mult = 1 - depth * s
    end
    mult = math.max(0.5, math.min(1.5, mult))
    local val = reaper.ScaleToEnvelopeMode(scaling, mult)
    reaper.InsertEnvelopePoint(env, t, val, 2, 0, false, true)
  end
  reaper.Envelope_SortPoints(env)
  return true
end

function M.apply_layer_envelope(track, total_sec, spec)
  local ve = spec.vol_envelope
  if not ve then return false end
  local shape = ve.shape or "single_wave"
  local depth = ve.depth or 0.08
  local peak_at = ve.peak_at or "center"
  local peak_at_center = peak_at == "center"

  if shape == "single_wave" or shape == "breathe" then
    local ok = M.apply_single_wave(track, total_sec, depth, peak_at_center)
    if ok then
      log(string.format(
        "轨 %d %s · single_wave depth=%.2f peak_at=%s · %.0f min",
        spec.track or 0, spec.name or "", depth, peak_at, total_sec / 60
      ))
    end
    return ok
  end
  log("未知 vol_envelope.shape: " .. tostring(shape))
  return false
end

function M.apply_from_config(cfg, total_sec, paths_mod)
  local n = 0
  for _, spec in ipairs(cfg.loop_layers or {}) do
    if spec.vol_envelope then
      local tr
      if paths_mod and paths_mod.track_for_layer then
        tr = paths_mod.track_for_layer(spec)
      else
        tr = reaper.GetTrack(0, (spec.track or 1) - 1)
      end
      if tr and M.apply_layer_envelope(tr, total_sec, spec) then
        n = n + 1
      end
    end
  end
  return n
end

return M
