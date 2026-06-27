-- 场景配方 · 见 subprojects/MVI_6927/video_analysis.md §三
-- 由 create_rain_subproject.py 自动生成

return {
  scene_id = "MVI_6927",
  project_name = "Rain · MVI_6927",
  series = "rain_sleep",
  duration_hours = 3,

  video = {
    track = 8,
    name = "Video · MVI_6927 loop",
    path = "assets/loop_video/rain_video/MVI_6927.mp4",
    render_only = true,
  },

  loop_layers = {
    {
      track = 1,
      id = "1_base",
      name = "空气底噪",
      vol = 0.28,
      paths = {
        "assets/sound_effect/rain_sound/1_base/air_tone/165877_Ambience,_Room_Tone,_Interior,_Air_Condition,_Unit_A.mp3",
      },
    },
    {
      track = 2,
      id = "2_rain",
      name = "小雨主雨势",
      vol = 1.0,
      paths = {
        "assets/sound_effect/rain_sound/2_rain/light_rain/197192_Rain,_Vegetation,_Light_Rain_In_A_Field_Of_Bananas_Trees_03.mp3",
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
        "assets/sound_effect/rain_sound/5_env/forest_rain/171831_Rain,_Vegetation,_Forest,_Evening,_Medium_Rain,_Distant_Bird.mp3",
      },
    },
    {
      track = 7,
      id = "7_comfort",
      name = "伞面水滴",
      vol = 0.45,
      paths = {
        "assets/sound_effect/rain_sound/3_impact/rain_on_umbrella/171322_Rain,_Cloth,_Light,_Under_Umbrella,_Close.mp3",
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
        "assets/sound_effect/rain_sound/3_impact/rain_on_leaves/152602_Rain,_Vegetation,_Rain,_Daytime,_Rain_Drops_Hitting_Palm_Lea.mp3",
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
        "assets/sound_effect/elevenlabs_sound/bird/api_mvi6918_bird_distant.mp3",
      },
      min_gap_min = 12,
      max_gap_min = 28,
      randomness = 0.55,
      clear_existing = true,
    },
  },

  fade_sec = 0.08,
}
