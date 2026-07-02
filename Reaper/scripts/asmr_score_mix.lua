-- @description ASMR · RS-PASS 混音打分（唯一入口 · 含轨级一键应用）
-- @version 2.5
-- @about
--   工作流：先在 Reaper Render 把混音导出到 `<工程>/output/`（或 output/score/），再运行本脚本。
-- @about
--   对已有 WAV 打分 → 结合 .rpp 生成修改建议 → 可选一键应用轨级调整。
--   报告：`<工程>/output/score/mix_score.md` · 需已保存 .rpp · python3 + ffmpeg

local r = reaper

local DEFAULT_DURATION = 300.0
local REPORT_STEM = "mix_score"
local PREVIEW_DIRNAME = "mix_preview.wav"

local DIM_ZH = {
  n5_peak_loudness = "N_5",
  s50_sharpness = "S_50",
  r5_roughness = "R_5",
  iacc = "IACC",
  f50_fluctuation = "F_50",
  si_irregularity = "SI",
  tmax_tonality = "T_max",
  crest_headroom = "Crest",
}

local function log(msg)
  r.ShowConsoleMsg("[score_mix] " .. msg .. "\n")
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

local function score_duration()
  local v = tonumber(r.GetExtState("relaxASMR", "score_duration"))
  if v and v > 0 then return v end
  return DEFAULT_DURATION
end

local function path_exists_file(p)
  if not p or p == "" then return false end
  if r.file_exists then return r.file_exists(p) end
  local fh = io.open(p, "rb")
  if fh then
    fh:close()
    return true
  end
  return false
end

local function path_exists(p)
  return path_exists_file(p)
end

local function is_wav_file(p)
  if not p or p == "" then return false end
  if not p:lower():match("%.wav$") then return false end
  if r.file_exists and r.file_exists(p) then
    return true
  end
  local fh = io.open(p, "rb")
  if fh then
    fh:close()
    return true
  end
  return false
end

local function is_readable_file(p)
  return is_wav_file(p) or path_exists_file(p)
end

local function normalize_project_dir(dir)
  if not dir or dir == "" then return nil end
  if dir:match("[\\/]Audio Files$") then
    return dir:match("^(.+)[\\/]Audio Files$")
  end
  return dir
end

local function basename_no_ext(path)
  if not path or path == "" then return nil end
  local name = path:match("([^/\\]+)$")
  if not name then return nil end
  return name:gsub("%.rpp$", "", 1):gsub("%.RPP$", "", 1)
end

