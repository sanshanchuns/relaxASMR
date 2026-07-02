-- @description Rain · 首次建轨 + 插入素材（读 asmr_config.lua）
-- @version 1.0
-- @author relaxASMR

local r = reaper

local function log(msg)
  r.ShowConsoleMsg("[rain_bootstrap] " .. msg .. "\n")
end

local function get_scripts_dir()
  local _, script_path = r.get_action_context()
  if script_path and script_path ~= "" then
    return script_path:match("^(.+)[\\/][^\\/]+$")
  end
  return nil
end

local function load_paths()
  local scripts_dir = get_scripts_dir()
  if not scripts_dir then return nil end
  local sep = package.config:sub(1, 1)
  local f = loadfile(scripts_dir .. sep .. "rain_paths.lua")
  if not f then return nil end
  return f()
end

local function load_config()
  local scripts_dir = get_scripts_dir()
  if not scripts_dir then return nil, "无法定位 scripts 目录" end
  local sep = package.config:sub(1, 1)
  local cfg_path = scripts_dir .. sep .. "asmr_config.lua"
  local f = loadfile(cfg_path)
  if not f then return nil, "找不到 asmr_config.lua：" .. cfg_path end
  return f(), cfg_path
end

local function track_by_number(n)
  return r.GetTrack(0, n - 1)
end

local function ensure_tracks(cfg)
  local names = {}
  if cfg.video then
    names[cfg.video.track or 1] = cfg.video.name or "Video"
  end
  for _, layer in ipairs(cfg.loop_layers or {}) do
    names[layer.track] = layer.name or layer.id or ("轨" .. layer.track)
  end
  for _, layer in ipairs(cfg.scatter_layers or {}) do
    names[layer.track] = layer.name or layer.id or ("轨" .. layer.track)
  end
  local max_track = 0
  for t in pairs(names) do
    if t > max_track then max_track = t end
  end
  local count = r.CountTracks(0)
  while count < max_track do
    r.InsertTrackAtIndex(count, false)
    count = count + 1
  end
  for t, name in pairs(names) do
    local tr = track_by_number(t)
    if tr then r.GetSetMediaTrackInfo_String(tr, "P_NAME", name, true) end
  end
end

local function insert_media(track, abs_path, pos, vol, loop_src)
  if not abs_path or abs_path == "" then return false end
  local item = r.AddMediaItemToTrack(track)
  if not item then return false end
  local take = r.AddTakeToMediaItem(item)
  if not take then
    r.DeleteTrackMediaItem(track, item)
    return false
  end
  local src = r.PCM_Source_CreateFromFile(abs_path)
  if not src then
    r.DeleteTrackMediaItem(track, item)
    log("无法打开: " .. abs_path)
    return false
  end
  r.SetMediaItemTake_Source(take, src)
  local len = r.GetMediaSourceLength(src, false)
  r.SetMediaItemInfo_Value(item, "D_POSITION", pos or 0)
  r.SetMediaItemInfo_Value(item, "D_LENGTH", len)
  r.SetMediaItemInfo_Value(item, "B_LOOPSRC", loop_src and 1 or 0)
  if vol then
    r.SetMediaItemInfo_Value(item, "D_VOL", vol)
  end
  r.UpdateItemInProject(item)
  return true
end

local function bootstrap_layer(track_num, paths, repo_root, paths_mod, vol)
  local tr = track_by_number(track_num)
  if not tr then return 0 end
  if r.CountTrackMediaItems(tr) > 0 then
    log("轨 " .. track_num .. " 已有 item，跳过插入")
    return 0
  end
  local placed = 0
  for _, rel in ipairs(paths or {}) do
    local abs = paths_mod.resolve_asset(rel, repo_root)
    if insert_media(tr, abs, 0, vol, false) then
      placed = placed + 1
      log("插入轨 " .. track_num .. ": " .. rel)
    end
  end
  return placed
end

local function main()
  log("========== rain_bootstrap ==========")
  local paths_mod = load_paths()
  if not paths_mod then
    r.ShowMessageBox("找不到 rain_paths.lua", "rain_bootstrap", 0)
    return
  end
  local cfg, cfg_path = load_config()
  if not cfg then
    r.ShowMessageBox(cfg_path, "rain_bootstrap", 0)
    return
  end
  local repo_root = paths_mod.repo_root()
  if not repo_root then
    r.ShowMessageBox(
      "无法定位仓库根目录。请把本脚本放在 Reaper/Projects/Rain/.../scripts/ 下运行。",
      "rain_bootstrap",
      0
    )
    return
  end
  log("repo: " .. repo_root)
  log("配置: " .. cfg_path)

  r.Undo_BeginBlock()
  r.PreventUIRefresh(1)
  ensure_tracks(cfg)

  if cfg.video and cfg.video.path then
    local tr = track_by_number(cfg.video.track or 1)
    if tr and r.CountTrackMediaItems(tr) == 0 then
      local abs = paths_mod.resolve_asset(cfg.video.path, repo_root)
      if insert_media(tr, abs, 0, nil, true) then
        log("插入视频: " .. cfg.video.path)
      end
    end
  end

  for _, layer in ipairs(cfg.loop_layers or {}) do
    bootstrap_layer(layer.track, layer.paths, repo_root, paths_mod, layer.vol)
  end
  for _, layer in ipairs(cfg.scatter_layers or {}) do
    bootstrap_layer(layer.track, layer.paths, repo_root, paths_mod, layer.vol)
  end

  r.PreventUIRefresh(-1)
  r.UpdateArrange()
  r.Undo_EndBlock("Rain bootstrap", -1)

  r.ShowMessageBox(
    string.format(
      "建轨与素材插入完成。\n\n下一步：运行 rain_setup_project.lua\n循环 + 稀疏铺至 %.0f 小时。",
      cfg.duration_hours or 3
    ),
    "rain_bootstrap · 完成",
    0
  )
end

main()
