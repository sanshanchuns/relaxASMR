-- @description ASMR · 循环指定轨道 + 随机 one-shot（读同目录 asmr_config.lua）
-- @version 1.7
-- @author relaxASMR
-- @about
--   ForestRainNight/scripts/
--     asmr_config.lua
--     asmr_setup_project.lua
--   日志：View → Reaper console（或 ~ 键）

local r = reaper

local LOOP_TOLERANCE_SEC = 60
local MAX_ONESHOT_SEC = 120 -- 超过则视为 item 被误拉长，改用源文件时长

local function log_add(log, fmt, ...)
  local s = string.format(fmt, ...)
  log[#log + 1] = s
  r.ShowConsoleMsg("[asmr] " .. s .. "\n")
end

local function get_project_dir()
  local proj_path = r.GetProjectPath("")
  if proj_path and proj_path ~= "" then
    return proj_path
  end
  local _, script_path = r.get_action_context()
  if not script_path or script_path == "" then
    return nil
  end
  local root = script_path:match("^(.+)[\\/]scripts[\\/]")
  if root then return root end
  return script_path:match("^(.+)[\\/][^\\/]+$")
end

local function get_scripts_dir()
  local _, script_path = r.get_action_context()
  if script_path and script_path ~= "" then
    return script_path:match("^(.+)[\\/][^\\/]+$")
  end
  local project_dir = get_project_dir()
  if not project_dir then return nil end
  return project_dir .. package.config:sub(1, 1) .. "scripts"
end

local function load_config()
  local scripts_dir = get_scripts_dir()
  if not scripts_dir then
    return nil, "无法定位 scripts 目录。请先打开并保存 ForestRainNight.rpp"
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

local function resolve_media_path(path, proj_path)
  if not path or path == "" then return nil end
  if path:match("^[%a]:\\") or path:match("^/") or path:match("^\\\\") then
    return path
  end
  if not proj_path or proj_path == "" then
    return path
  end
  local sep = package.config:sub(1, 1)
  return proj_path .. sep .. path:gsub("/", sep)
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

local function get_oneshot_length(item, src, log, track_label)
  local src_len = r.GetMediaSourceLength(src, false)
  local display_len = r.GetMediaItemInfo_Value(item, "D_LENGTH")
  local loop_src = r.GetMediaItemInfo_Value(item, "B_LOOPSRC") == 1

  if not src_len or src_len <= 0 then
    log_add(log, "  [%s] 无源时长，用 item 显示长度 %.2fs", track_label, display_len or 0)
    return display_len
  end

  if not display_len or display_len <= 0 or display_len > MAX_ONESHOT_SEC or display_len > src_len * 1.5 then
    if display_len and display_len > src_len * 1.5 then
      log_add(
        log,
        "  [%s] item 显示 %.1fs ≠ 源 %.2fs（loop=%s）→ 随机用源时长",
        track_label,
        display_len,
        src_len,
        loop_src and "是" or "否"
      )
    end
    return src_len
  end

  log_add(log, "  [%s] one-shot 时长 %.2fs（源 %.2fs）", track_label, display_len, src_len)
  return display_len
end

local function get_track_template(track, proj_path, log, track_label)
  local n = r.CountTrackMediaItems(track)
  log_add(log, "  [%s] 扫描轨道 item 数 = %d", track_label, n)

  for i = 0, n - 1 do
    local item = r.GetTrackMediaItem(track, i)
    local take = r.GetActiveTake(item)
    if not take then
      log_add(log, "  [%s] item[%d] 无 active take，跳过", track_label, i)
    else
      local src = r.GetMediaItemTake_Source(take)
      if not src then
        log_add(log, "  [%s] item[%d] 无 source（空占位？），跳过", track_label, i)
      else
        local oneshot_len = get_oneshot_length(item, src, log, track_label)
        if not oneshot_len or oneshot_len <= 0 then
          log_add(log, "  [%s] item[%d] 时长无效，跳过", track_label, i)
        else
          local chunk = get_item_state_chunk(item)
          local fn = get_source_filename(src)
          local path = fn and resolve_media_path(fn, proj_path) or nil
          log_add(
            log,
            "  [%s] item[%d] 模板 OK · chunk=%s · path=%s",
            track_label,
            i,
            chunk and "有" or "无",
            path or "(无)"
          )
          if chunk or path then
            return {
              chunk = chunk,
              length = oneshot_len,
              path = path,
            }
          end
        end
      end
    end
  end

  log_add(log, "  [%s] 未找到可用 template", track_label)
  return nil
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

local function get_source_length(path, log, label)
  if not path then return nil end
  local src = r.PCM_Source_CreateFromFile(path)
  if not src then
    log_add(log, "  [%s] PCM_Source_CreateFromFile 失败: %s", label, path)
    return nil
  end
  local len = r.GetMediaSourceLength(src, false)
  r.PCM_Source_Destroy(src)
  log_add(log, "  [%s] 文件时长 %.2fs · %s", label, len or 0, path)
  return len
end

local function delete_track_items(track)
  local n = r.CountTrackMediaItems(track)
  for i = n - 1, 0, -1 do
    r.DeleteTrackMediaItem(track, r.GetTrackMediaItem(track, i))
  end
end

local function insert_oneshot(track, path, pos, item_len, fade_sec, log, label)
  local item = r.AddMediaItemToTrack(track)
  if not item then
    log_add(log, "  [%s] AddMediaItemToTrack 失败 @ %.1fs", label, pos)
    return false
  end

  local take = r.AddTakeToMediaItem(item)
  if not take then
    r.DeleteTrackMediaItem(track, item)
    log_add(log, "  [%s] AddTakeToMediaItem 失败 @ %.1fs", label, pos)
    return false
  end

  local src = r.PCM_Source_CreateFromFile(path)
  if not src then
    r.DeleteTrackMediaItem(track, item)
    log_add(log, "  [%s] 插入失败 @ %.1fs · 无法打开: %s", label, pos, path)
    return false
  end

  r.SetMediaItemTake_Source(take, src)
  r.SetMediaItemTakeInfo_Value(take, "D_STARTOFFS", 0)
  r.SetMediaItemTakeInfo_Value(take, "D_PLAYRATE", 1)

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

local function insert_from_template(track, template, pos, fade_sec, log, label)
  local item = r.AddMediaItemToTrack(track)
  if not item then
    log_add(log, "  [%s] AddMediaItemToTrack 失败 @ %.1fs", label, pos)
    return false
  end

  local ok_chunk = false
  if template.chunk then
    ok_chunk = r.SetItemStateChunk(item, template.chunk, false)
    if not ok_chunk then
      log_add(log, "  [%s] SetItemStateChunk 失败 @ %.1fs → 尝试文件路径", label, pos)
      r.DeleteTrackMediaItem(track, item)
      if template.path then
        return insert_oneshot(track, template.path, pos, template.length, fade_sec, log, label)
      end
      return false
    end
  elseif template.path then
    r.DeleteTrackMediaItem(track, item)
    return insert_oneshot(track, template.path, pos, template.length, fade_sec, log, label)
  else
    r.DeleteTrackMediaItem(track, item)
    log_add(log, "  [%s] 无 chunk 且无 path @ %.1fs", label, pos)
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
  if not item_len or item_len <= 0 then
    log_add(log, "  [%s] 无法生成时间点：item_len 无效", label)
    return times
  end
  if item_len >= total_sec then
    log_add(
      log,
      "  [%s] 无法生成时间点：item_len %.1fs >= 工程 %.1fs",
      label,
      item_len,
      total_sec
    )
    return times
  end

  math.randomseed(os.time() + math.floor(min_gap or 0) + math.floor(item_len * 1000))
  local t = min_gap * (0.5 + math.random() * 0.5)
  while t + item_len < total_sec do
    times[#times + 1] = t
    local gap = min_gap + math.random() * (max_gap - min_gap)
    t = t + gap
  end

  log_add(
    log,
    "  [%s] 时间点 %d 个 · item_len=%.2fs · 间隔 %d–%d s · 首点 %.0fs",
    label,
    #times,
    item_len,
    min_gap,
    max_gap,
    times[1] or -1
  )
  return times
end

local function run_loop(cfg, total_sec, log)
  log_add(log, "── 循环轨 2–4 ──")
  for _, spec in ipairs(cfg.loop_tracks or {}) do
    local label = string.format("轨%d", spec.track)
    local tr = track_by_number(spec.track)
    if not tr then
      log_add(log, "✗ 循环 %s 不存在: %s", label, spec.name or "")
    elseif track_already_looped(tr, total_sec) then
      log_add(log, "○ 跳过 %s %s · 已循环至 %.1f h", label, spec.name or "", total_sec / 3600)
    else
      log_add(log, "→ 处理 %s %s", label, spec.name or "")
      local n = loop_track_items(tr, total_sec)
      log_add(log, "✓ 循环 %s %s · %d 个 item → %.1f h", label, spec.name or "", n, total_sec / 3600)
    end
  end
end

local function run_random(cfg, proj_path, total_sec, log)
  log_add(log, "── 随机轨 5–7 ──")
  for _, spec in ipairs(cfg.random_tracks or {}) do
    local label = string.format("轨%d", spec.track)
    log_add(log, "→ 随机 %s %s", label, spec.name or "")

    local tr = track_by_number(spec.track)
    if not tr then
      log_add(log, "✗ %s 轨道不存在", label)
    else
      local _, track_name = r.GetTrackName(tr)
      log_add(log, "  [%s] Reaper 轨名: %s", label, track_name or "")

      local template = get_track_template(tr, proj_path, log, label)
      local config_wav = resolve_media_path(spec.wav, proj_path)
      local wav = (template and template.path) or config_wav
      local item_len

      if template then
        item_len = template.length
      elseif config_wav then
        log_add(log, "  [%s] 轨道上无 template，用配置路径", label)
        item_len = get_source_length(config_wav, log, label)
      end

      local can_insert = item_len and item_len > 0 and (template or wav)
      if not can_insert then
        log_add(log, "✗ %s %s · 无可用 sample（请拖入 WAV 或检查配置）", label, spec.name or "")
      else
        local saved_template = template
        if spec.clear_existing then
          local n_before = r.CountTrackMediaItems(tr)
          delete_track_items(tr)
          log_add(log, "  [%s] clear_existing · 删除 %d 个 item", label, n_before)
        end

        local min_g = (spec.min_gap_min or 8) * 60
        local max_g = (spec.max_gap_min or 18) * 60
        if max_g < min_g then max_g = min_g end

        local times = generate_jitter_times(total_sec, item_len, min_g, max_g, log, label)
        local placed = 0
        local failed = 0
        local use_chunk = saved_template and saved_template.chunk
        local method = use_chunk and "chunk" or "file"

        log_add(log, "  [%s] 开始插入 · 方式=%s · 目标=%d", label, method, #times)

        for i, pos in ipairs(times) do
          local ok
          if saved_template then
            ok = insert_from_template(tr, saved_template, pos, cfg.fade_sec, log, label)
          elseif wav then
            ok = insert_oneshot(tr, wav, pos, item_len, cfg.fade_sec, log, label)
          else
            ok = false
          end
          if ok then
            placed = placed + 1
          else
            failed = failed + 1
            if failed <= 3 then
              log_add(log, "  [%s] 插入失败 #%d @ %.1fs", label, i, pos)
            end
          end
        end

        if failed > 3 then
          log_add(log, "  [%s] … 另有 %d 次插入失败", label, failed - 3)
        end

        local src_note = use_chunk and "复制轨道 sample" or (wav or "?")
        if placed > 0 then
          log_add(
            log,
            "✓ 随机 %s %s · %d 次 · 间隔 %d–%d min%s · %s",
            label,
            spec.name or "",
            placed,
            spec.min_gap_min or 8,
            spec.max_gap_min or 18,
            failed > 0 and string.format(" · 失败 %d", failed) or "",
            src_note
          )
        else
          log_add(
            log,
            "✗ 随机 %s %s · 放置 0 个 · 计划 %d · 失败 %d · %s",
            label,
            spec.name or "",
            #times,
            failed,
            src_note
          )
        end
      end
    end
  end
end

local function main()
  r.ShowConsoleMsg("\n[asmr] ========== asmr_setup_project v1.7 ==========\n")

  local cfg, cfg_path_or_err = load_config()
  if not cfg then
    r.ShowMessageBox(cfg_path_or_err, "asmr_setup_project", 0)
    return
  end

  local hours = cfg.duration_hours or 8
  local total_sec = hours * 3600

  local choice = r.ShowMessageBox(
    string.format(
      "工程配置: %s\n时长: %.0f 小时\n循环轨 2–4: %d 条 · 随机轨 5–7: %d 条\n\n【确定】= 循环 + 随机（推荐）\n【否】= 仅循环 2–4\n【取消】= 仅随机 5–7",
      cfg.project_name or "ASMR",
      hours,
      #(cfg.loop_tracks or {}),
      #(cfg.random_tracks or {})
    ),
    "asmr_setup_project",
    3
  )

  local mode_all = (choice == 6)
  local mode_loop_only = (choice == 7)
  local mode_random_only = (choice == 2)
  if not mode_all and not mode_loop_only and not mode_random_only then
    r.ShowConsoleMsg(string.format("[asmr] 用户取消（choice=%s）\n", tostring(choice)))
    return
  end

  r.Undo_BeginBlock()
  r.PreventUIRefresh(1)

  local log = {}
  log_add(log, "配置: %s", cfg_path_or_err or "")
  log_add(log, "工程目录: %s", get_project_dir() or "(未保存)")
  log_add(log, "PROJECT_LENGTH = %.0f h (%.0f s)", hours, total_sec)
  log_add(
    log,
    "模式: %s (choice=%d)",
    mode_loop_only and "仅循环" or (mode_random_only and "仅随机" or "循环+随机"),
    choice
  )

  set_project_length(total_sec)
  log_add(log, "已设置工程长度")

  local proj_path = get_project_dir()
  if (mode_all or mode_random_only) and not proj_path then
    r.PreventUIRefresh(-1)
    r.Undo_EndBlock("ASMR setup loop + random", -1)
    r.ShowMessageBox(
      "无法定位工程目录，随机轨需要相对路径。\n请先保存 ForestRainNight.rpp（Ctrl+S）后再运行。",
      "asmr_setup_project",
      0
    )
    return
  end

  if mode_all or mode_loop_only then
    run_loop(cfg, total_sec, log)
  end
  if mode_all or mode_random_only then
    run_random(cfg, proj_path, total_sec, log)
  end

  r.PreventUIRefresh(-1)
  r.UpdateArrange()
  r.Undo_EndBlock("ASMR setup loop + random", -1)

  log_add(log, "========== 完成 ==========")
  r.ShowMessageBox(table.concat(log, "\n"), "asmr_setup_project · 完成", 0)
end

main()
