-- @description 在选中轨道、指定时长内随机分布 one-shot（单轨手动）
-- @version 1.0
-- @author relaxASMR

local r = reaper

local function parse_number(s, default)
  local n = tonumber(s)
  return n or default
end

local function get_source_length(path)
  local src = r.PCM_Source_CreateFromFile(path)
  if not src then return nil end
  local len = r.GetMediaSourceLength(src, false)
  r.PCM_Source_Destroy(src)
  return len
end

local function collect_positions(count, range_start, range_end, item_len, min_gap)
  local positions = {}
  local span = range_end - range_start - item_len
  if span <= 0 or count < 1 then return positions end

  math.randomseed(os.time())

  local max_tries = count * 200
  local tries = 0
  while #positions < count and tries < max_tries do
    tries = tries + 1
    local pos = range_start + math.random() * span
    local ok = true
    for _, p in ipairs(positions) do
      if math.abs(pos - p) < min_gap then
        ok = false
        break
      end
    end
    if ok then
      positions[#positions + 1] = pos
    end
  end

  table.sort(positions)
  return positions
end

local function insert_item(track, path, pos, item_len)
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
  r.SetMediaItemTakeInfo_Value(take, "D_STARTOFFS", 0)
  r.SetMediaItemTakeInfo_Value(take, "D_PLAYRATE", 1)

  if not item_len or item_len <= 0 then
    item_len = r.GetMediaSourceLength(src, false)
  end

  r.SetMediaItemInfo_Value(item, "D_POSITION", pos)
  r.SetMediaItemInfo_Value(item, "D_LENGTH", item_len)
  r.UpdateItemInProject(item)
  return true
end

local function main()
  local track = r.GetSelectedTrack(0, 0)
  if not track then
    r.ShowMessageBox("请先选中一条轨道", "random_scatter_items", 0)
    return
  end

  local _, track_name = r.GetTrackName(track)

  local ok, file = r.GetUserFileNameForRead("", "选择 one-shot WAV", "wav")
  if not ok then return end

  local item_len = get_source_length(file)
  if not item_len or item_len <= 0 then
    r.ShowMessageBox("无法读取音频长度：" .. file, "random_scatter_items", 0)
    return
  end

  local ret, user = r.GetUserInputs(
    "随机分布 · 轨道: " .. track_name,
    4,
    "数量 count,工程时长(小时) hours,最小间隔(分钟) min_gap,起点偏移(分钟) start_offset",
    "3,8,8,0"
  )
  if not ret then return end

  local count_s, hours_s, gap_s, start_s = user:match("([^,]+),([^,]+),([^,]+),([^,]+)")
  local count = parse_number(count_s, 3)
  local hours = parse_number(hours_s, 8)
  local min_gap = parse_number(gap_s, 8) * 60
  local start_offset = parse_number(start_s, 0) * 60

  local range_start = start_offset
  local range_end = hours * 3600
  local project_len = r.GetProjectLength(0)
  if project_len > 0 then
    range_end = math.min(range_end, project_len)
  end

  if range_end - range_start < item_len + min_gap then
    r.ShowMessageBox("时间范围太短，无法放置", "random_scatter_items", 0)
    return
  end

  r.Undo_BeginBlock()
  r.PreventUIRefresh(1)

  local positions = collect_positions(count, range_start, range_end, item_len, min_gap)
  local placed = 0
  for _, pos in ipairs(positions) do
    if insert_item(track, file, pos, item_len) then
      placed = placed + 1
    end
  end

  r.PreventUIRefresh(-1)
  r.UpdateArrange()
  r.Undo_EndBlock("Random scatter one-shots on track", -1)

  if placed < count then
    r.ShowMessageBox(
      string.format("已放置 %d / %d 个", placed, count),
      "random_scatter_items",
      0
    )
  end
end

main()
