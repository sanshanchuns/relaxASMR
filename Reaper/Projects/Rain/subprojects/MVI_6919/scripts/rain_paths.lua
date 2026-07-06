-- 路径解析：脚本 → Rain → Projects → Reaper → repo 根

local M = {}

function M.repo_root()
  local _, script_path = reaper.get_action_context()
  if script_path and script_path ~= "" then
    local root = script_path:match("^(.+)[\\/]Reaper[\\/]")
    if root then return root end
    -- subprojects/MVI_6918/scripts/ → up to Rain
    local rain = script_path:match("^(.+)[\\/]subprojects[\\/]")
    if rain then
      root = rain:match("^(.+)[\\/]Reaper[\\/]")
      if root then return root end
    end
  end
  return nil
end

function M.sep()
  return package.config:sub(1, 1)
end

function M.resolve_asset(rel_path, repo_root)
  if not rel_path or rel_path == "" then return nil end
  if rel_path:match("^[%a]:") or rel_path:match("^/") or rel_path:match("^\\\\") then
    return rel_path
  end
  if not repo_root then return rel_path end
  return repo_root .. M.sep() .. rel_path:gsub("/", M.sep())
end

return M
