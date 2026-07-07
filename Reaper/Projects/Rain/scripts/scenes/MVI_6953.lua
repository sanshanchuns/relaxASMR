-- 场景配方 · 见 subprojects/MVI_6953/video_analysis.md §三
-- 由 create_rain_subproject.py 自动生成

return {
  scene_id = "MVI_6953",
  project_name = "Rain · MVI_6953",
  series = "rain_sleep",
  duration_hours = 3.0,

  video = {
    track = 7,
    name = "Video · MVI_6953 loop",
    path = "assets/loop_video/rain_video/MVI_6953/MVI_6953_loop_0.95_dur_8_fade_0.5.mp4",
    render_only = true,
  },

  loop_layers = {
    {
      track = 1,
      id = "1_rain",
      name = "小雨主雨势",
      vol = 1.0,
      paths = {
      },
    },
    {
      track = 3,
      id = "3_environment",
      name = "环境空间",
      vol = 0.26,
      paths = {
      },
    },
    {
      track = 4,
      id = "4_water",
      name = "水体/滴水",
      vol = 0.18,
      paths = {
      },
    },
    {
      track = 6,
      id = "6_human",
      name = "留白（待选）",
      vol = 0.0,
      paths = {
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
      track = 5,
      id = "5_wildlife",
      name = "远处鸟鸣",
      vol = 0.28,
      paths = {
      },
    },
  },

  fade_sec = 0.08,
}
