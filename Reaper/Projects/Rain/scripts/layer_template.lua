-- 雨声系列 · 统一轨结构（所有子工程相同）
-- 轨 1–7 = rain_sound_design 七层（混音时只动这些轨）
-- 轨 8 = 视频 looper（已生成，仅最终渲染用，混音流程不改动）
-- Group = Folder 父轨 · 总线 FX（削高频 + 轻压缩）

return {
  video_track = 8,

  group_bus = {
    name = "Group",
    -- JS 参数与 asmr_sleep_hf_eq.jsfx slider1..9 一致
    js_eq = {
      file = "asmr_sleep_hf_eq.jsfx",
      js_name = "relaxASMR/asmr_sleep_hf_eq.jsfx",
      params = { 120, -3, 3500, 1.2, -5, 6000, 0.8, -4, 8000 },
    },
    reacomp = true,
  },

  layers = {
    { track = 1, id = "1_base",   name = "1_base 底噪" },
    { track = 2, id = "2_rain",   name = "2_rain 雨层" },
    { track = 3, id = "3_impact", name = "3_impact 击打" },
    { track = 4, id = "4_water",  name = "4_water 水体" },
    { track = 5, id = "5_env",    name = "5_env 环境" },
    { track = 6, id = "6_life",   name = "6_life 生物" },
    { track = 7, id = "7_comfort", name = "7_comfort 心理舒适" },
  },
}
