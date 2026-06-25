-- @description ASMR · 单轨随机散布 one-shot（通用）
-- @version 2.0
-- @author relaxASMR
-- @about
--   参数（GetUserInputs）：
--     track        轨道号（1-based），0=当前选中轨
--     duration_h   工程时长（小时），0=读工程长度
--     count        总出现次数；0=按间隔自动铺满
--     min_gap_min  最小间隔（分钟）
--     max_gap_min  最大间隔（分钟）
--     randomness   随机程度 0~1（越大间隔/位置抖动越大）
--     fade_ms      淡入淡出（毫秒）
--   优先复制轨道上已有 item（template）；否则用 paths 配置或选文件。

local r = reaper

local function log(msg)
  r.ShowConsoleMsg("[scatter] " .. msg .. "\n")
end

local function parse_num(s, default)
  local n = tonumber(s)
  if n == nil then return default end
  return n
end

local function load_paths()
  local _, script_path = r.get_action_context()
  if not script_path then return nil end
  local dir = script_path:match("^(.+)[\\/][^\\/]+$")
  local f = loadfile(dir .. package.config:sub(1, 1) .. "asmr_paths.lua")
  if not f then return nil end
  return f()
end

local function track_by_number(n)
  if n < 1 then return nil end
  return r.GetTrack(0, n - 1)
end

local function get_item_chunk(item)
  local a, b = r.GetSetItemState(item, "", false)
  if type(b) == "string" and b ~= "" then return b end
  if type(a) == "string" and a ~= "" then return a end
  return nil
end

local function get_source_filename(src)
  local a, b = r.GetMediaSourceFileName(src, "")
  if type(b) == "string" and b ~= "" then return b end
  if type(a) == "string" and a ~= "" then return a end
  return nil
end

local function get_template(track)
  local n = r.CountTrackMediaItems(track)
  for i = 0, n - 1 do
    local item = r.GetTrackMediaItem(track, i)
    local take = r.GetActiveTake(item)
    if take then
      local src = r.GetMediaItemTake_Source(take)
      if src then
        local len = r.GetMediaItemInfo_Value(item, "D_LENGTH")
        local src_len = r.GetMediaSourceLength(src, false)
        if len > src_len * 1.5 then len = src_len end
        if len and len > 0 then
          return {
            chunk = get_item_chunk(item),
            length = len,
            path = get_source_filename(src),
          }
        end
      end
    end
  end
  return nil
end

local function delete_items(track)
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
  local item = r.AddMediaItemToTrack(track)
  if not item then return false end
  if template.chunk then
    local ok = r.SetItemStateChunk(item, template.chunk, false)
    if not ok then
      r.DeleteTrackMediaItem(track, item)
      if template.path then
        return insert_oneshot(track, template.path, pos, template.length, fade_sec)
      end
      return false
    end
  elseif template.path then
    r.DeleteTrackMediaItem(track, item)
    return insert_oneshot(track, template.path, pos, template.length, fade_sec)
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

local function jitter_gap(min_gap, max_gap, randomness)
  local spread = max_gap - min_gap
  local rfac = math.max(0, math.min(1, randomness or 0.5))
  local base = min_gap + math.random() * spread
  local jitter = (math.random() - 0.5) * spread * rfac
  return math.max(min_gap, base + jitter)
end

local function positions_by_count(count, range_start, range_end, item_len, randomness)
  local positions = {}
  local span = range_end - range_start - item_len
  if count < 1 or span <= 0 then return positions end
  local step = span / (count + 1)
  local rfac = math.max(0, math.min(1, randomness or 0.5))
  for i = 1, count do
    local jitter = (math.random() - 0.5) * step * rfac
    local pos = range_start + step * i + jitter
    if pos >= range_start and pos + item_len <= range_end then
      positions[#positions + 1] = pos
    end
  end
  table.sort(positions)
  return positions
end

local function positions_by_gap(range_start, range_end, item_len, min_gap, max_gap, randomness)
  local positions = {}
  local t = range_start + min_gap * (0.3 + math.random() * 0.4)
  while t + item_len < range_end do
    positions[#positions + 1] = t
    t = t + jitter_gap(min_gap, max_gap, randomness)
  end
  return positions
end

local function main()
  local sel = r.GetSelectedTrack(0, 0)
  local _, sel_name = sel and r.GetTrackName(sel) or ""

  local ret, user = r.GetUserInputs(
    "随机散布 · " .. (sel_name or "未选中"),
    7,
    "轨道 track (0=选中),时长h duration_h,次数 count (0=按间隔),min间隔min,max间隔min,随机度0-1,fade_ms",
    "0,3,0,3,8,0.6,80"
  )
  if not ret then return end

  local track_n, dur_h, count, min_gap_min, max_gap_min, randomness, fade_ms =
    user:match("([^,]+),([^,]+),([^,]+),([^,]+),([^,]+),([^,]+),([^,]+)")

  track_n = parse_num(track_n, 0)
  dur_h = parse_num(dur_h, 3)
  count = parse_num(count, 0)
  min_gap_min = parse_num(min_gap_min, 3)
  max_gap_min = parse_num(max_gap_min, 8)
  randomness = parse_num(randomness, 0.5)
  fade_ms = parse_num(fade_ms, 80)

  local track
  if track_n > 0 then
    track = track_by_number(track_n)
  else
    track = sel
  end
  if not track then
    r.ShowMessageBox("请指定有效轨道或先选中一条轨道", "asmr_scatter_track", 0)
    return
  end

  local _, track_name = r.GetTrackName(track)
  local template = get_template(track)
  if not template then
    r.ShowMessageBox("轨道上无 template item，请先插入一条 sample", "asmr_scatter_track", 0)
    return
  end

  local total_sec = dur_h * 3600
  if dur_h <= 0 then
    total_sec = r.GetProjectLength(0)
    if total_sec <= 0 then total_sec = 3 * 3600 end
  end

  local min_gap = min_gap_min * 60
  local max_gap = max_gap_min * 60
  if max_gap < min_gap then max_gap = min_gap end
  local fade_sec = fade_ms / 1000

  math.randomseed(os.time() + math.floor(randomness * 1000))

  local positions
  if count > 0 then
    positions = positions_by_count(count, 0, total_sec, template.length, randomness)
  else
    positions = positions_by_gap(0, total_sec, template.length, min_gap, max_gap, randomness)
  end

  r.Undo_BeginBlock()
  r.PreventUIRefresh(1)
  delete_items(track)

  local placed = 0
  for _, pos in ipairs(positions) do
    if insert_from_template(track, template, pos, fade_sec) then
      placed = placed + 1
    end
  end

  r.PreventUIRefresh(-1)
  r.UpdateArrange()
  r.Undo_EndBlock("Scatter track " .. track_name, -1)

  log(string.format(
    "轨 %s · 放置 %d · 计划 %d · %.1fh · random=%.2f",
    track_name, placed, #positions, total_sec / 3600, randomness
  ))
end

main()
