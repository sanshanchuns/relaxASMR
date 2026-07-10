-- 雨声系列 · 四层音频 + 视频轨
-- 轨 1–4 = 1_rain / 2_impact / 3_random / 4_wildlife（素材在 baseURL/audio/）
-- 轨 5 = 视频 looper（仅最终渲染）
-- Group = Folder 父轨 · ReaEQ + ReaComp

return {
  video_track = 5,

  group_bus = {
    name = "Group",
    js_eq = {
      file = "asmr_sleep_hf_eq.jsfx",
      js_name = "relaxASMR/asmr_sleep_hf_eq.jsfx",
      params = { 120, -3, 3500, 1.2, -5, 6000, 0.8, -4, 8000 },
    },
    reacomp = true,
  },

  layers = {
    { track = 1, id = "1_rain",     name = "1_rain 雨层" },
    { track = 2, id = "2_impact",   name = "2_impact 击打" },
    { track = 3, id = "3_random",   name = "3_random 随机" },
    { track = 4, id = "4_wildlife", name = "4_wildlife 生物" },
  },
}
