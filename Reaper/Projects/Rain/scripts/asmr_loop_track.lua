-- @description ASMR · 单轨循环至工程时长
-- @version 1.0
-- @author relaxASMR

local r = reaper

local function parse_num(s, default)
  local n = tonumber(s)
  return n or default
end

local function track_by_number(n)
  if n < 1 then return nil end
  return r.GetTrack(0, n - 1)
end

local function main()
  local sel = r.GetSelectedTrack(0, 0)
  local ret, user = r.GetUserInputs(
    "循环轨 · 0=选中轨",
    2,
    "轨道 track (0=选中),时长 minutes (0=工程长度)",
    "0,100"
  )
  if not ret then return end
  local track_n, minutes_s = user:match("([^,]+),([^,]+)")
  track_n = parse_num(track_n, 0)
  local minutes = parse_num(minutes_s, 100)

  local track
  if track_n > 0 then
    track = track_by_number(track_n)
  else
    track = sel
  end
  if not track then
    r.ShowMessageBox("请指定轨道", "asmr_loop_track", 0)
    return
  end

  local total_sec = minutes * 60
  if minutes <= 0 then
    total_sec = r.GetProjectLength(0)
    if total_sec <= 0 then total_sec = 100 * 60 end
  end

  r.GetSetProjectInfo(0, "PROJECT_LENGTH", total_sec, true)

  r.Undo_BeginBlock()
  r.PreventUIRefresh(1)
  local n = r.CountTrackMediaItems(track)
  for i = 0, n - 1 do
    local item = r.GetTrackMediaItem(track, i)
    r.SetMediaItemInfo_Value(item, "B_LOOPSRC", 1)
    local pos = r.GetMediaItemInfo_Value(item, "D_POSITION")
    local len = total_sec - pos
    if len > 0 then
      r.SetMediaItemInfo_Value(item, "D_LENGTH", len)
    end
  end
  r.PreventUIRefresh(-1)
  r.UpdateArrange()
  r.Undo_EndBlock("Loop track to duration", -1)
end

main()
