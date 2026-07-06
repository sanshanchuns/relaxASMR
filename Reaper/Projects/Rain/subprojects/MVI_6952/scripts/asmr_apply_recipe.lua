-- @description ASMR · 按 asmr_config 铺循环层
-- @version 2.1
-- @author relaxASMR
-- @about
--   读取工程目录 scripts/asmr_config.lua
--   循环：video + loop_layers + 1_rain 音量包络
--   稀疏散布请逐轨运行 asmr_scatter_track.lua（手动填间隔/随机度）

local r = reaper

local LOOP_TOLERANCE = 60

local function log(msg)
  r.ShowConsoleMsg("[apply_recipe] " .. msg .. "\n")
end

local function script_dir()
  local _, script_path = r.get_action_context()
  return script_path:match("^(.+)[\\/][^\\/]+$")
end

local function load_paths()
  local f = loadfile(script_dir() .. package.config:sub(1, 1) .. "asmr_paths.lua")
  if not f then return nil end
  return f()
end

local function load_vol_envelope()
  local f = loadfile(script_dir() .. package.config:sub(1, 1) .. "asmr_vol_envelope.lua")
  if not f then return nil end
  return f()
end

local function track_by_number(n)
  return r.GetTrack(0, n - 1)
end

local function track_for_spec(spec, paths_mod)
  if paths_mod and paths_mod.track_for_layer then
    return paths_mod.track_for_layer(spec)
  end
  return track_by_number(spec.track)
end

local function track_looped(track, total_sec)
  local n = r.CountTrackMediaItems(track)
  for i = 0, n - 1 do
    local item = r.GetTrackMediaItem(track, i)
    if r.GetMediaItemInfo_Value(item, "B_LOOPSRC") == 1 then
      local pos = r.GetMediaItemInfo_Value(item, "D_POSITION")
      local len = r.GetMediaItemInfo_Value(item, "D_LENGTH")
      if len >= (total_sec - pos) - LOOP_TOLERANCE then
        return true
      end
    end
  end
  return false
end

local function loop_track(track, total_sec)
  local n = r.CountTrackMediaItems(track)
  for i = 0, n - 1 do
    local item = r.GetTrackMediaItem(track, i)
    if r.GetMediaItemInfo_Value(item, "B_LOOPSRC") ~= 1 then goto continue end
    local pos = r.GetMediaItemInfo_Value(item, "D_POSITION")
    local len = total_sec - pos
    if len > 0 then r.SetMediaItemInfo_Value(item, "D_LENGTH", len) end
    ::continue::
  end
end

local function main()
  local paths_mod = load_paths()
  if not paths_mod then
    r.ShowMessageBox("找不到 asmr_paths.lua", "asmr_apply_recipe", 0)
    return
  end
  local cfg, err = paths_mod.load_asmr_config()
  if not cfg then
    r.ShowMessageBox(err, "asmr_apply_recipe", 0)
    return
  end

  local hours = cfg.duration_hours or 3
  local total_sec = hours * 3600

  local choice = r.ShowMessageBox(
    string.format(
      "%s\n时长 %.0f h\n【确定】循环 + 1_rain 音量包络\n【否】仅循环\n【取消】放弃",
      cfg.project_name or cfg.scene_id or "ASMR",
      hours
    ),
    "asmr_apply_recipe",
    3
  )
  local with_envelope, loop_only = choice == 6, choice == 7
  if not with_envelope and not loop_only then return end

  r.Undo_BeginBlock()
  r.PreventUIRefresh(1)
  r.GetSetProjectInfo(0, "PROJECT_LENGTH", total_sec, true)

  if cfg.video and cfg.video.track and not cfg.video.render_only then
    local tr = track_by_number(cfg.video.track)
    if tr and not track_looped(tr, total_sec) then
      loop_track(tr, total_sec)
      log("视频轨已循环至 " .. hours .. " h")
    end
  end
  for _, spec in ipairs(cfg.loop_layers or {}) do
    local tr = track_for_spec(spec, paths_mod)
    if tr and not track_looped(tr, total_sec) then
      loop_track(tr, total_sec)
      log("循环轨 " .. spec.track .. " " .. (spec.name or ""))
    end
  end
  if with_envelope then
    local vol_mod = load_vol_envelope()
    if vol_mod then
      local n = vol_mod.apply_from_config(cfg, total_sec, paths_mod)
      if n > 0 then log("音量包络 " .. n .. " 轨") end
    end
  end

  r.PreventUIRefresh(-1)
  r.UpdateArrange()
  r.Undo_EndBlock("Apply ASMR recipe", -1)
  r.ShowMessageBox(
    "循环层已应用 · " .. hours .. " h\n稀疏层请逐轨运行 asmr_scatter_track.lua",
    "asmr_apply_recipe",
    0
  )
end

main()
