-- @description ASMR · 单轨随机散布（配方优先，无配方则手动）
-- @version 3.0
-- @author relaxASMR
-- @about
--   输入：0=当前选中轨 · 或层 id（3_impact）· 或配方 track 号（3）
--   有 scripts/asmr_config.lua 且匹配 scatter_layers → 用配方间隔/随机度
--   否则弹出手动参数（时长、间隔、随机度等）
--   整片铺稀疏仍用 asmr_apply_recipe.lua

local r = reaper

local function log(msg)
  r.ShowConsoleMsg("[scatter] " .. msg .. "\n")
end

local function script_dir()
  local _, p = r.get_action_context()
  return p:match("^(.+)[\\/][^\\/]+$")
end

local function load_paths()
  local f = loadfile(script_dir() .. package.config:sub(1, 1) .. "asmr_paths.lua")
  if not f then return nil end
  return f()
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
    for i = 0, r.CountTracks(0) - 1 do
      local tr = r.GetTrack(0, i)
      local _, name = r.GetTrackName(tr)
      if name == key then return tr, name end
    end
    return r.GetTrack(0, n - 1), "track " .. n
  end
  for i = 0, r.CountTracks(0) - 1 do
    local tr = r.GetTrack(0, i)
    local _, name = r.GetTrackName(tr)
    if name == key then return tr, name end
  end
  return nil, key
end

local function find_scatter_spec(cfg, track, key)
  if not cfg or not track then return nil end
  local name = track_name(track)
  local paths_mod = load_paths()
  for _, spec in ipairs(cfg.scatter_layers or {}) do
    if spec.id and name == spec.id then return spec end
    if paths_mod and paths_mod.track_for_layer then
      if paths_mod.track_for_layer(spec) == track then return spec end
    end
    local n = tonumber(key)
    if n and spec.track == n then return spec end
  end
  return nil
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
    local take = r.GetActiveTake(item)
    if not take then goto continue end
    local src = r.GetMediaItemTake_Source(take)
    if not src then goto continue end
    local path = get_source_path(take)
    if not path then goto continue end
    local len = r.GetMediaItemInfo_Value(item, "D_LENGTH")
    local src_len = r.GetMediaSourceLength(src, false)
    local is_loop = r.GetMediaItemInfo_Value(item, "B_LOOPSRC") == 1
    -- 循环片段也作 template：散布用源文件长度做单次事件，不用 chunk（含循环状态）
    if is_loop or len > src_len * 1.5 then
      len = src_len
    end
    local tmpl = {
      chunk = is_loop and nil or get_item_chunk(item),
      length = len,
      path = path,
    }
    if r.GetMediaItemInfo_Value(item, "D_POSITION") < 0.001 then return tmpl end
    if not fallback then fallback = tmpl end
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

local function delete_scatter_items(track, keep_template)
  local n = r.CountTrackMediaItems(track)
  for i = n - 1, 0, -1 do
    local item = r.GetTrackMediaItem(track, i)
    if keep_template and r.GetMediaItemInfo_Value(item, "D_POSITION") < 0.001 then
      goto continue
    end
    if r.GetMediaItemInfo_Value(item, "B_LOOPSRC") ~= 1 then
      r.DeleteTrackMediaItem(track, item)
    end
    ::continue::
  end
end

local function delete_all_items(track)
  local n = r.CountTrackMediaItems(track)
  for i = n - 1, 0, -1 do
    r.DeleteTrackMediaItem(track, r.GetTrackMediaItem(track, i))
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

