-- 雨声系列 · 统一轨结构（Rain Sound Design 六层 + Dynamic）
-- 轨 1–6 = 六层素材轨（混音时只动这些轨）
-- 轨 7 = 视频 looper（仅最终渲染）
-- Layer 7 Dynamic = 自动化（主载 1_rain 音量包络等），无独立轨
-- Group = Folder 父轨 · ReaEQ + ReaComp

return {
  video_track = 7,

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
    { track = 1, id = "1_rain",        name = "1_rain 雨层" },
    { track = 2, id = "2_impact",      name = "2_impact 击打" },
    { track = 3, id = "3_environment", name = "3_environment 环境" },
    { track = 4, id = "4_water",       name = "4_water 水体" },
    { track = 5, id = "5_wildlife",    name = "5_wildlife 生物" },
    { track = 6, id = "6_human",       name = "6_human 人类" },
  },
}
