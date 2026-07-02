-- @description ASMR · RS-PASS 混音打分（选中区间 / 整工程前 N 秒）
-- @version 1.1
-- @author relaxASMR
-- @about
--   将当前混音渲染为临时 WAV，调用本仓库 benchmark/（经 scoring_bridge.py）做 RS-PASS 打分。
--   · 有时间选区 → 打分选区（最长 300s，可在 ExtState relaxASMR/score_duration 修改）
--   · 无选区 → 从工程开头分析前 N 秒
--   报告写入 <工程>/output/scoring/ · 需已保存 .rpp · 需 python3 + ffmpeg

local r = reaper

local DEFAULT_DURATION = 300.0
local REPORT_STEM = "mix_score"

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

local function path_exists(p)
  if not p or p == "" then return false end
  if r.file_exists then return r.file_exists(p) end
  local fh = io.open(p, "rb")
  if fh then fh:close(); return true end
  return false
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

local function win_quote(s)
  return '"' .. tostring(s):gsub('"', '\\"') .. '"'
end

local function project_rpp_path(sep)
  local dir = r.GetProjectPath("")
  if not dir or dir == "" then return nil end
  local _, name = r.GetProjectName(0, "")
  if not name or name == "" then return nil end
  if not name:match("%.rpp$") and not name:match("%.RPP$") then
    name = name .. ".rpp"
  end
  return dir .. sep .. name
end

local function get_time_range(max_dur)
  local ts_start, ts_end = r.GetSet_LoopTimeRange2(0, false, 0, 0, false)
  local has_ts = (ts_end - ts_start) > 0.001
  local range_start, range_end, label
  if has_ts then
    range_start = ts_start
    range_end = ts_end
    label = string.format("选中区间 %.1f–%.1f s", range_start, range_end)
  else
    range_start = 0
    range_end = r.GetProjectLength(0)
    label = string.format("整工程（前 %.0f s）", max_dur)
  end
  local range_len = math.max(0, range_end - range_start)
  if range_len < 0.05 then
    return nil, nil, nil, "工程时长过短或选区无效"
  end
  local analyze_len = math.min(range_len, max_dur)
  local render_end = range_start + analyze_len
  return range_start, render_end, label, nil
end

local function save_render_state()
  local rv, file = r.GetSetProjectInfo_String(0, "RENDER_FILE", "", false)
  return {
    bounds = r.GetSetProjectInfo(0, "RENDER_BOUNDSFLAG", 0, false),
    start = r.GetSetProjectInfo(0, "RENDER_STARTPOS", 0, false),
    ["end"] = r.GetSetProjectInfo(0, "RENDER_ENDPOS", 0, false),
    file = file or "",
    format = r.GetSetProjectInfo(0, "RENDER_FORMAT", 0, false),
    channels = r.GetSetProjectInfo(0, "RENDER_CHANNELS", 0, false),
    srate = r.GetSetProjectInfo(0, "RENDER_SRATE", 0, false),
    tail = r.GetSetProjectInfo(0, "RENDER_TAILFLAG", 0, false),
  }
end

local function restore_render_state(st)
  if not st then return end
  r.GetSetProjectInfo(0, "RENDER_BOUNDSFLAG", st.bounds, true)
  r.GetSetProjectInfo(0, "RENDER_STARTPOS", st.start, true)
  r.GetSetProjectInfo(0, "RENDER_ENDPOS", st["end"], true)
  r.GetSetProjectInfo_String(0, "RENDER_FILE", st.file, true)
  r.GetSetProjectInfo(0, "RENDER_FORMAT", st.format, true)
  r.GetSetProjectInfo(0, "RENDER_CHANNELS", st.channels, true)
  r.GetSetProjectInfo(0, "RENDER_SRATE", st.srate, true)
  r.GetSetProjectInfo(0, "RENDER_TAILFLAG", st.tail, true)
end

