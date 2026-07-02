-- 轨级 RS-PASS 修改建议 · 展示与一键应用（由 asmr_score_mix.lua 调用）

local M = {}

local function log(msg)
  reaper.ShowConsoleMsg("[score_apply] " .. msg .. "\n")
end

local function path_exists(p)
  if not p or p == "" then return false end
  if reaper.file_exists then return reaper.file_exists(p) end
  local fh = io.open(p, "rb")
  if fh then fh:close(); return true end
  return false
end

function M.track_by_name(name)
  if not name or name == "" then return nil end
  local lname = name:lower()
  for i = 0, reaper.CountTracks(0) - 1 do
    local tr = reaper.GetTrack(0, i)
    local _, n = reaper.GetSetMediaTrackInfo_String(tr, "P_NAME", "", false)
    if n == name or n:lower() == lname then return tr end
    if n:match("^" .. name) or n:lower():match("^" .. lname) then return tr end
  end
  return nil
end

function M.group_track()
  return M.track_by_name("Group") or M.track_by_name("group")
end

function M.track_has_fx_name(track, needle)
  if not track then return false end
  needle = needle:lower()
  local nfx = reaper.TrackFX_GetCount(track)
  for i = 0, nfx - 1 do
    local _, name = reaper.TrackFX_GetFXName(track, i, "")
    if name and name:lower():find(needle, 1, true) then return true end
  end
  return false
end

