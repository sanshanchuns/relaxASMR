-- @description ASMR · Group 总线削高频（安全感）
-- @version 2.1
-- @about
--   Group 轨添加/刷新 JS「ASMR Sleep HF EQ」。
--   Windows Reaper 无法直接加载 WSL 路径时，会复制到 Reaper/Effects/relaxASMR/。

local r = reaper

local JS_NAME = "ASMR Sleep HF EQ"
local JS_FILE = "asmr_sleep_hf_eq.jsfx"
local JS_SUBDIR = "relaxASMR"

local DEFAULTS = { 120, -3, 3500, 1.2, -5, 6000, 0.8, -4, 8000 }

local function log(msg)
  r.ShowConsoleMsg("[group_eq] " .. msg .. "\n")
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

local function path_sep(p)
  if p and p:match("^/") then return "/" end
  if p and p:match("^\\\\") then return "\\" end
  return package.config:sub(1, 1)
end

local function readable(path)
  if not path then return false end
  if r.file_exists and r.file_exists(path) then return true end
  local fh = io.open(path, "rb")
  if fh then
    fh:close()
    return true
  end
  return false
end

local function copy_file(src, dest)
  local in_f = io.open(src, "rb")
  if not in_f then return false end
  local data = in_f:read("*a")
  in_f:close()
  local out_f = io.open(dest, "wb")
  if not out_f then return false end
  out_f:write(data)
  out_f:close()
  return true
end

local function ensure_dir(dir)
  os.execute(string.format('mkdir "%s" 2>nul', dir:gsub("/", "\\")))
  os.execute(string.format('mkdir -p "%s" 2>/dev/null', dir))
  return true
end

