-- @description Ensure Group bus: ReaEQ bypass, ReaLimit -1 dBTP, no ReaComp
-- @version 1.0

local function find_group_track()
  for i = 0, reaper.CountTracks(0) - 1 do
    local tr = reaper.GetTrack(0, i)
    local _, name = reaper.GetSetMediaTrackInfo_String(tr, "P_NAME", "", false)
    if name == "Group" then
      return tr
    end
  end
  return nil
end

local function fx_name(tr, idx)
  local ok, name = reaper.TrackFX_GetFXName(tr, idx, "")
  return ok and name or ""
end

local tr = find_group_track()
if not tr then
  reaper.ShowConsoleMsg("ensure_group_realimit: Group track not found\n")
  return
end

for i = reaper.TrackFX_GetCount(tr) - 1, 0, -1 do
  if fx_name(tr, i):find("ReaComp", 1, true) then
    reaper.TrackFX_Delete(tr, i)
  end
end

local limit_idx = -1
for i = 0, reaper.TrackFX_GetCount(tr) - 1 do
  if fx_name(tr, i):find("ReaLimit", 1, true) then
    limit_idx = i
    break
  end
end
if limit_idx < 0 then
  limit_idx = reaper.TrackFX_AddByName(tr, "ReaLimit", false, -1)
end
if limit_idx < 0 then
  reaper.ShowConsoleMsg("ensure_group_realimit: ReaLimit not available\n")
  return
end

for i = 0, reaper.TrackFX_GetCount(tr) - 1 do
  if fx_name(tr, i):find("ReaEQ", 1, true) then
    reaper.TrackFX_SetEnabled(tr, i, false)
  end
end

reaper.TrackFX_SetEnabled(tr, limit_idx, true)
-- ReaLimit (Cockos): param 0 = ceiling (dB), param 3 = true peak (0/1)
reaper.TrackFX_SetParamEx(tr, limit_idx, 0, -1.0, true)
if reaper.TrackFX_GetNumParams(tr, limit_idx) > 3 then
  reaper.TrackFX_SetParamEx(tr, limit_idx, 3, 1.0, true)
end

reaper.Main_OnCommand(40026, 0) -- File: Save project
reaper.Main_OnCommand(40004, 0) -- File: Quit REAPER