function M.resolve_fx_path(params, ctx)
  local fx = params.fx or ""
  local search = params.search_paths or { "scripts/fx" }
  local sep = ctx.sep or package.config:sub(1, 1)
  local candidates = {}
  if ctx.project_root then
    for _, sub in ipairs(search) do
      candidates[#candidates + 1] = ctx.project_root .. sep .. sub:gsub("/", sep) .. sep .. fx
    end
  end
  if ctx.repo_root then
    candidates[#candidates + 1] = ctx.repo_root .. sep .. "Reaper" .. sep .. "scripts" .. sep .. "fx" .. sep .. fx
  end
  for _, p in ipairs(candidates) do
    if path_exists(p) then return p end
  end
  return nil
end

function M.adjust_vol(track, factor)
  local v = reaper.GetMediaTrackInfo_Value(track, "D_VOL")
  reaper.SetMediaTrackInfo_Value(track, "D_VOL", v * factor)
  return true
end

function M.add_vol_envelope(track, total_sec, params, vol_mod)
  if not vol_mod then return false, "缺少 vol_envelope 模块" end
  local spec = {
    track = 0,
    name = "",
    vol_envelope = {
      shape = params.shape or "single_wave",
      depth = params.depth or 0.08,
      peak_at = params.peak_at or "center",
    },
  }
  local ok = vol_mod.apply_layer_envelope(track, total_sec, spec)
  return ok, ok and "已添加音量包络" or "包络添加失败"
end

function M.add_fx(track, params, ctx)
  if M.track_has_fx_name(track, "asmr_sleep") or M.track_has_fx_name(track, "sleep hf") then
    return true, "已有 HF EQ，跳过"
  end
  local fx_path = M.resolve_fx_path(params, ctx)
  if not fx_path then
    return false, "找不到 FX: " .. tostring(params.fx)
  end
  local idx = reaper.TrackFX_AddByName(track, fx_path, false, -1)
  if idx == nil or idx < 0 then
    idx = reaper.TrackFX_AddByName(track, "JS: " .. fx_path, false, -1)
  end
  if idx == nil or idx < 0 then
    return false, "TrackFX_AddByName 失败: " .. fx_path
  end
  return true, "已添加 " .. (params.fx or "FX")
end

function M.resolve_track(action)
  local target = action.target or "track"
  if target == "group" or action.track_name == "Group" then
    return M.group_track(), "Group"
  end
  local name = action.track_name or action.layer_id
  return M.track_by_name(name), name
end

function M.load_actions(actions_path)
  local f, err = loadfile(actions_path)
  if not f then return nil, err or "loadfile 失败" end
  return f()
end

function M.format_actions_list(actions)
  local lines = {}
  for i, act in ipairs(actions or {}) do
    local tag = act.auto_apply and "[可自动]" or "[手动]"
    local pri = act.priority and ("(" .. act.priority .. ")") or ""
    lines[#lines + 1] = string.format("%d. %s %s %s", i, tag, pri, act.text or act.reason or "?")
  end
  return table.concat(lines, "\n")
end

function M.apply_actions(actions, ctx, opts)
  opts = opts or {}
  local only_auto = opts.only_auto ~= false
  local vol_mod = ctx.vol_mod
  local total_sec = ctx.total_sec or reaper.GetProjectLength(0)
  local applied, skipped, failed = {}, {}, {}

  reaper.Undo_BeginBlock()
  reaper.PreventUIRefresh(1)

  for _, act in ipairs(actions or {}) do
    if act.action == "note" then
      skipped[#skipped + 1] = act.text or act.reason
    elseif only_auto and not act.auto_apply then
      skipped[#skipped + 1] = (act.text or act.reason) .. "（需手动）"
    else
      local track, tname = M.resolve_track(act)
      if not track and act.action ~= "note" then
        failed[#failed + 1] = (act.text or "?") .. " → 找不到轨"
      elseif act.action == "adjust_vol" then
        local factor = (act.params or {}).factor or 1.0
        M.adjust_vol(track, factor)
        applied[#applied + 1] = string.format("%s ×%.2f", tname, factor)
        log("adjust_vol " .. tname .. " ×" .. factor)
      elseif act.action == "add_vol_envelope" then
        local ok, msg = M.add_vol_envelope(track, total_sec, act.params or {}, vol_mod)
        if ok then applied[#applied + 1] = tname .. ": " .. msg
        else failed[#failed + 1] = tname .. ": " .. msg end
      elseif act.action == "add_fx" then
        local ok, msg = M.add_fx(track, act.params or {}, ctx)
        if ok then applied[#applied + 1] = (tname or "Group") .. ": " .. msg
        else failed[#failed + 1] = (tname or "Group") .. ": " .. msg end
      else
        skipped[#skipped + 1] = act.text or act.action
      end
    end
  end

  reaper.PreventUIRefresh(-1)
  reaper.Undo_EndBlock("RS-PASS apply track fixes", -1)
  reaper.UpdateArrange()

  return applied, skipped, failed
end

function M.prompt_and_apply(actions, ctx)
  if not actions or #actions == 0 then
    return false, "无轨级修改建议（混音结构已接近目标）"
  end

  local auto_n = 0
  for _, a in ipairs(actions) do
    if a.auto_apply and a.action ~= "note" then auto_n = auto_n + 1 end
  end

  local list = M.format_actions_list(actions)
  local intro = string.format(
    "轨级修改建议（共 %d 条，其中 %d 条可一键应用）:\n\n%s",
    #actions, auto_n, list
  )

  reaper.ShowConsoleMsg("[score_apply] " .. intro .. "\n")

  if auto_n == 0 then
    reaper.MB(intro .. "\n\n均为手动项（换素材/相位解耦等），请查看报告。", "RS-PASS 轨级建议", 0)
    return false, "仅手动建议"
  end

  local choice = reaper.MB(
    intro .. "\n\n一键应用所有【可自动】项？\n（音量微调 / 1_rain 包络 / Group HF EQ）\n\nYes=应用  No=仅看建议",
    "RS-PASS 轨级建议",
    4
  )
  if choice ~= 6 then
    return false, "用户跳过"
  end

  local applied, skipped, failed = M.apply_actions(actions, ctx, { only_auto = true })
  local msg = ""
  if #applied > 0 then
    msg = msg .. "已应用:\n· " .. table.concat(applied, "\n· ") .. "\n"
  end
  if #failed > 0 then
    msg = msg .. "\n失败:\n· " .. table.concat(failed, "\n· ") .. "\n"
  end
  if #skipped > 0 then
    msg = msg .. "\n仍须手动:\n· " .. table.concat(skipped, "\n· ") .. "\n"
  end
  msg = msg .. "\n建议 Ctrl+S 保存后重新打分验证。"
  reaper.MB(msg, "RS-PASS 一键修改", 0)
  return #applied > 0, msg
end

return M
