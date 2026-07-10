-- 场景配方 · 见 baseURL/material/MVI_6989_video_analysis.md §三
-- 由 create_rain_subproject.py 自动生成

return {
  scene_id = "MVI_6989",
  project_name = "Rain · MVI_6989",
  series = "rain_sleep",
  duration_hours = 3.0,

  video = {
    track = 5,
    name = "Video · MVI_6989 loop",
    path = "/mnt/e/自然之声/to_youtube/MVI_6989_loop_0.96_dur_19_fade_0.5.mp4",
    render_only = true,
  },

  loop_layers = {
    {
      track = 1,
      id = "1_rain",
      name = "主雨势",
      vol = 30.2691,
      paths = {
        "/mnt/e/自然之声/to_youtube/audio/1_rain/sounds/14_GentleSwish_FoliageDense_FoliageLush_C4_中雨_极湿_近贴.wav",
      },
    },
  },

  scatter_layers = {
    {
      track = 2,
      id = "2_impact",
      name = "雨打树叶",
      vol = 0.5,
      paths = {
      },
    },
    {
      track = 3,
      id = "3_random",
      name = "随机散音",
      vol = 0.35,
      paths = {
      },
    },
    {
      track = 4,
      id = "4_wildlife",
      name = "野生生态",
      vol = 0.28,
      paths = {
      },
    },
  },

  fade_sec = 0.08,
}
