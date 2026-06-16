-- @description StreamHeal · 循环指定轨道至工程全长（读同目录 asmr_config.lua）
-- @version 1.0
-- @author relaxASMR

local r = reaper

local LOOP_TOLERANCE_SEC = 60

local function log_add(log, fmt, ...)
  local s = string.format(fmt, ...)
  log[#log + 1] = s
  r.ShowConsoleMsg("[streamheal] " .. s .. "\n")
end

local function get_scripts_dir()
  local _, script_path = r.get_action_context()
  if script_path and script_path ~= "" then
    return script_path:match("^(.+)[\\/][^\\/]+$")
  end
  local proj_path = r.GetProjectPath("")
  if proj_path and proj_path ~= "" then
    return proj_path .. package.config:sub(1, 1) .. "scripts"
  end
  return nil
end

local function load_config()
  local scripts_dir = get_scripts_dir()
  if not scripts_dir then
    return nil, "无法定位 scripts 目录。请先打开并保存 StreamHeal.rpp"
  end
  local sep = package.config:sub(1, 1)
  local cfg_path = scripts_dir .. sep .. "asmr_config.lua"
  local f = loadfile(cfg_path)
  if not f then
    return nil, "找不到配置：\n" .. cfg_path
  end
  return f(), cfg_path
end

local function track_by_number(track_num_1based)
  local idx = track_num_1based - 1
  if idx < 0 then return nil end
  return r.GetTrack(0, idx)
end

local function set_project_length(seconds)
  r.GetSetProjectInfo(0, "PROJECT_LENGTH", seconds, true)
end

local function track_already_looped(track, total_sec)
  local n = r.CountTrackMediaItems(track)
  if n == 0 then return false end
  for i = 0, n - 1 do
    local item = r.GetTrackMediaItem(track, i)
    if r.GetMediaItemInfo_Value(item, "B_LOOPSRC") == 1 then
      local pos = r.GetMediaItemInfo_Value(item, "D_POSITION")
      local len = r.GetMediaItemInfo_Value(item, "D_LENGTH")
      if len >= (total_sec - pos) - LOOP_TOLERANCE_SEC then
        return true
      end
    end
  end
  return false
end

local function loop_track_items(track, end_time)
  local n = r.CountTrackMediaItems(track)
  if n == 0 then return 0 end
  local done = 0
  for i = 0, n - 1 do
    local item = r.GetTrackMediaItem(track, i)
    r.SetMediaItemInfo_Value(item, "B_LOOPSRC", 1)
    local pos = r.GetMediaItemInfo_Value(item, "D_POSITION")
    local len = end_time - pos
    if len > 0 then
      r.SetMediaItemInfo_Value(item, "D_LENGTH", len)
      done = done + 1
    end
  end
  return done
end

local function main()
  r.ShowConsoleMsg("\n[streamheal] ========== setup_project v1.0 ==========\n")

  local cfg, cfg_path_or_err = load_config()
  if not cfg then
    r.ShowMessageBox(cfg_path_or_err, "StreamHeal setup", 0)
    return
  end

  local hours = cfg.duration_hours or 3
  local total_sec = hours * 3600
  local n_loop = #(cfg.loop_tracks or {})

  local choice = r.ShowMessageBox(
    string.format(
      "工程: %s\n时长: %.0f 小时\n循环轨: %d 条\n\n确定 = 设置工程长度并循环所有轨",
      cfg.project_name or "StreamHeal",
      hours,
      n_loop
    ),
    "StreamHeal setup",
    1
  )
  if choice ~= 1 then
    r.ShowConsoleMsg("[streamheal] 用户取消\n")
    return
  end

  r.Undo_BeginBlock()
  r.PreventUIRefresh(1)

  local log = {}
  log_add(log, "配置: %s", cfg_path_or_err or "")
  log_add(log, "PROJECT_LENGTH = %.0f h (%.0f s)", hours, total_sec)
  set_project_length(total_sec)

  for _, spec in ipairs(cfg.loop_tracks or {}) do
    local label = string.format("轨%d", spec.track)
    local tr = track_by_number(spec.track)
    if not tr then
      log_add(log, "✗ %s 不存在: %s", label, spec.name or "")
    elseif track_already_looped(tr, total_sec) then
      log_add(log, "○ 跳过 %s %s · 已循环", label, spec.name or "")
    else
      local n = loop_track_items(tr, total_sec)
      log_add(log, "✓ 循环 %s %s · %d 个 item → %.1f h", label, spec.name or "", n, hours)
    end
  end

  r.PreventUIRefresh(-1)
  r.UpdateArrange()
  r.Undo_EndBlock("StreamHeal loop setup", -1)

  log_add(log, "========== 完成 ==========")
  r.ShowMessageBox(table.concat(log, "\n"), "StreamHeal setup · 完成", 0)
end

main()
