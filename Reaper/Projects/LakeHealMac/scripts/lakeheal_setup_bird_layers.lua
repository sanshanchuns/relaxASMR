-- @description LakeHealMac · 铺满鸟层轨 3–5 至 3h（轨 1/2 不动）
-- @version 3.0
-- @author relaxASMR
-- @about
--   按组随机 · 每组：轨3×1 · 轨4×4 · 轨5×1
--   轨3/5 组内随机落点 · 两者时间不重叠 · 组间 gap 随机
--   配置：同目录 asmr_config.lua

local r = reaper

local function log_add(log, fmt, ...)
  local s = string.format(fmt, ...)
  log[#log + 1] = s
  r.ShowConsoleMsg("[lakeheal] " .. s .. "\n")
end

local function get_project_dir()
  local proj_path = r.GetProjectPath("")
  if proj_path and proj_path ~= "" then return proj_path end
  local _, script_path = r.get_action_context()
  if not script_path or script_path == "" then return nil end
  return script_path:match("^(.+)[\\/]scripts[\\/]")
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
    return nil, "无法定位 scripts 目录。请先打开并保存 LakeHealMac.RPP"
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
  return r.GetTrack(0, track_num_1based - 1)
end

local function resolve_media_path(path, proj_path)
  if not path or path == "" then return nil end
  if path:match("^[%a]:\\") or path:match("^/") or path:match("^\\\\") then
    return path
  end
  if not proj_path or proj_path == "" then return path end
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

local function get_track_template(track, proj_path, log, label)
  local n = r.CountTrackMediaItems(track)
  if n == 0 then
    log_add(log, "  [%s] 轨道无 item", label)
    return nil
  end

  for i = 0, n - 1 do
    local item = r.GetTrackMediaItem(track, i)
    local take = r.GetActiveTake(item)
    if take then
      local src = r.GetMediaItemTake_Source(take)
      if src then
        local src_len = r.GetMediaSourceLength(src, false)
        local display_len = r.GetMediaItemInfo_Value(item, "D_LENGTH")
        local item_len = display_len
        if src_len and src_len > 0 and (not display_len or display_len <= 0 or display_len > src_len * 1.5) then
          item_len = src_len
        end
        local chunk = get_item_state_chunk(item)
        local fn = get_source_filename(src)
        local path = fn and resolve_media_path(fn, proj_path) or nil
        if chunk or path then
          log_add(log, "  [%s] 模板 len=%.2fs", label, item_len)
          return { chunk = chunk, length = item_len, path = path, loop_src = true }
        end
      end
    end
  end

  return nil
end

local function get_fill_length(cfg)
  return (cfg.duration_hours or 3) * 3600
end

local function delete_track_items(track)
  local n = r.CountTrackMediaItems(track)
  for i = n - 1, 0, -1 do
    r.DeleteTrackMediaItem(track, r.GetTrackMediaItem(track, i))
  end
end

local function insert_from_template(track, template, pos, fade_sec)
  local item = r.AddMediaItemToTrack(track)
  if not item then return false end

  local ok = false
  if template.chunk then
    ok = r.SetItemStateChunk(item, template.chunk, false)
    if not ok and template.path then
      r.DeleteTrackMediaItem(track, item)
      item = r.AddMediaItemToTrack(track)
      if not item then return false end
      local take = r.AddTakeToMediaItem(item)
      if not take then
        r.DeleteTrackMediaItem(track, item)
        return false
      end
      local src = r.PCM_Source_CreateFromFile(template.path)
      if not src then
        r.DeleteTrackMediaItem(track, item)
        return false
      end
      r.SetMediaItemTake_Source(take, src)
      ok = true
    end
  elseif template.path then
    local take = r.AddTakeToMediaItem(item)
    if not take then
      r.DeleteTrackMediaItem(track, item)
      return false
    end
    local src = r.PCM_Source_CreateFromFile(template.path)
    if not src then
      r.DeleteTrackMediaItem(track, item)
      return false
    end
    r.SetMediaItemTake_Source(take, src)
    ok = true
  end

  if not ok then
    r.DeleteTrackMediaItem(track, item)
    return false
  end

  r.SetMediaItemInfo_Value(item, "D_POSITION", pos)
  r.SetMediaItemInfo_Value(item, "D_LENGTH", template.length)
  if template.loop_src then
    r.SetMediaItemInfo_Value(item, "B_LOOPSRC", 1)
  end
  if fade_sec and fade_sec > 0 then
    r.SetMediaItemInfo_Value(item, "D_FADEINLEN", fade_sec)
    r.SetMediaItemInfo_Value(item, "D_FADEOUTLEN", fade_sec)
  end
  r.UpdateItemInProject(item)
  return true
end

local function ranges_overlap(a0, a1, b0, b1)
  return not (a1 <= b0 or b1 <= a0)
end

-- 在 [w0, w1-len] 内均匀随机
local function random_pos_in(w0, w1, len)
  local span = w1 - len - w0
  if span <= 0 then return nil end
  return w0 + math.random() * span
end

-- 轨4 定组框 · 轨3/5 组内随机 · 两者时间不重叠
local function place_t3_t5(window_start, window_end, len3, len5, max_tries)
  max_tries = max_tries or 64

  for _ = 1, max_tries do
    local t3 = random_pos_in(window_start, window_end, len3)
    if t3 then
      local t3_end = t3 + len3
      local left_w1 = t3 - len5
      local right_w0 = t3_end

      local pick_left = left_w1 >= window_start
      local pick_right = right_w0 + len5 <= window_end

      if pick_left or pick_right then
        local t5
        if pick_left and pick_right then
          if math.random() < 0.5 then
            t5 = random_pos_in(window_start, left_w1 + len5, len5)
          else
            t5 = random_pos_in(right_w0, window_end, len5)
          end
        elseif pick_left then
          t5 = random_pos_in(window_start, left_w1 + len5, len5)
        else
          t5 = random_pos_in(right_w0, window_end, len5)
        end

        if t5 and not ranges_overlap(t3, t3_end, t5, t5 + len5) then
          return t3, t5
        end
      end
    end
  end

  return nil, nil
end

local function generate_bird_groups(total_sec, bg, len3, len4, len5)
  local groups = {}
  local gap_min = bg.group_gap_min or 2.0
  local gap_max = bg.group_gap_max or 4.0
  if gap_max < gap_min then gap_max = gap_min end

  local t4_count = bg.track4.count or 4
  local t4_step = bg.track4.step or 5
  local t4_offset = bg.track4.offset or 0
  local max_tries = bg.placement_max_tries or 64

  local cursor = bg.first_pos or 0

  while cursor < total_sec do
    local t4 = {}
    for i = 0, t4_count - 1 do
      t4[#t4 + 1] = cursor + t4_offset + i * t4_step
    end

    local window_start = cursor
    local window_end = t4[#t4] + len4

    if window_end - window_start < len3 + len5 + 0.01 then
      break
    end

    local t3, t5 = place_t3_t5(window_start, window_end, len3, len5, max_tries)
    if not t3 or not t5 then
      break
    end

    local group_end = window_end
    if t3 + len3 > group_end then group_end = t3 + len3 end
    if t5 + len5 > group_end then group_end = t5 + len5 end

    groups[#groups + 1] = {
      start = cursor,
      t3 = t3,
      t4 = t4,
      t5 = t5,
      end_t = group_end,
    }

    if group_end >= total_sec then break end

    local gap = gap_min + math.random() * (gap_max - gap_min)
    cursor = group_end + gap
  end

  return groups
end

local function run_bird_layers(cfg, proj_path, total_sec, log)
  local bg = cfg.bird_group
  if not bg then
    log_add(log, "✗ 配置缺少 bird_group")
    return
  end

  local tr3 = track_by_number(bg.track3.track)
  local tr4 = track_by_number(bg.track4.track)
  local tr5 = track_by_number(bg.track5.track)
  if not tr3 or not tr4 or not tr5 then
    log_add(log, "✗ 轨 3/4/5 不完整")
    return
  end

  local tmpl3 = get_track_template(tr3, proj_path, log, "轨3")
  local tmpl4 = get_track_template(tr4, proj_path, log, "轨4")
  local tmpl5 = get_track_template(tr5, proj_path, log, "轨5")
  if not tmpl3 or not tmpl4 or not tmpl5 then
    log_add(log, "✗ 轨 3/4/5 需各保留 ≥1 个 sample 作模板")
    return
  end

  if cfg.random_seed then
    math.randomseed(cfg.random_seed)
    log_add(log, "随机种子 = %d", cfg.random_seed)
  else
    math.randomseed(os.time())
    log_add(log, "随机种子 = os.time()")
  end

  local groups = generate_bird_groups(total_sec, bg, tmpl3.length, tmpl4.length, tmpl5.length)
  log_add(
    log,
    "生成 %d 组 · 每组 3×1 4×4 5×1 · gap %.1f–%.1f s",
    #groups,
    bg.group_gap_min,
    bg.group_gap_max
  )

  if cfg.clear_existing then
    delete_track_items(tr3)
    delete_track_items(tr4)
    delete_track_items(tr5)
    log_add(log, "已清除轨 3–5 旧 item")
  end

  local n3, n4, n5 = 0, 0, 0
  for _, g in ipairs(groups) do
    if g.t3 + tmpl3.length <= total_sec and insert_from_template(tr3, tmpl3, g.t3, cfg.fade_sec) then
      n3 = n3 + 1
    end
    for _, pos in ipairs(g.t4) do
      if pos + tmpl4.length <= total_sec and insert_from_template(tr4, tmpl4, pos, cfg.fade_sec) then
        n4 = n4 + 1
      end
    end
    if g.t5 + tmpl5.length <= total_sec and insert_from_template(tr5, tmpl5, g.t5, cfg.fade_sec) then
      n5 = n5 + 1
    end
  end

  log_add(log, "✓ 轨3 %s · %d item（每组 1）", bg.track3.name, n3)
  log_add(log, "✓ 轨4 %s · %d item（每组 4）", bg.track4.name, n4)
  log_add(log, "✓ 轨5 %s · %d item（每组 1 · 与轨3 不重叠）", bg.track5.name, n5)
end

local function main()
  r.ShowConsoleMsg("\n[lakeheal] ========== lakeheal_setup_bird_layers v3.0 ==========\n")

  local cfg, cfg_path_or_err = load_config()
  if not cfg then
    r.ShowMessageBox(cfg_path_or_err, "LakeHealMac setup", 0)
    return
  end

  local total_sec = get_fill_length(cfg)
  local hours = total_sec / 3600

  local choice = r.ShowMessageBox(
    string.format(
      "工程: %s\n轨 1/2 已有 %.0f h · 不改动\n轨 3–5 按组随机铺满至 %.0f h\n\n每组: 轨3×1 · 轨4×4 · 轨5×1\n轨3/5 时间不重叠 · 组间 gap 随机\n\n确定？",
      cfg.project_name or "LakeHealMac",
      hours,
      hours
    ),
    "LakeHealMac setup",
    1
  )
  if choice ~= 1 then return end

  r.Undo_BeginBlock()
  r.PreventUIRefresh(1)

  local log = {}
  log_add(log, "配置: %s", cfg_path_or_err or "")
  log_add(log, "铺满轨 3–5 → %.0f h · 轨 1/2 不改动", hours)

  run_bird_layers(cfg, get_project_dir(), total_sec, log)

  r.PreventUIRefresh(-1)
  r.UpdateArrange()
  r.Undo_EndBlock("LakeHealMac bird layers v3", -1)

  log_add(log, "========== 完成 ==========")
  r.ShowMessageBox(table.concat(log, "\n"), "LakeHealMac setup · 完成", 0)
end

main()
