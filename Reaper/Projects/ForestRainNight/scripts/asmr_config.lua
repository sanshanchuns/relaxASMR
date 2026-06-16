-- ForestRainNight · 工程配置
-- 位置：ForestRainNight/scripts/asmr_config.lua
-- 主脚本：ForestRainNight/scripts/asmr_setup_project.lua
--
-- L1/L2 · 轨 2–4 → 循环 8 h
-- L3/L4 · 轨 5–7 → 8 h 内随机稀疏出现（jitter）

return {
  project_name = "ForestRainNight",
  duration_hours = 8,

  -- L1 / L2 · 循环主层
  loop_tracks = {
    { track = 2, name = "L1 林中远雨" },
    { track = 3, name = "L2 伞面" },
    { track = 4, name = "L2 水坑" },
  },

  -- L3 / L4 · 随机稀疏层（会先 clear_existing 再生成）
  -- wav 可选：优先用轨道上已有 sample 的路径；无 sample 时用 wav 字段
  random_tracks = {
    {
      track = 5,
      name = "L3 远处闷雷",
      wav = "Audio Files/Distant,_low_rumblin_#1-1780647195133.wav",
      min_gap_min = 35,
      max_gap_min = 55,
      clear_existing = true,
    },
    {
      track = 6,
      name = "L3 湿叶摩擦",
      wav = "Audio Files/Subtle_wet_leaf_rust_#2-1780663735954_01.wav",
      min_gap_min = 12,
      max_gap_min = 28,
      clear_existing = true,
    },
    {
      track = 7,
      name = "L4 蛙",
      wav = "Audio Files/Single_quiet_frog_cr_#4-1780663380763.wav",
      min_gap_min = 45,
      max_gap_min = 65,
      clear_existing = true,
    },
  },

  fade_sec = 0.08,
}
