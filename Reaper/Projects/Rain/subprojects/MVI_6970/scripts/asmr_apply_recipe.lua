-- @description ASMR · 按 asmr_config 铺循环层 + 稀疏层
-- @version 2.0
-- @author relaxASMR
-- @about
--   读取工程目录 scripts/asmr_config.lua
--   循环：video + loop_layers
--   稀疏：scatter_layers（每轨调用通用散布逻辑）

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

local function get_item_chunk(item)
  local a, b = r.GetSetItemState(item, "", false)
  if type(b) == "string" and b ~= "" then return b end
  if type(a) == "string" and a ~= "" then return a end
  return nil
end

local function get_source_path(take)
  local src = r.GetMediaItemTake_Source(take)
  if not src then return nil end
  local a, b = r.GetMediaSourceFileName(src, "")
  if type(b) == "string" and b ~= "" then return b end
  if type(a) == "string" and a ~= "" then return a end
  return nil
end

local function get_template_from_track(track)
  local n = r.CountTrackMediaItems(track)
  local fallback = nil
  for i = 0, n - 1 do
    local item = r.GetTrackMediaItem(track, i)
    if r.GetMediaItemInfo_Value(item, "B_LOOPSRC") == 1 then goto continue end
    local take = r.GetActiveTake(item)
    if take then
      local src = r.GetMediaItemTake_Source(take)
      if src then
        local len = r.GetMediaItemInfo_Value(item, "D_LENGTH")
        local src_len = r.GetMediaSourceLength(src, false)
        if len > src_len * 1.5 then len = src_len end
        local tmpl = {
          chunk = get_item_chunk(item),
          length = len,
          path = get_source_path(take),
        }
        if r.GetMediaItemInfo_Value(item, "D_POSITION") < 0.001 then
          return tmpl
        end
        if not fallback then fallback = tmpl end
      end
    end
    ::continue::
  end
  return fallback
end

local function template_from_spec(spec, paths_mod)
  local rel = spec.paths and spec.paths[1]
  if not rel then return nil end
  local path = paths_mod.resolve_asset(rel, paths_mod.repo_root())
  if not path then return nil end
  local src = r.PCM_Source_CreateFromFile(path)
  if not src then return nil end
  local len = r.GetMediaSourceLength(src, false)
  if not len or len <= 0 then return nil end
  return { path = path, length = len }
end

local function get_scatter_template(track, spec, paths_mod)
  local t = get_template_from_track(track)
  if t then return t end
  return template_from_spec(spec, paths_mod)
end

local function delete_scatter_items(track)
  local n = r.CountTrackMediaItems(track)
  for i = n - 1, 0, -1 do
    local item = r.GetTrackMediaItem(track, i)
    if r.GetMediaItemInfo_Value(item, "B_LOOPSRC") ~= 1 then
      if r.GetMediaItemInfo_Value(item, "D_POSITION") < 0.001 then
        goto continue
      end
      r.DeleteTrackMediaItem(track, item)
    end
    ::continue::
  end
end

local function insert_oneshot(track, path, pos, item_len, fade_sec)
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
  if template.path and not template.chunk then
    return insert_oneshot(track, template.path, pos, template.length, fade_sec)
  end
  local item = r.AddMediaItemToTrack(track)
  if not item then return false end
  if not template.chunk then
    r.DeleteTrackMediaItem(track, item)
    return false
  end
  if not r.SetItemStateChunk(item, template.chunk, false) then
    r.DeleteTrackMediaItem(track, item)
    if template.path then
      return insert_oneshot(track, template.path, pos, template.length, fade_sec)
    end
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

local function jitter_gap(min_gap, max_gap, randomness)
  local spread = max_gap - min_gap
  local rfac = math.max(0, math.min(1, randomness or 0.5))
  return math.max(min_gap, min_gap + math.random() * spread + (math.random() - 0.5) * spread * rfac)
end

local function scatter_track(track, spec, total_sec, fade_sec, paths_mod)
  local template = get_scatter_template(track, spec, paths_mod)
  if not template then
    log("轨 " .. spec.track .. " 无 template 且 config.paths 不可用，跳过")
    return 0
  end
  if spec.clear_existing then delete_scatter_items(track) end

  local min_g = (spec.min_gap_min or 3) * 60
  local max_g = (spec.max_gap_min or 8) * 60
  if max_g < min_g then max_g = min_g end
  local randomness = spec.randomness or 0.5
  local count = spec.count

  math.randomseed(os.time() + spec.track * 997)

  local positions = {}
  if count and count > 0 then
    local span = total_sec - template.length
    local step = span / (count + 1)
    for i = 1, count do
      local jitter = (math.random() - 0.5) * step * randomness
      positions[#positions + 1] = step * i + jitter
    end
  else
    local t = min_g * (0.3 + math.random() * 0.4)
    while t + template.length < total_sec do
      positions[#positions + 1] = t
      t = t + jitter_gap(min_g, max_g, randomness)
    end
  end

  local placed = 0
  for _, pos in ipairs(positions) do
    if insert_from_template(track, template, pos, fade_sec) then
      placed = placed + 1
    end
  end
  log(string.format("轨 %d %s · 放置 %d", spec.track, spec.name or "", placed))
  return placed
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
  local fade_sec = cfg.fade_sec or 0.08

  local choice = r.ShowMessageBox(
    string.format(
      "%s\n时长 %.0f h\n【确定】循环+稀疏\n【否】仅循环\n【取消】仅稀疏",
      cfg.project_name or cfg.scene_id or "ASMR",
      hours
    ),
    "asmr_apply_recipe",
    3
  )
  local all, loop_only, scatter_only = choice == 6, choice == 7, choice == 2
  if not all and not loop_only and not scatter_only then return end

  r.Undo_BeginBlock()
  r.PreventUIRefresh(1)
  r.GetSetProjectInfo(0, "PROJECT_LENGTH", total_sec, true)

  if all or loop_only then
    -- 视频 looper：render_only 时不改动（仅最终渲染用）
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
    local vol_mod = load_vol_envelope()
    if vol_mod then
      local n = vol_mod.apply_from_config(cfg, total_sec, paths_mod)
      if n > 0 then log("音量包络 " .. n .. " 轨") end
    end
  end

  if all or scatter_only then
    for _, spec in ipairs(cfg.scatter_layers or {}) do
      local tr = track_for_spec(spec, paths_mod)
      if tr then scatter_track(tr, spec, total_sec, fade_sec, paths_mod) end
    end
  end

  r.PreventUIRefresh(-1)
  r.UpdateArrange()
  r.Undo_EndBlock("Apply ASMR recipe", -1)
  r.ShowMessageBox("配方已应用 · " .. hours .. " h", "asmr_apply_recipe", 0)
end

main()