local function render_mix(start_t, end_t, out_wav, sr)
  local saved = save_render_state()
  r.PreventUIRefresh(1)
  r.Undo_BeginBlock()
  r.GetSetProjectInfo_String(0, "RENDER_FILE", out_wav, true)
  r.GetSetProjectInfo(0, "RENDER_FORMAT", 0, true)       -- WAV
  r.GetSetProjectInfo(0, "RENDER_CHANNELS", 2, true)     -- stereo
  r.GetSetProjectInfo(0, "RENDER_SRATE", sr, true)
  r.GetSetProjectInfo(0, "RENDER_TAILFLAG", 0, true)
  r.GetSetProjectInfo(0, "RENDER_BOUNDSFLAG", 0, true)   -- custom range
  r.GetSetProjectInfo(0, "RENDER_STARTPOS", start_t, true)
  r.GetSetProjectInfo(0, "RENDER_ENDPOS", end_t, true)

  local ok = false
  if type(r.RenderProjectSection) == "function" then
    ok = r.RenderProjectSection(0, start_t, end_t, out_wav, 0, sr, 2, 0, 0)
  end
  if not ok then
    -- 41885: Render project, auto-close dialog
    r.Main_OnCommand(41885, 0)
    ok = path_exists(out_wav)
  end

  restore_render_state(saved)
  r.Undo_EndBlock("RS-PASS preview render", -1)
  r.PreventUIRefresh(-1)
  return ok
end