local function build_positions(total_sec, template_len, count, min_gap, max_gap, randomness)
  local positions = {}
  if count and count > 0 then
    local span = total_sec - template_len
    local step = span / (count + 1)
    for i = 1, count do
      local jitter = (math.random() - 0.5) * step * randomness
      positions[#positions + 1] = step * i + jitter
    end
  else
    local t = min_gap * (0.3 + math.random() * 0.4)
    while t + template_len < total_sec do
      positions[#positions + 1] = t
      t = t + jitter_gap(min_gap, max_gap, randomness)
    end
  end
  return positions
end

local function run_scatter(track, label, total_sec, fade_sec, template, spec)
  local count = spec.count
  local min_g = (spec.min_gap_min or 3) * 60
  local max_g = (spec.max_gap_min or 8) * 60
  if max_g < min_g then max_g = min_g end
  local randomness = spec.randomness or 0.5
  local clear = spec.clear_existing

  math.randomseed(os.time() + math.floor(min_g) + math.floor(template.length * 100))

  r.Undo_BeginBlock()
  r.PreventUIRefresh(1)
  if clear then
    delete_scatter_items(track, true)
  end

  local positions = build_positions(total_sec, template.length, count, min_g, max_g, randomness)
  local placed = 0
  for _, pos in ipairs(positions) do
    if insert_from_template(track, template, pos, fade_sec) then placed = placed + 1 end
  end

  r.PreventUIRefresh(-1)
  r.UpdateArrange()
  r.Undo_EndBlock("Scatter " .. label, -1)

  log(string.format("%s · 放置 %d / %d · %.1fh", label, placed, #positions, total_sec / 3600))
  r.ShowMessageBox(
    string.format("%s\n放置 %d 个事件", label, placed),
    "asmr_scatter_track",
    0
  )
end

local function run_manual(track, label)
  local template = get_template_from_track(track)
  if not template then
    r.ShowMessageBox(
      "轨道上需有一条可读的音频 sample（建议在 position 0）。\n"
        .. "若片段已拖入仍报错，检查是否为有效音频、路径是否可访问。",
      "asmr_scatter_track",
      0
    )
    return
  end

  local ret, user = r.GetUserInputs(
    "手动散布 · " .. label,
    6,
    "时长h (0=工程),次数(0=间隔),min间隔min,max间隔min,随机度0-1,fade_ms",
    "0,0,3,8,0.6,80"
  )
  if not ret then return end

  local dur_h, count, min_gap_min, max_gap_min, randomness, fade_ms =
    user:match("([^,]+),([^,]+),([^,]+),([^,]+),([^,]+),([^,]+)")
  dur_h = tonumber(dur_h) or 0
  count = tonumber(count) or 0
  min_gap_min = tonumber(min_gap_min) or 3
  max_gap_min = tonumber(max_gap_min) or 8
  randomness = tonumber(randomness) or 0.5
  fade_ms = tonumber(fade_ms) or 80

  local total_sec = dur_h > 0 and dur_h * 3600 or r.GetProjectLength(0)
  if total_sec <= 0 then total_sec = 3 * 3600 end

  local spec = {
    count = count > 0 and count or nil,
    min_gap_min = min_gap_min,
    max_gap_min = max_gap_min,
    randomness = randomness,
    clear_existing = false,
  }
  delete_all_items(track)
  run_scatter(track, label .. " (手动)", total_sec, fade_ms / 1000, template, spec)
end

local function main()
  local sel = r.GetSelectedTrack(0, 0)
  local sel_hint = sel and track_name(sel) or "未选中"
  local ret, key = r.GetUserInputs(
    "散布单轨",
    1,
    "0=选中 · 或层 id(3_impact) · 或轨号",
    sel_hint == "未选中" and "0" or sel_hint
  )
  if not ret then return end

  local track, label = resolve_track(key)
  if not track then
    r.ShowMessageBox("找不到轨道: " .. key, "asmr_scatter_track", 0)
    return
  end
  label = track_name(track) or label

  local paths_mod = load_paths()
  local cfg, cfg_err = nil, nil
  if paths_mod then
    cfg, cfg_err = paths_mod.load_asmr_config()
  end

  local spec = cfg and find_scatter_spec(cfg, track, key)
  if spec and paths_mod then
    local total_sec = (cfg.duration_hours or 3) * 3600
    if r.GetProjectLength(0) > 0 then total_sec = r.GetProjectLength(0) end
    local fade_sec = cfg.fade_sec or 0.08
    local template = get_template_from_track(track)
    if not template then template = template_from_spec(spec, paths_mod) end
    if not template then
      r.ShowMessageBox("无 template 且 config.paths 不可用", "asmr_scatter_track", 0)
      return
    end
    log("配方模式 · " .. (spec.name or spec.id or label))
    run_scatter(track, spec.name or spec.id or label, total_sec, fade_sec, template, spec)
    return
  end

  if cfg_err and key ~= "0" and not tonumber(key) then
    log("无配方或层未在 scatter_layers，改用手动模式")
  end
  run_manual(track, label)
end

main()