-- GetProjectName 在部分 Reaper 版本/子工程下会为空，需从目录名或 .rpp 推断
local function project_stems(root)
  local stems, seen = {}, {}

  local function add(s)
    s = basename_no_ext(s)
    if s and s ~= "" and not seen[s] then
      seen[s] = true
      stems[#stems + 1] = s
    end
  end

  local _, name = r.GetProjectName(0, "")
  add(name)
  add(root)
  add(normalize_project_dir(r.GetProjectPath("")))

  return stems
end

local function project_stem(root)
  local stems = project_stems(root)
  if #stems > 0 then return stems[1] end
  return "mix"
end

local function shell_quote(s)
  return "'" .. tostring(s):gsub("'", "'\\''") .. "'"
end

local function run_shell(cmd, timeout_ms)
  timeout_ms = timeout_ms or 600000
  if not r.ExecProcess then
    local p = io.popen(cmd .. " 2>&1")
    if not p then return nil, "io.popen failed" end
    local out = p:read("*a") or ""
    local ok = p:close()
    return ok and 0 or 1, out
  end

  local raw = r.ExecProcess(cmd, timeout_ms)
  if raw == nil or raw == "" then
    return nil, "ExecProcess returned empty (process not started?)"
  end
  if raw == "-999" or raw:match("^%-999\n?$") then
    return nil, "-999 (executable not found — macOS 需 /bin/sh 与 python3 绝对路径)"
  end

  local code_str, body = raw:match("^(-?%d+)\r?\n(.*)$")
  if not code_str then
    return 0, raw
  end
  return tonumber(code_str), body or ""
end

local function resolve_python3()
  local ext = r.GetExtState("relaxASMR", "python3_path")
  if ext and ext ~= "" and is_readable_file(ext) then
    return ext
  end

  local _, pyenv_py = run_shell(
    "/bin/sh -c "
      .. shell_quote(
        'ls -1d "$HOME/.pyenv/versions/"*/bin/python3 2>/dev/null | sort -V | tail -1'
      ),
    10000
  )
  if pyenv_py then
    local p = pyenv_py:match("(%S+)")
    if p and is_readable_file(p) then
      return p
    end
  end

  for _, p in ipairs({
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
    "/usr/bin/python3",
  }) do
    if is_readable_file(p) then return p end
  end

  local _, which_py = run_shell("/bin/bash -lc 'command -v python3'", 10000)
  if which_py then
    local p = which_py:match("(%S+)")
    if p and is_readable_file(p) and not p:match("/%.pyenv/shims/") then
      return p
    end
  end
  return nil
end

local function ensure_dir(dir)
  if path_exists(dir) then return true end
  if r.RecursiveCreateDirectory then
    return r.RecursiveCreateDirectory(dir, 0)
  end
  return false
end

local function wsl_to_unix(win_path)
  if not win_path then return nil, nil end
  local distro, tail = win_path:match("^\\\\wsl%.localhost\\([^\\]+)\\(.*)$")
  if not distro then
    distro, tail = win_path:match("^\\\\wsl$\\([^\\]+\\(.*)$")
  end
  if not tail then return nil, nil end
  return distro, tail:gsub("\\", "/")
end

local function is_wsl_unc(p)
  return p and (p:match("^\\\\wsl%.localhost\\") or p:match("^\\\\wsl$\\")) ~= nil
end

local function bash_quote(s)
  return "'" .. tostring(s):gsub("'", "'\\''") .. "'"
end

local function resolve_rpp_path(sep, proj_root)
  local dir = normalize_project_dir(proj_root) or normalize_project_dir(r.GetProjectPath(""))
  if not dir or dir == "" then return nil end

  local _, name = r.GetProjectName(0, "")
  if name and name ~= "" then
    if not name:match("%.rpp$") and not name:match("%.RPP$") then
      name = name .. ".rpp"
    end
    local p = dir .. sep .. name
    if path_exists_file(p) then return p end
  end

  local folder = dir:match("([^/\\]+)$")
  if folder then
    local p = dir .. sep .. folder .. ".rpp"
    if path_exists_file(p) then return p end
  end

  return dir .. sep .. (folder or "project") .. ".rpp"
end

local function collect_project_roots(paths, sep)
  local roots, seen = {}, {}

  local function add(p)
    p = normalize_project_dir(p)
    if p and p ~= "" and not seen[p] then
      seen[p] = true
      roots[#roots + 1] = p
    end
  end

  add(r.GetProjectPath(""))
  add(paths and paths.project_root())
  local rpp = resolve_rpp_path(sep, nil)
  if rpp then
    add(rpp:match("^(.+)[\\/][^\\/]+$"))
  end

  return roots
end

local function output_root(proj_root, sep)
  return proj_root .. sep .. "output"
end

local function score_out_dir(proj_root, sep)
  return output_root(proj_root, sep) .. sep .. "score"
end

local function newest_wav_in_dir(dir)
  if not dir or dir == "" then return nil end
  local cmd = "/bin/sh -c "
    .. shell_quote(string.format(
      "find %s -type f -name '*.wav' -print0 2>/dev/null | xargs -0 ls -t 2>/dev/null | head -1",
      dir:gsub("'", "'\\''")
    ))
  local _, body = run_shell(cmd, 30000)
  if not body or body == "" then return nil end
  local p = body:match("^%s*(.-)%s*$")
  if p and is_wav_file(p) then
    return p
  end
  return nil
end

local function wav_candidates_for_root(root, sep, stem)
  local out_dir = output_root(root, sep)
  local score_dir = score_out_dir(root, sep)
  return {
    out_dir .. sep .. stem .. ".wav",
    out_dir .. sep .. PREVIEW_DIRNAME .. sep .. stem .. ".wav",
    out_dir .. sep .. PREVIEW_DIRNAME .. sep .. stem .. "_1.wav",
    score_dir .. sep .. stem .. ".wav",
    score_dir .. sep .. PREVIEW_DIRNAME .. sep .. stem .. ".wav",
    score_dir .. sep .. PREVIEW_DIRNAME .. sep .. stem .. "_1.wav",
    score_dir .. sep .. "_mix_preview.wav" .. sep .. stem .. ".wav",
  }, out_dir, score_dir
end

local function direct_output_wav(root, sep)
  local out_dir = output_root(root, sep)
  for _, stem in ipairs(project_stems(root)) do
    local p = out_dir .. sep .. stem .. ".wav"
    if is_wav_file(p) then
      return p
    end
  end
  return nil
end

-- 用户手动 Render 后常见路径：output/$project.wav 或 output/score/mix_preview.wav/$project.wav
local function find_score_wav(paths, sep)
  local tried = {}

  for _, root in ipairs(collect_project_roots(paths, sep)) do
    local out_dir = output_root(root, sep)
    local score_dir = score_out_dir(root, sep)

    local direct = direct_output_wav(root, sep)
    if direct then
      log("找到 WAV: " .. direct)
      return direct, root
    end

    for _, stem in ipairs(project_stems(root)) do
      local candidates = wav_candidates_for_root(root, sep, stem)
      for _, p in ipairs(candidates) do
        tried[#tried + 1] = p
        if is_wav_file(p) then
          log("找到 WAV: " .. p)
          return p, root
        end
      end
    end

    local newest = newest_wav_in_dir(out_dir) or newest_wav_in_dir(score_dir)
    if newest then
      log("找到 WAV（最新）: " .. newest)
      return newest, root
    end
  end

  for _, p in ipairs(tried) do
    log("未命中: " .. p)
  end
  return nil, nil
end

local function build_score_command(repo_root, sep, wav_path, out_dir, rpp_path, duration, summary_path)
  local bridge = repo_root .. sep .. "scripts" .. sep .. "video_export" .. sep .. "scoring_bridge.py"
  if not is_readable_file(bridge) then
    return nil, "找不到 scoring_bridge.py:\n" .. bridge
  end

  if is_wsl_unc(repo_root) or is_wsl_unc(wav_path) then
    local distro, unix_bridge = wsl_to_unix(bridge)
    local _, unix_wav = wsl_to_unix(wav_path)
    local _, unix_out = wsl_to_unix(out_dir)
    local _, unix_sum = wsl_to_unix(summary_path)
    local unix_rpp = nil
    if rpp_path then
      _, unix_rpp = wsl_to_unix(rpp_path)
    end
    if not unix_bridge then
      return nil, "无法解析 WSL 路径"
    end
    local inner = string.format(
      "python3 %s %s --output-dir %s --duration %.0f --report-stem %s --summary-file %s",
      bash_quote(unix_bridge),
      bash_quote(unix_wav),
      bash_quote(unix_out),
      duration,
      REPORT_STEM,
      bash_quote(unix_sum)
    )
    if unix_rpp then
      inner = inner .. " --rpp " .. bash_quote(unix_rpp)
    end
    return string.format('wsl -d %s bash -lc %s', distro or "Ubuntu", bash_quote(inner)), nil
  end

  local py = resolve_python3()
  if not py then
    return nil, "找不到 python3。可在 Reaper ExtState 设置 relaxASMR/python3_path"
  end

  local parts = {
    shell_quote(py),
    shell_quote(bridge),
    shell_quote(wav_path),
    "--output-dir", shell_quote(out_dir),
    string.format("--duration %.0f", duration),
    "--report-stem", REPORT_STEM,
    "--summary-file", shell_quote(summary_path),
  }
  if rpp_path and path_exists(rpp_path) then
    parts[#parts + 1] = "--rpp"
    parts[#parts + 1] = shell_quote(rpp_path)
  end

  if package.config:sub(1, 1) == "\\" then
    return table.concat(parts, " "), nil
  end
  return "/bin/sh -c " .. shell_quote(table.concat(parts, " ")), nil
end

local function read_summary(path)
  local fh = io.open(path, "r")
  if not fh then return nil end
  local data = {}
  for line in fh:lines() do
    local k, v = line:match("^([^=]+)=(.*)$")
    if k then data[k] = v end
  end
  fh:close()
  return data
end

local function load_module(name)
  local f = loadfile(script_dir() .. package.config:sub(1, 1) .. name)
  if not f then return nil end
  return f()
end

local function format_weak_dims(raw)
  if not raw or raw == "" then return "" end
  local parts = {}
  for pair in raw:gmatch("[^,]+") do
    local k, v = pair:match("^([^=]+)=(.+)$")
    if k and DIM_ZH[k] then
      parts[#parts + 1] = DIM_ZH[k] .. " " .. v
    end
  end
  return table.concat(parts, " · ")
end

-- ── 轨级建议 · 一键应用 ────────────────────────────────────────

local Apply = {}

function Apply.track_by_name(name)
  if not name or name == "" then return nil end
  local lname = name:lower()
  for i = 0, r.CountTracks(0) - 1 do
    local tr = r.GetTrack(0, i)
    local _, n = r.GetSetMediaTrackInfo_String(tr, "P_NAME", "", false)
    if n == name or n:lower() == lname then return tr end
    if n:match("^" .. name) or n:lower():match("^" .. lname) then return tr end
  end
  return nil
end

function Apply.group_track()
  return Apply.track_by_name("Group") or Apply.track_by_name("group")
end

function Apply.track_has_fx_name(track, needle)
  if not track then return false end
  needle = needle:lower()
  local nfx = r.TrackFX_GetCount(track)
  for i = 0, nfx - 1 do
    local _, name = r.TrackFX_GetFXName(track, i, "")
    if name and name:lower():find(needle, 1, true) then return true end
  end
  return false
end

function Apply.resolve_fx_path(params, ctx)
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
    candidates[#candidates + 1] = ctx.repo_root .. sep .. "Reaper" .. sep .. "Projects" .. sep .. "Rain" .. sep .. "scripts" .. sep .. "fx" .. sep .. fx
  end
  for _, p in ipairs(candidates) do
    if is_readable_file(p) then return p end
  end
  return nil
end

function Apply.adjust_vol(track, factor)
  local v = r.GetMediaTrackInfo_Value(track, "D_VOL")
  r.SetMediaTrackInfo_Value(track, "D_VOL", v * factor)
  return true
end

function Apply.add_vol_envelope(track, total_sec, params, vol_mod)
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

local function read_jsfx_desc(fx_path)
  local fh = io.open(fx_path, "r")
  if not fh then return nil end
  local desc = nil
  for line in fh:lines() do
    local d = line:match("^desc:(.+)$")
    if d then
      desc = d:match("^%s*(.-)%s*$")
      break
    end
  end
  fh:close()
  return desc
end

local function ensure_jsfx_in_resource(src_path, rel_in_effects)
  if not src_path or not rel_in_effects then return nil end
  local res = r.GetResourcePath()
  if not res or res == "" then return nil end
  local sep = package.config:sub(1, 1)
  local dest = res .. sep .. "Effects" .. sep .. rel_in_effects:gsub("/", sep)
  if path_exists_file(dest) then return dest end

  local dest_dir = dest:match("^(.+)[\\/][^\\/]+$")
  if dest_dir then
    ensure_dir(dest_dir)
  end

  run_shell("/bin/cp -f " .. shell_quote(src_path) .. " " .. shell_quote(dest), 30000)
  if path_exists_file(dest) then
    log("已安装 JSFX → " .. dest)
    return dest
  end
  return nil
end

function Apply.add_fx(track, params, ctx)
  if Apply.track_has_fx_name(track, "asmr_sleep") or Apply.track_has_fx_name(track, "sleep hf") then
    return true, "已有 HF EQ，跳过"
  end
  local fx_path = Apply.resolve_fx_path(params, ctx)
  if not fx_path then
    return false, "找不到 FX: " .. tostring(params.fx)
  end

  local rel = params.js_name or ("relaxASMR/" .. (params.fx or "asmr_sleep_hf_eq.jsfx"))
  ensure_jsfx_in_resource(fx_path, rel)

  local desc = read_jsfx_desc(fx_path)
  local fname = params.fx or "asmr_sleep_hf_eq.jsfx"
  local attempts = {}
  if desc then attempts[#attempts + 1] = "JS: " .. desc end
  attempts[#attempts + 1] = "JS: " .. rel
  attempts[#attempts + 1] = "JS: " .. fname

  for _, name in ipairs(attempts) do
    local idx = r.TrackFX_AddByName(track, name, false, -1)
    if idx and idx >= 0 then
      log("add_fx OK: " .. name)
      return true, "已添加 " .. (desc or fname)
    end
  end

  return false, "TrackFX_AddByName 失败（请手动在 Group 添加 JS: ASMR Sleep HF EQ）"
end

function Apply.track_by_config_num(n)
  if not n or n < 1 then return nil end
  -- Group 占 index 0 时，配方 track=N 对应 GetTrack(0, N)（如 1_rain → track 1 → index 1）
  local tr = r.GetTrack(0, n)
  if tr then
    local _, nm = r.GetSetMediaTrackInfo_String(tr, "P_NAME", "", false)
    local low = (nm or ""):lower()
    if low ~= "group" and low ~= "video" then
      return tr
    end
  end
  return r.GetTrack(0, n - 1)
end

function Apply.resolve_track(action, ctx)
  ctx = ctx or {}
  local target = action.target or "track"
  if target == "group" or action.track_name == "Group" then
    return Apply.group_track(), "Group"
  end

  -- Reaper 轨名是 layer_id（1_rain），不是配方里的中文 track_name
  local lid = action.layer_id
  if lid and lid ~= "" then
    local tr = Apply.track_by_name(lid)
    if tr then return tr, lid end
  end

  local paths = ctx.paths
  if paths and paths.track_for_layer and lid and lid ~= "" then
    local tr = paths.track_for_layer({ id = lid, track = action.track })
    if tr then return tr, lid end
  end

  local tname = action.track_name
  if tname and tname ~= "" then
    local tr = Apply.track_by_name(tname)
    if tr then return tr, tname end
  end

  if action.track then
    local tr = Apply.track_by_config_num(action.track)
    if tr then
      local _, nm = r.GetSetMediaTrackInfo_String(tr, "P_NAME", "", false)
      return tr, nm or lid or tname or ("track" .. action.track)
    end
  end

  return nil, lid or tname or "?"
end

function Apply.load_actions(actions_path)
  local f, err = loadfile(actions_path)
  if not f then return nil, err or "loadfile 失败" end
  return f()
end

function Apply.format_actions_list(actions)
  local lines = {}
  for i, act in ipairs(actions or {}) do
    local tag = act.auto_apply and "[可自动]" or "[手动]"
    local pri = act.priority and ("(" .. act.priority .. ")") or ""
    lines[#lines + 1] = string.format("%d. %s %s %s", i, tag, pri, act.text or act.reason or "?")
  end
  return table.concat(lines, "\n")
end

function Apply.apply_actions(actions, ctx, opts)
  opts = opts or {}
  local only_auto = opts.only_auto ~= false
  local vol_mod = ctx.vol_mod
  local total_sec = ctx.total_sec or r.GetProjectLength(0)
  local applied, skipped, failed = {}, {}, {}

  r.Undo_BeginBlock()
  r.PreventUIRefresh(1)
  local ok, err = pcall(function()
    for _, act in ipairs(actions or {}) do
      if act.action == "note" then
        skipped[#skipped + 1] = act.text or act.reason
      elseif only_auto and not act.auto_apply then
        skipped[#skipped + 1] = (act.text or act.reason) .. "（需手动）"
      else
        local track, tname = Apply.resolve_track(act, ctx)
        if not track and act.action ~= "note" then
          failed[#failed + 1] = (act.text or "?") .. " → 找不到轨"
        elseif act.action == "adjust_vol" then
          local factor = (act.params or {}).factor or 1.0
          Apply.adjust_vol(track, factor)
          applied[#applied + 1] = string.format("%s ×%.2f", tname, factor)
          log("apply_vol " .. tname .. " ×" .. factor)
        elseif act.action == "add_vol_envelope" then
          local ok_env, msg = Apply.add_vol_envelope(track, total_sec, act.params or {}, vol_mod)
          if ok_env then applied[#applied + 1] = tname .. ": " .. msg
          else failed[#failed + 1] = tname .. ": " .. msg end
        elseif act.action == "add_fx" then
          local ok_fx, msg = Apply.add_fx(track, act.params or {}, ctx)
          if ok_fx then applied[#applied + 1] = (tname or "Group") .. ": " .. msg
          else failed[#failed + 1] = (tname or "Group") .. ": " .. msg end
        else
          skipped[#skipped + 1] = act.text or act.action
        end
      end
    end
  end)
  r.PreventUIRefresh(-1)
  r.Undo_EndBlock("RS-PASS apply track fixes", -1)
  r.UpdateArrange()
  if not ok then
    failed[#failed + 1] = tostring(err)
  end

  return applied, skipped, failed
end

function Apply.prompt_and_apply(actions, ctx)
  if not actions or #actions == 0 then
    return false, "无轨级修改建议"
  end

  local auto_n = 0
  for _, a in ipairs(actions) do
    if a.auto_apply and a.action ~= "note" then auto_n = auto_n + 1 end
  end

  local list = Apply.format_actions_list(actions)
  local intro = string.format(
    "轨级修改建议（共 %d 条，其中 %d 条可一键应用）:\n\n%s",
    #actions, auto_n, list
  )
  log(intro)

  if auto_n == 0 then
    r.MB(intro .. "\n\n均为手动项（换素材/相位解耦等），请查看 mix_score.md。", "RS-PASS 轨级建议", 0)
    return false, "仅手动建议"
  end

  local choice = r.MB(
    intro .. "\n\n一键应用所有【可自动】项？\n（音量微调 / 1_rain 包络 / Group HF EQ）\n\nYes=应用  No=仅看建议",
    "RS-PASS 轨级建议",
    4
  )
  if choice ~= 6 then return false, "用户跳过" end

  local applied, skipped, failed = Apply.apply_actions(actions, ctx, { only_auto = true })
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
  msg = msg .. "\n改完后重新 Render WAV，再运行打分验证。"
  r.MB(msg, "RS-PASS 一键修改", 0)
  return #applied > 0, msg
end

-- ── main ─────────────────────────────────────────────────────

local function fail(msg)
  r.MB(msg, "RS-PASS 打分", 0)
end

local function show_results(ctx, summary)
  local weak = format_weak_dims(summary.weak_dims)
  local msg = string.format(
    "RS-PASS 混音打分\n\n"
      .. "WAV: %s\n"
      .. "综合分: %s / 100  (%s)\n"
      .. "RS-PASS: %s · 类型贴合: %s\n"
      .. "噪声类型: %s · 模式: %s\n"
      .. "分析: %.0f s\n",
    ctx.wav_path,
    summary.total_score,
    summary.grade or "?",
    summary.rs_pass_score or "?",
    summary.type_fit_score or "?",
    summary.noise_type or "?",
    summary.mode or "?",
    tonumber(summary.duration_s) or 0
  )
  if weak ~= "" then
    msg = msg .. "\n最弱项: " .. weak .. "\n"
  end
  msg = msg .. "\n报告:\n" .. (summary.report_md or (ctx.out_dir .. ctx.sep .. REPORT_STEM .. ".md"))

  r.MB(msg, "RS-PASS 打分", 0)

  local actions_path = summary.actions_lua
  if actions_path and actions_path ~= "" and path_exists(actions_path) then
    r.defer(function()
      local vol_mod = load_module("asmr_vol_envelope.lua")
      local actions, err = Apply.load_actions(actions_path)
      if actions then
      Apply.prompt_and_apply(actions, {
        sep = ctx.sep,
        project_root = ctx.project_root,
        repo_root = ctx.repo_root,
        vol_mod = vol_mod,
        paths = load_paths(),
        total_sec = r.GetProjectLength(0),
      })
      else
        log("无法加载 mix_score_actions.lua: " .. tostring(err))
      end
    end)
  end
end

local function run_score(ctx)
  log("打分输入: " .. ctx.wav_path)

  local cmd, cmd_err = build_score_command(
    ctx.repo_root,
    ctx.sep,
    ctx.wav_path,
    ctx.out_dir,
    ctx.rpp_path,
    ctx.duration,
    ctx.summary_path
  )
  if not cmd then
    fail(cmd_err or "无法构建打分命令")
    return
  end

  log("执行: " .. cmd)
  local exit_code, output = run_shell(cmd, 600000)
  if output and output ~= "" then log(output) end
  if exit_code == nil then
    log("命令启动失败: " .. tostring(output))
  elseif exit_code ~= 0 then
    log(string.format("打分命令退出码 %s", tostring(exit_code)))
  end

  local summary = read_summary(ctx.summary_path)
  if not summary or not summary.total_score then
    fail(
      "打分失败。请确认:\n"
        .. "· python3 可用\n"
        .. "· ffmpeg / ffprobe 已安装\n"
        .. "· benchmark/ 目录完整\n"
        .. "· Reaper 控制台有详细日志"
    )
    return
  end

  r.defer(function() show_results(ctx, summary) end)
end

local function main()
  local paths = load_paths()
  if not paths then
    fail("无法加载 asmr_paths.lua")
    return
  end

  local sep = paths.sep()
  local repo_root = paths.repo_root()
  if not repo_root then
    fail("无法定位仓库根目录（工程需在 Reaper/Projects/... 下）")
    return
  end

  if r.GetProjectPath("") == "" then
    fail("请先保存工程 (.rpp)，再运行打分。")
    return
  end

  local proj_root = paths.project_root()
  local proj_path = normalize_project_dir(r.GetProjectPath(""))
  if not proj_root or proj_root == "" then proj_root = proj_path end
  if not proj_root or proj_root == "" then
    fail("无法定位工程目录（请先保存 .rpp）")
    return
  end

  local wav_path, wav_root = find_score_wav(paths, sep)
  if wav_root and wav_root ~= "" then
    proj_root = wav_root
  end

  local out_root = output_root(proj_root, sep)
  local out_dir = score_out_dir(proj_root, sep)
  if not ensure_dir(out_dir) then
    fail("无法创建输出目录:\n" .. out_dir)
    return
  end

  if not wav_path then
    fail(
      "未找到混音 WAV。\n\n"
        .. "工程目录: " .. proj_root .. "\n"
        .. "工程名: " .. project_stem(proj_root) .. "\n\n"
        .. "请先在 Reaper Render 导出到：\n"
        .. "· " .. out_root .. sep .. project_stem(proj_root) .. ".wav\n"
        .. "· 或 " .. out_dir .. "/\n\n"
        .. "（控制台 [score_mix] 有完整候选路径列表）"
    )
    return
  end

  local duration = score_duration()
  local summary_path = out_dir .. sep .. "mix_score_summary.txt"
  local rpp_path = resolve_rpp_path(sep, proj_root)

  local ok = r.MB(
    string.format(
      "RS-PASS 混音打分\n\n"
        .. "WAV: %s\n"
        .. "分析: 前 ≤ %.0f s\n"
        .. "工程: %s\n"
        .. "报告: %s\n\n"
        .. "继续打分？",
      wav_path,
      duration,
      rpp_path or "(未找到 .rpp)",
      out_dir
    ),
    "RS-PASS 打分",
    1
  )
  if ok ~= 1 then return end

  log("使用 WAV: " .. wav_path)

  local ctx = {
    sep = sep,
    repo_root = repo_root,
    project_root = proj_root,
    out_dir = out_dir,
    rpp_path = rpp_path,
    duration = duration,
    summary_path = summary_path,
    wav_path = wav_path,
  }

  r.defer(function() run_score(ctx) end)
end

main()
