-- 子工程配方（与 scenes/MVI_6918.lua、video_analysis.md §三 同步）
-- 系列：Rain 睡眠（专注+钢琴属 Lake，勿混）

return {
  scene_id = "MVI_6918",
  project_name = "Rain · MVI_6918",
  series = "rain_sleep",
  duration_hours = 3,

  video = {
    track = 8,
    name = "Video · MVI_6918 loop",
    path = "assets/rain_video/MVI_6919_loop_0.98_dur_3_fade_0.5.mp4",
    render_only = true,
  },

  loop_layers = {
    {
      track = 1,
      id = "1_base",
      name = "空气底噪",
      vol = 0.28,
      paths = {
        "assets/rain_sound/1_base/空气底噪/6979801635392343310_空气底噪_河边湖边午后环境.mp3",
      },
    },
    {
      track = 2,
      id = "2_rain",
      name = "小雨主雨势",
      vol = 1.0,
      paths = {
        "assets/rain_sound/2_rain/小雨/6969458569175403790_雨滴在树叶上_淅淅沥沥雨后滴水小雨大自然夏至夏天下雨声清凉.mp3",
      },
      vol_envelope = {
        shape = "single_wave",
        depth = 0.08,
        peak_at = "center",
      },
    },
    {
      track = 5,
      id = "5_env",
      name = "林间雨环境",
      vol = 0.22,
      paths = {
        "assets/rain_sound/5_env/竹林_雨/7335268175694646554_电影级森林雨天气素材.mp3",
      },
    },
    {
      track = 7,
      id = "7_comfort",
      name = "伞面水滴",
      vol = 0.45,
      paths = {
        "assets/rain_sound/3_impact/雨伞/小雨击打雨伞.wav",
      },
    },
  },

  scatter_layers = {
    {
      track = 3,
      id = "3_impact",
      name = "雨打树叶",
      vol = 0.5,
      paths = {
        "assets/rain_sound/3_impact/雨打树叶/6974691567823097118_雨滴在树叶上的声音.mp3",
      },
      min_gap_min = 3,
      max_gap_min = 8,
      randomness = 0.6,
      clear_existing = true,
    },
    {
      track = 6,
      id = "6_life",
      name = "远处鸟鸣",
      vol = 0.3,
      paths = {
        "assets/rain_sound/6_life/鸟鸣/6974679661968182536_清晨大自然的鸟叫声.mp3",
      },
      min_gap_min = 12,
      max_gap_min = 28,
      randomness = 0.55,
      clear_existing = true,
    },
  },

  fade_sec = 0.08,
}