local function build_score_command(repo_root, sep, wav_path, out_dir, rpp_path, duration, summary_path)
  local bridge = repo_root .. sep .. "scripts" .. sep .. "video_export" .. sep .. "scoring_bridge.py"
  if not path_exists(bridge) then
    return nil, "找不到 scoring_bridge.py:\n" .. bridge
  end

  local args = string.format(
    "%s --output-dir %s --duration %.0f --report-stem %s --summary-file %s",
    bash_quote(wav_path),
    bash_quote(out_dir),
    duration,
    REPORT_STEM,
    bash_quote(summary_path)
  )
  if rpp_path and path_exists(rpp_path) then
    args = args .. " --rpp " .. bash_quote(rpp_path)
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
    local cmd = string.format('wsl -d %s bash -lc %s', distro or "Ubuntu", bash_quote(inner))
    return cmd, nil
  end

  -- 原生 Linux / macOS / Windows python
  local py = "python3"
  if package.config:sub(1, 1) == "\\" then py = "python" end
  local parts = { py, win_quote(bridge), win_quote(wav_path) }
  if rpp_path and path_exists(rpp_path) then
    parts[#parts + 1] = "--rpp"
    parts[#parts + 1] = win_quote(rpp_path)
  end
  parts[#parts + 1] = "--output-dir"
  parts[#parts + 1] = win_quote(out_dir)
  parts[#parts + 1] = string.format("--duration %.0f", duration)
  parts[#parts + 1] = "--report-stem"
  parts[#parts + 1] = REPORT_STEM
  parts[#parts + 1] = "--summary-file"
  parts[#parts + 1] = win_quote(summary_path)
  return table.concat(parts, " "), nil
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

local function load_score_apply()
  return load_module("asmr_score_apply.lua")
end

local function load_vol_envelope()
  return load_module("asmr_vol_envelope.lua")
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

-- ── main ─────────────────────────────────────────────────────

local function main()
  local paths = load_paths()
  if not paths then
    r.MB("无法加载 asmr_paths.lua", "RS-PASS 打分", 0)
    return
  end

  local sep = paths.sep()
  local repo_root = paths.repo_root()
  if not repo_root then
    r.MB("无法定位仓库根目录（工程需在 Reaper/Projects/... 下）", "RS-PASS 打分", 0)
    return
  end

  if r.GetProjectPath("") == "" then
    r.MB("请先保存工程 (.rpp)，再运行打分。", "RS-PASS 打分", 0)
    return
  end

  local duration = score_duration()
  local t0, t1, range_label, err = get_time_range(duration)
  if err then
    r.MB(err, "RS-PASS 打分", 0)
    return
  end

  local proj_root = paths.project_root()
  if not proj_root then proj_root = r.GetProjectPath("") end
  local out_dir = proj_root .. sep .. "output" .. sep .. "scoring"
  if not ensure_dir(out_dir) then
    r.MB("无法创建输出目录:\n" .. out_dir, "RS-PASS 打分", 0)
    return
  end

  local wav_path = out_dir .. sep .. "_mix_preview.wav"
  local summary_path = out_dir .. sep .. "mix_score_summary.txt"
  local rpp_path = project_rpp_path(sep)
  local sr = math.floor(r.GetSetProjectInfo(0, "PROJECT_SRATE", 48000, false))
  if sr < 8000 then sr = 48000 end

  local ok_render = r.MB(
    string.format(
      "RS-PASS 混音打分\n\n范围: %s\n分析时长: ≤ %.0f s\n输出: %s\n\n继续？",
      range_label,
      duration,
      out_dir
    ),
    "RS-PASS 打分",
    1
  )
  if ok_render ~= 1 then return end

  r.SetCursorContext(0, t0)
  log(string.format("渲染 %.3f – %.3f s → %s", t0, t1, wav_path))
  if not render_mix(t0, t1, wav_path, sr) then
    r.MB("混音渲染失败。请检查 Render 设置或手动 Render 后再试。", "RS-PASS 打分", 0)
    return
  end

  local cmd, cmd_err = build_score_command(repo_root, sep, wav_path, out_dir, rpp_path, duration, summary_path)
  if not cmd then
    r.MB(cmd_err or "无法构建打分命令", "RS-PASS 打分", 0)
    return
  end

  log("执行: " .. cmd)
  local exec_fn = r.ExecProcess or io.popen
  local output = ""
  if r.ExecProcess then
    output = r.ExecProcess(cmd, 600000) or ""
  else
    local p = io.popen(cmd .. " 2>&1")
    if p then
      output = p:read("*a") or ""
      p:close()
    end
  end
  if output ~= "" then log(output) end

  local summary = read_summary(summary_path)
  if not summary or not summary.total_score then
    r.MB(
      "打分失败。请确认:\n"
        .. "· python3 可用\n"
        .. "· ffmpeg / ffprobe 已安装\n"
        .. "· benchmark/ 目录完整\n"
        .. "· Reaper 控制台有详细日志",
      "RS-PASS 打分",
      0
    )
    return
  end

  local weak = format_weak_dims(summary.weak_dims)
  local msg = string.format(
    "RS-PASS 混音打分\n\n"
      .. "范围: %s\n"
      .. "综合分: %s / 100  (%s)\n"
      .. "RS-PASS: %s · 类型贴合: %s\n"
      .. "噪声类型: %s · 模式: %s\n"
      .. "分析: %.0f s\n",
    range_label,
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
  msg = msg .. "\n报告:\n" .. (summary.report_md or (out_dir .. sep .. REPORT_STEM .. ".md"))

  r.MB(msg, "RS-PASS 打分", 0)

  -- 轨级建议 + 可选一键修改
  local actions_path = summary.actions_lua
  if actions_path and actions_path ~= "" and path_exists(actions_path) then
    local apply_mod = load_score_apply()
    local vol_mod = load_vol_envelope()
    if apply_mod then
      local actions, err = apply_mod.load_actions(actions_path)
      if actions then
        apply_mod.prompt_and_apply(actions, {
          sep = sep,
          project_root = proj_root,
          repo_root = repo_root,
          vol_mod = vol_mod,
          total_sec = r.GetProjectLength(0),
        })
      else
        log("无法加载 actions: " .. tostring(err))
      end
    end
  end
end

main()
