-- @description ASMR · 按 asmr_config 散布指定轨道
-- @version 1.0
-- @author relaxASMR
-- @about
--   输入轨道号，从 scripts/asmr_config.lua 的 scatter_layers 读取
--   count / min_gap / max_gap / randomness；0=当前选中轨

local r = reaper

local function load_paths()
  local _, script_path = r.get_action_context()
  local dir = script_path:match("^(.+)[\\/][^\\/]+$")
  local f = loadfile(dir .. package.config:sub(1, 1) .. "asmr_paths.lua")
  if not f then return nil end
  return f()
end

local function track_by_number(n)
  return r.GetTrack(0, n - 1)
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
  if not item or not template.chunk then return false end
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

local function main()
  local paths_mod = load_paths()
  if not paths_mod then return end
  local cfg, err = paths_mod.load_asmr_config()
  if not cfg then
    r.ShowMessageBox(err, "asmr_scatter_config_track", 0)
    return
  end

  local ret, track_s = r.GetUserInputs("散布轨（读 config）", 1, "轨道 track (0=选中)", "0")
  if not ret then return end
  local track_n = tonumber(track_s) or 0
  local track
  if track_n > 0 then
    track = track_by_number(track_n)
  else
    track = r.GetSelectedTrack(0, 0)
  end
  if not track then return end

  local spec = nil
  local tr_idx = -1
  for i = 0, r.CountTracks(0) - 1 do
    if r.GetTrack(0, i) == track then
      tr_idx = i + 1
      break
    end
  end
  for _, s in ipairs(cfg.scatter_layers or {}) do
    if s.track == tr_idx or s.track == track_n then
      spec = s
      break
    end
  end
  if not spec then
    r.ShowMessageBox("config 中无 scatter_layers 条目：轨 " .. tr_idx, "asmr_scatter_config_track", 0)
    return
  end

  local hours = cfg.duration_hours or 3
  local total_sec = hours * 3600
  if r.GetProjectLength(0) > 0 then total_sec = r.GetProjectLength(0) end
  local fade_sec = cfg.fade_sec or 0.08
  local template = get_scatter_template(track, spec, paths_mod)
  if not template then
    r.ShowMessageBox(
      "轨 " .. tr_idx .. " 无 template，且无法从 config.paths 加载素材",
      "asmr_scatter_config_track",
      0
    )
    return
  end

  if spec.clear_existing then delete_scatter_items(track) end
  local min_g = (spec.min_gap_min or 3) * 60
  local max_g = (spec.max_gap_min or 8) * 60
  local randomness = spec.randomness or 0.5
  math.randomseed(os.time() + tr_idx * 131)

  local positions = {}
  if spec.count and spec.count > 0 then
    local span = total_sec - template.length
    local step = span / (spec.count + 1)
    for i = 1, spec.count do
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

  r.Undo_BeginBlock()
  r.PreventUIRefresh(1)
  local placed = 0
  for _, pos in ipairs(positions) do
    if insert_from_template(track, template, pos, fade_sec) then placed = placed + 1 end
  end
  r.PreventUIRefresh(-1)
  r.UpdateArrange()
  r.Undo_EndBlock("Scatter " .. (spec.name or ""), -1)

  r.ShowMessageBox(
    string.format("%s · 轨 %d · 放置 %d", spec.name or "", tr_idx, placed),
    "asmr_scatter_config_track",
    0
  )
end

main()
