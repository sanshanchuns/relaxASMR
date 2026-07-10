-- @description Rain · 视频循环 + 音频层循环/稀疏（读 asmr_config.lua）
-- @version 1.0
-- @author relaxASMR

local r = reaper

local LOOP_TOLERANCE_SEC = 60
local MAX_ONESHOT_SEC = 600

local function log_add(log, fmt, ...)
  local s = string.format(fmt, ...)
  log[#log + 1] = s
  r.ShowConsoleMsg("[rain] " .. s .. "\n")
end

local function get_scripts_dir()
  local _, script_path = r.get_action_context()
  if script_path and script_path ~= "" then
    return script_path:match("^(.+)[\\/][^\\/]+$")
  end
  return nil
end

local function load_paths()
  local scripts_dir = get_scripts_dir()
  if not scripts_dir then return nil end
  local sep = package.config:sub(1, 1)
  local f = loadfile(scripts_dir .. sep .. "rain_paths.lua")
  if not f then return nil end
  return f()
end

local function scene_id_from_project()
  local _, name = r.GetProjectName(0, "")
  if name and name ~= "" then
    return name:gsub("%.rpp$", "")
  end
  return nil
end

local function load_config()
  local scripts_dir = get_scripts_dir()
  if not scripts_dir then return nil, "无法定位 scripts 目录" end
  local sep = package.config:sub(1, 1)
  local sid = scene_id_from_project()
  local cfg_path
  if sid and sid ~= "" then
    cfg_path = scripts_dir .. sep .. "scenes" .. sep .. sid .. ".lua"
    local f = loadfile(cfg_path)
    if f then return f(), cfg_path end
  end
  cfg_path = scripts_dir .. sep .. "asmr_config.lua"
  local f = loadfile(cfg_path)
  if not f then return nil, "找不到场景配方：" .. cfg_path end
  return f(), cfg_path
end

local function track_by_number(n)
  if n < 1 then return nil end
  return r.GetTrack(0, n - 1)
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

local function get_item_state_chunk(item)
  local a, b = r.GetSetItemState(item, "", false)
  if type(b) == "string" and b ~= "" then return b end
  if type(a) == "string" and a ~= "" then return a end
  return nil
end

local function get_source_filename(src)
  if not src then return nil end
  local a, b = r.GetMediaSourceFileName(src, "")
  if type(b) == "string" and b ~= "" then return b end
  if type(a) == "string" and a ~= "" then return a end
  return nil
end

local function get_oneshot_length(item, src, log, label)
  local src_len = r.GetMediaSourceLength(src, false)
  local display_len = r.GetMediaItemInfo_Value(item, "D_LENGTH")
  local loop_src = r.GetMediaItemInfo_Value(item, "B_LOOPSRC") == 1

  if not src_len or src_len <= 0 then
    return display_len
  end
  if not display_len or display_len <= 0 or display_len > MAX_ONESHOT_SEC or display_len > src_len * 1.5 then
    if display_len and display_len > src_len * 1.5 then
      log_add(log, "  [%s] item %.1fs ≠ 源 %.1fs → 用源时长", label, display_len, src_len)
    end
    return src_len
  end
  return display_len
end

local function get_track_template(track, repo_root, paths_mod, log, label)
  local n = r.CountTrackMediaItems(track)
  for i = 0, n - 1 do
    local item = r.GetTrackMediaItem(track, i)
    local take = r.GetActiveTake(item)
    if take then
      local src = r.GetMediaItemTake_Source(take)
      if src then
        local oneshot_len = get_oneshot_length(item, src, log, label)
        if oneshot_len and oneshot_len > 0 then
          local chunk = get_item_state_chunk(item)
          local fn = get_source_filename(src)
          local path = fn
          if fn and not fn:match("^[%a]:") and not fn:match("^/") and not fn:match("^\\\\") then
            path = paths_mod.resolve_asset(fn, repo_root)
          end
          if chunk or path then
            return { chunk = chunk, length = oneshot_len, path = path }
          end
        end
      end
    end
  end
  return nil
end

local function delete_track_items(track)
  local n = r.CountTrackMediaItems(track)
  for i = n - 1, 0, -1 do
    r.DeleteTrackMediaItem(track, r.GetTrackMediaItem(track, i))
  end
end

local function get_source_length(path, log, label)
  local src = r.PCM_Source_CreateFromFile(path)
  if not src then
    log_add(log, "  [%s] 无法打开: %s", label, path)
    return nil
  end
  local len = r.GetMediaSourceLength(src, false)
  r.PCM_Source_Destroy(src)
  return len
end

local function insert_oneshot(track, path, pos, item_len, fade_sec, log, label)
  local item = r.AddMediaItemToTrack(track)
  if not item then return false end
  local take = r.AddTakeToMediaItem(item)
  if not take then
    r.DeleteTrackMediaItem(track, item)
    return false
  end
  local src = r.PCM_Source_CreateFromFile(path)
  if not src then
    r.DeleteTrackMediaItem(track, item)
    return false
  end
  r.SetMediaItemTake_Source(take, src)
  if not item_len or item_len <= 0 then
    item_len = r.GetMediaSourceLength(src, false)
  end
  r.SetMediaItemInfo_Value(item, "D_POSITION", pos)
  r.SetMediaItemInfo_Value(item, "D_LENGTH", item_len)
  r.SetMediaItemInfo_Value(item, "B_LOOPSRC", 0)
  if fade_sec and fade_sec > 0 then
    r.SetMediaItemInfo_Value(item, "D_FADEINLEN", fade_sec)
    r.SetMediaItemInfo_Value(item, "D_FADEOUTLEN", fade_sec)
  end
  r.UpdateItemInProject(item)
  return true
end

local function insert_from_template(track, template, pos, fade_sec)
  local item = r.AddMediaItemToTrack(track)
  if not item then return false end
  if template.chunk then
    local ok = r.SetItemStateChunk(item, template.chunk, false)
    if not ok then
      r.DeleteTrackMediaItem(track, item)
      if template.path then
        return insert_oneshot(track, template.path, pos, template.length, fade_sec, {}, "")
      end
      return false
    end
  elseif template.path then
    r.DeleteTrackMediaItem(track, item)
    return insert_oneshot(track, template.path, pos, template.length, fade_sec, {}, "")
  else
    r.DeleteTrackMediaItem(track, item)
    return false
  end
  r.SetMediaItemInfo_Value(item, "D_POSITION", pos)
  r.SetMediaItemInfo_Value(item, "D_LENGTH", template.length)
  r.SetMediaItemInfo_Value(item, "B_LOOPSRC", 0)
  if fade_sec and fade_sec > 0 then
    r.SetMediaItemInfo_Value(item, "D_FADEINLEN", fade_sec)
    r.SetMediaItemInfo_Value(item, "D_FADEOUTLEN", fade_sec)
  end
  r.UpdateItemInProject(item)
  return true
end

local function generate_jitter_times(total_sec, item_len, min_gap, max_gap, log, label)
  local times = {}
  if not item_len or item_len <= 0 or item_len >= total_sec then return times end
  math.randomseed(os.time() + math.floor(min_gap or 0) + math.floor(item_len * 1000))
  local t = min_gap * (0.5 + math.random() * 0.5)
  while t + item_len < total_sec do
    times[#times + 1] = t
    t = t + min_gap + math.random() * (max_gap - min_gap)
  end
  log_add(log, "  [%s] 计划 %d 个事件 · item=%.2fs · 间隔 %.0f–%.0f s", label, #times, item_len, min_gap, max_gap)
  return times
end

local function run_video_loop(cfg, total_sec, log)
  if not cfg.video then return end
  local label = string.format("轨%d 视频", cfg.video.track or 1)
  local tr = track_by_number(cfg.video.track or 1)
  if not tr then
    log_add(log, "✗ %s 不存在", label)
    return
  end
  if track_already_looped(tr, total_sec) then
    log_add(log, "○ 跳过 %s · 已循环", label)
    return
  end
  local n = loop_track_items(tr, total_sec)
  log_add(log, "✓ %s · %d item → %.1f h", label, n, total_sec / 3600)
end

local function run_loop_layers(cfg, total_sec, log)
  log_add(log, "── 循环音频层 ──")
  for _, spec in ipairs(cfg.loop_layers or {}) do
    local label = string.format("轨%d %s", spec.track, spec.name or spec.id or "")
    local tr = track_by_number(spec.track)
    if not tr then
      log_add(log, "✗ %s 不存在", label)
    elseif track_already_looped(tr, total_sec) then
      log_add(log, "○ 跳过 %s · 已循环", label)
    else
      local n = loop_track_items(tr, total_sec)
      log_add(log, "✓ %s · %d item → %.1f h", label, n, total_sec / 3600)
    end
  end
end

local function run_scatter_layers(cfg, repo_root, paths_mod, total_sec, log)
  log_add(log, "── 稀疏事件层 ──")
  for _, spec in ipairs(cfg.scatter_layers or {}) do
    local label = string.format("轨%d %s", spec.track, spec.name or spec.id or "")
    local tr = track_by_number(spec.track)
    if not tr then
      log_add(log, "✗ %s 不存在", label)
    else
      local template = get_track_template(tr, repo_root, paths_mod, log, label)
      local config_path = nil
      if spec.paths and spec.paths[1] then
        config_path = paths_mod.resolve_asset(spec.paths[1], repo_root)
      end
      local wav = (template and template.path) or config_path
      local item_len = template and template.length or get_source_length(wav, log, label)

      if not item_len or item_len <= 0 or not wav then
        log_add(log, "✗ %s · 无可用 sample", label)
      else
        local saved = template
        if spec.clear_existing then
          delete_track_items(tr)
        end
        local min_g = (spec.min_gap_min or 5) * 60
        local max_g = (spec.max_gap_min or 15) * 60
        if max_g < min_g then max_g = min_g end
        local times = generate_jitter_times(total_sec, item_len, min_g, max_g, log, label)
        local placed = 0
        for _, pos in ipairs(times) do
          if saved and insert_from_template(tr, saved, pos, cfg.fade_sec) then
            placed = placed + 1
          elseif wav and insert_oneshot(tr, wav, pos, item_len, cfg.fade_sec, log, label) then
            placed = placed + 1
          end
        end
        log_add(log, "✓ %s · 放置 %d / %d", label, placed, #times)
      end
    end
  end
end

local function main()
  r.ShowConsoleMsg("\n[rain] ========== rain_setup_project ==========\n")
  local paths_mod = load_paths()
  if not paths_mod then
    r.ShowMessageBox("找不到 rain_paths.lua", "rain_setup", 0)
    return
  end
  local cfg, cfg_path = load_config()
  if not cfg then
    r.ShowMessageBox(cfg_path, "rain_setup", 0)
    return
  end
  local repo_root = paths_mod.repo_root()
  if not repo_root then
    r.ShowMessageBox("无法定位仓库根目录", "rain_setup", 0)
    return
  end

  local hours = cfg.duration_hours or 3
  local total_sec = hours * 3600

  local choice = r.ShowMessageBox(
    string.format(
      "%s\n时长: %.0f h\n循环层 %d · 稀疏层 %d\n\n【确定】全部\n【否】仅循环\n【取消】仅稀疏",
      cfg.project_name or cfg.scene_id or "Rain",
      hours,
      #(cfg.loop_layers or {}),
      #(cfg.scatter_layers or {})
    ),
    "rain_setup_project",
    3
  )
  local all = choice == 6
  local loop_only = choice == 7
  local scatter_only = choice == 2
  if not all and not loop_only and not scatter_only then return end

  r.Undo_BeginBlock()
  r.PreventUIRefresh(1)
  local log = {}
  log_add(log, "配置: %s", cfg_path)
  set_project_length(total_sec)

  if all or loop_only then
    run_video_loop(cfg, total_sec, log)
    run_loop_layers(cfg, total_sec, log)
  end
  if all or scatter_only then
    run_scatter_layers(cfg, repo_root, paths_mod, total_sec, log)
  end

  r.PreventUIRefresh(-1)
  r.UpdateArrange()
  r.Undo_EndBlock("Rain setup", -1)
  log_add(log, "========== 完成 ==========")
  r.ShowMessageBox(table.concat(log, "\n"), "rain_setup · 完成", 0)
end

main()
