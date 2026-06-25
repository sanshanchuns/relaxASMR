-- 将 asmr_config.lua 导出为 JSON（供 generate_subproject.py 使用）
-- 用法: lua dump_asmr_config.lua /path/to/asmr_config.lua

local path = arg[1]
if not path then
  io.stderr:write("usage: lua dump_asmr_config.lua <asmr_config.lua>\n")
  os.exit(1)
end

local f = loadfile(path)
if not f then
  io.stderr:write("cannot load " .. path .. "\n")
  os.exit(1)
end
local c = f()

local function esc(s)
  s = tostring(s or "")
  s = string.gsub(s, "\\", "\\\\")
  s = string.gsub(s, '"', '\\"')
  s = string.gsub(s, "\n", "\\n")
  return '"' .. s .. '"'
end

local function paths_json(tbl)
  local parts = {}
  for _, p in ipairs(tbl or {}) do
    parts[#parts + 1] = esc(p)
  end
  return "[" .. table.concat(parts, ",") .. "]"
end

local function layer_json(l)
  local s = "{"
  s = s .. '"track":' .. (l.track or 0) .. ","
  s = s .. '"id":' .. esc(l.id) .. ","
  s = s .. '"name":' .. esc(l.name) .. ","
  if l.vol then s = s .. '"vol":' .. l.vol .. "," end
  s = s .. '"paths":' .. paths_json(l.paths)
  if l.min_gap_min then s = s .. ',"min_gap_min":' .. l.min_gap_min end
  if l.max_gap_min then s = s .. ',"max_gap_min":' .. l.max_gap_min end
  if l.randomness then s = s .. ',"randomness":' .. l.randomness end
  if l.count then s = s .. ',"count":' .. l.count end
  if l.clear_existing then s = s .. ',"clear_existing":true' end
  s = s .. "}"
  return s
end

local function list_json(layers)
  local parts = {}
  for _, l in ipairs(layers or {}) do
    parts[#parts + 1] = layer_json(l)
  end
  return "[" .. table.concat(parts, ",") .. "]"
end

local out = "{"
out = out .. '"scene_id":' .. esc(c.scene_id) .. ","
out = out .. '"project_name":' .. esc(c.project_name) .. ","
out = out .. '"duration_hours":' .. (c.duration_hours or 3) .. ","
out = out .. '"fade_sec":' .. (c.fade_sec or 0.08) .. ","
if c.video then
  out = out .. '"video":{"track":' .. (c.video.track or 1) .. ","
  out = out .. '"name":' .. esc(c.video.name) .. ","
  out = out .. '"path":' .. esc(c.video.path) .. "},"
end
out = out .. '"loop_layers":' .. list_json(c.loop_layers) .. ","
out = out .. '"scatter_layers":' .. list_json(c.scatter_layers)
out = out .. "}"

print(out)