local function repo_js_candidates()
  local out = {}
  local seen = {}
  local function add(p)
    if p and not seen[p] then
      seen[p] = true
      out[#out + 1] = p
    end
  end

  local sep_lua = package.config:sub(1, 1)
  add(script_dir() .. sep_lua .. "fx" .. sep_lua .. JS_FILE)

  local pm = load_paths()
  if pm and pm.repo_root then
    local root = pm.repo_root()
    if root then
      local sep = path_sep(root)
      add(root .. sep .. "Reaper" .. sep .. "scripts" .. sep .. "fx" .. sep .. JS_FILE)
    end
  end

  local proj = r.GetProjectPath("")
  if proj and proj ~= "" then
    proj = proj:gsub("[\\/]Audio Files$", "")
    local sep = path_sep(proj)
    local root = proj:match("^(.+)[\\/]Reaper[\\/]")
    if root then
      add(root .. sep .. "Reaper" .. sep .. "scripts" .. sep .. "fx" .. sep .. JS_FILE)
    end
    local host, rest = proj:match("^\\\\wsl%.localhost\\([^\\]+)\\(.+)$")
    if host and rest then
      local rroot = rest:match("^(.+)[\\/]Reaper[\\/]")
      if rroot then
        add("\\\\wsl.localhost\\" .. host .. "\\" .. rroot:gsub("/", "\\") ..
          "\\Reaper\\scripts\\fx\\" .. JS_FILE)
      end
    end
    host, rest = proj:match("^\\\\wsl$\\([^\\]+)\\(.+)$")
    if host and rest then
      local rroot = rest:match("^(.+)[\\/]Reaper[\\/]")
      if rroot then
        add("\\\\wsl$\\" .. host .. "\\" .. rroot:gsub("/", "\\") ..
          "\\Reaper\\scripts\\fx\\" .. JS_FILE)
      end
    end
    local scripts = proj .. sep .. "scripts" .. sep .. "fx" .. sep .. JS_FILE
    add(scripts)
  end

  return out
end

local function find_jsfx_source()
  for _, p in ipairs(repo_js_candidates()) do
    if readable(p) then
      log("源文件: " .. p)
      return p
    end
  end
  return nil
end

local function resource_js_path()
  local res = r.GetResourcePath()
  local sep = path_sep(res)
  return res .. sep .. "Effects" .. sep .. JS_SUBDIR .. sep .. JS_FILE
end

local function install_jsfx_to_resource(src)
  local dest = resource_js_path()
  local sep = path_sep(dest)
  local dest_dir = dest:match("^(.+)[\\/]" .. JS_FILE .. "$")
  ensure_dir(dest_dir)
  if copy_file(src, dest) then
    log("已安装到: " .. dest)
    return dest
  end
  return nil
end

local function install_jsfx_to_project(src)
  local pm = load_paths()
  if not pm then return nil end
  local proj = pm.project_root()
  if not proj then return nil end
  local sep = path_sep(proj)
  local dest_dir = proj .. sep .. "scripts" .. sep .. "fx"
  ensure_dir(dest_dir)
  local dest = dest_dir .. sep .. JS_FILE
  if copy_file(src, dest) then
    log("已复制到工程: " .. dest)
    return dest
  end
  return nil
end

local function find_group_track()
  for i = 0, r.CountTracks(0) - 1 do
    local tr = r.GetTrack(0, i)
    local _, name = r.GetSetMediaTrackInfo_String(tr, "P_NAME", "", false)
    if name == "Group" then return tr end
  end
  return nil
end

local function find_fx(track, needle)
  for i = 0, r.TrackFX_GetCount(track) - 1 do
    local ok, name = r.TrackFX_GetFXName(track, i, "")
    if ok and name:find(needle, 1, true) then return i end
  end
  return -1
end

local function try_add_jsfx(track, path_or_name)
  local fx = r.TrackFX_AddByName(track, path_or_name, false, -1)
  if fx >= 0 then
    log("AddByName 成功: " .. path_or_name)
    return fx
  end
  return -1
end

local function add_jsfx(track, src)
  local names = {
    "JS:" .. JS_SUBDIR .. "/" .. JS_FILE:gsub("%.jsfx$", ""),
    "JS: " .. JS_NAME,
    "JS:" .. JS_SUBDIR .. "/" .. JS_FILE,
    JS_FILE,
  }

  local installed = install_jsfx_to_resource(src)
  if installed then names[#names + 1] = installed end

  local proj_copy = install_jsfx_to_project(src)
  if proj_copy then names[#names + 1] = proj_copy end

  for _, p in ipairs(repo_js_candidates()) do
    if readable(p) then names[#names + 1] = p end
  end

  for _, name in ipairs(names) do
    local fx = try_add_jsfx(track, name)
    if fx >= 0 then return fx end
  end
  return -1
end

local function set_js_params(track, fx)
  for i, v in ipairs(DEFAULTS) do
    r.TrackFX_SetParam(track, fx, i - 1, v)
  end
end

local function main()
  local tr = find_group_track()
  if not tr then
    r.ShowMessageBox("找不到名为 Group 的轨", "asmr_apply_group_eq", 0)
    return
  end

  local src = find_jsfx_source()
  if not src then
    r.ShowMessageBox(
      "找不到源文件 asmr_sleep_hf_eq.jsfx\n请确认 Reaper/scripts/fx/ 下存在该文件",
      "asmr_apply_group_eq",
      0
    )
    return
  end

  r.Undo_BeginBlock()

  local fx = find_fx(tr, "asmr_sleep_hf_eq")
  if fx < 0 then fx = find_fx(tr, JS_NAME) end
  if fx < 0 then
    fx = add_jsfx(tr, src)
  end
  if fx < 0 then
    r.Undo_EndBlock("ASMR Group EQ", -1)
    r.ShowMessageBox(
      "仍无法加载 JS FX。\n已尝试安装到:\n" .. resource_js_path() ..
        "\n请重启 Reaper 后再运行，或手动添加 Effects/relaxASMR 下的插件",
      "asmr_apply_group_eq",
      0
    )
    return
  end

  set_js_params(tr, fx)
  r.TrackFX_SetEnabled(tr, fx, true)

  local reaeq = find_fx(tr, "ReaEQ")
  if reaeq >= 0 and reaeq ~= fx then
    r.TrackFX_SetEnabled(tr, reaeq, false)
    log("已旁路 ReaEQ")
  end

  r.Undo_EndBlock("ASMR Group HF EQ", -1)
  r.ShowMessageBox(
    "Group 已配置 ASMR Sleep HF EQ\n（若首次安装，下次扫描 JS 后名称更稳定）",
    "asmr_apply_group_eq",
    0
  )
end

main()
