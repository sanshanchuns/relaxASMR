-- @description ASMR · 按 asmr_config 写入长时音量包络
-- @version 1.0
-- @author relaxASMR
-- @about
--   读取 scripts/asmr_config.lua 中带 vol_envelope 的 loop 层，
--   在轨 Volume 包络上写入单周期缓慢起伏（默认 3h 一个波峰/波谷）。
--   建议在 asmr_apply_recipe 铺循环后运行；也可单独执行。

local r = reaper

local function script_dir()
  local _, script_path = r.get_action_context()
  return script_path:match("^(.+)[\\/][^\\/]+$")
end

local function load_paths()
  local f = loadfile(script_dir() .. package.config:sub(1, 1) .. "asmr_paths.lua")
  if not f then return nil end
  return f()
end

local function main()
  local paths_mod = load_paths()
  if not paths_mod then return end
  local cfg, err = paths_mod.load_asmr_config()
  if not cfg then
    r.ShowMessageBox(err, "asmr_apply_vol_envelope", 0)
    return
  end

  local hours = cfg.duration_hours or 3
  local total_sec = hours * 3600
  if r.GetProjectLength(0) > 0 then total_sec = r.GetProjectLength(0) end

  local vol_mod = loadfile(script_dir() .. package.config:sub(1, 1) .. "asmr_vol_envelope.lua")()
  if not vol_mod then
    r.ShowMessageBox("找不到 asmr_vol_envelope.lua", "asmr_apply_vol_envelope", 0)
    return
  end

  r.Undo_BeginBlock()
  r.PreventUIRefresh(1)
  local n = vol_mod.apply_from_config(cfg, total_sec, paths_mod)
  r.PreventUIRefresh(-1)
  r.UpdateArrange()
  r.Undo_EndBlock("Apply vol envelopes", -1)

  r.ShowMessageBox(
    string.format("已写入 %d 条轨音量包络 · %.1f h", n, total_sec / 3600),
    "asmr_apply_vol_envelope",
    0
  )
end

main()
