-- 仓库根目录解析（Reaper/scripts/ → Reaper/ → repo）

local M = {}

local function path_exists(p)
  if not p or p == "" then return false end
  if reaper.file_exists then return reaper.file_exists(p) end
  local fh = io.open(p, "rb")
  if fh then
    fh:close()
    return true
  end
  return false
end

local function scene_id_from_project()
  local _, name = reaper.GetProjectName(0, "")
  if name and name ~= "" then
    return name:gsub("%.rpp$", "")
  end
  return nil
end

local function rain_project_root(dir)
  if not dir or dir == "" then return nil end
  local sep = M.sep()
  local scenes = dir .. sep .. "scripts" .. sep .. "scenes"
  if path_exists(scenes) then return dir end
  return nil
end

local function legacy_project_with_config(dir)
  if not dir or dir == "" then return nil end
  local sep = M.sep()
  local cfg = dir .. sep .. "scripts" .. sep .. "asmr_config.lua"
  if path_exists(cfg) then return dir end
  return nil
end

-- .rpp 所在目录（非 RECORD_PATH「Audio Files」子目录）
function M.project_root()
  local proj = reaper.GetProjectPath("")
  if proj and proj ~= "" then
    local found = rain_project_root(proj)
    if found then return found end
    found = legacy_project_with_config(proj)
    if found then return found end
    local parent = proj:match("^(.+)[\\/]Audio Files$")
    if parent then
      found = rain_project_root(parent) or legacy_project_with_config(parent)
      if found then return found end
    end
  end
  local _, script_path = reaper.get_action_context()
  if script_path and script_path ~= "" then
    local d = script_path:match("^(.+)[\\/]scripts[\\/]")
    if d then return d end
  end
  return proj
end

function M.repo_root()
  local proj = reaper.GetProjectPath("")
  if proj and proj ~= "" then
    local root = proj:match("^(.+)[\\/]Reaper[\\/]")
    if root then return root end
    root = proj:match("^\\\\wsl%.localhost\\[^\\]+\\(.+)[\\/]Reaper[\\/]")
    if root then
      return "\\\\wsl.localhost\\" .. (proj:match("^\\\\wsl%.localhost\\([^\\]+)\\") or "Ubuntu") .. "\\" .. root:gsub("/", "\\")
    end
    root = proj:match("^\\\\wsl$\\[^\\]+\\(.+)[\\/]Reaper[\\/]")
    if root then return proj:match("^\\\\wsl$\\[^\\]+\\") .. root:gsub("/", "\\") end
  end
  local _, script_path = reaper.get_action_context()
  if script_path and script_path ~= "" then
    local root = script_path:match("^(.+)[\\/]Reaper[\\/]")
    if root then return root end
  end
  return nil
end

function M.sep()
  return package.config:sub(1, 1)
end

function M.project_dir()
  return M.project_root()
end

function M.resolve_asset(rel_path, repo_root)
  if not rel_path or rel_path == "" then return nil end
  if rel_path:match("^[%a]:") or rel_path:match("^/") or rel_path:match("^\\\\") then
    return rel_path
  end
  local proj = M.project_root()
  if proj then
    local from_proj = proj .. M.sep() .. rel_path:gsub("/", M.sep())
    if path_exists(from_proj) then
      return from_proj
    end
  end
  if repo_root then
    return repo_root .. M.sep() .. rel_path:gsub("/", M.sep())
  end
  return rel_path
end

function M.project_scripts_dir()
  local root = M.project_root()
  if not root or root == "" then return nil end
  return root .. M.sep() .. "scripts"
end

function M.scene_config_path()
  local scripts_dir = M.project_scripts_dir()
  if not scripts_dir then return nil, "无法定位工程 scripts 目录（请先保存 .rpp）" end
  local sep = M.sep()
  local sid = scene_id_from_project()
  if sid and sid ~= "" then
    local scene_cfg = scripts_dir .. sep .. "scenes" .. sep .. sid .. ".lua"
    if path_exists(scene_cfg) then return scene_cfg end
  end
  local legacy = scripts_dir .. sep .. "asmr_config.lua"
  if path_exists(legacy) then return legacy end
  if sid and sid ~= "" then
    return scripts_dir .. sep .. "scenes" .. sep .. sid .. ".lua"
  end
  return legacy
end

function M.load_asmr_config()
  local cfg_path, err = M.scene_config_path()
  if not cfg_path then return nil, err end
  local f = loadfile(cfg_path)
  if not f then return nil, "找不到: " .. cfg_path end
  return f(), cfg_path
end

--- 按层 id 找轨（Group 父轨占 index 0 时仍正确）
function M.track_for_layer(spec)
  if not spec then return nil end
  local id = spec.id
  if id then
    for i = 0, reaper.CountTracks(0) - 1 do
      local tr = reaper.GetTrack(0, i)
      local _, name = reaper.GetSetMediaTrackInfo_String(tr, "P_NAME", "", false)
      if name == id then return tr end
    end
  end
  local n = spec.track
  if n and n >= 1 then
    local tr = reaper.GetTrack(0, n)
    if tr then return tr end
    return reaper.GetTrack(0, n - 1)
  end
  return nil
end

return M
