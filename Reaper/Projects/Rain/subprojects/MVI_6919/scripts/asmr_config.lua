-- 场景配方 · 见 subprojects/MVI_6919/video_analysis.md §三
-- 由 create_rain_subproject.py 自动生成

return {
  scene_id = "MVI_6919",
  project_name = "Rain · MVI_6919",
  series = "rain_sleep",
  duration_hours = 3.0,

  video = {
    track = 7,
    name = "Video · MVI_6919 loop",
    path = "assets/loop_video/rain_video/MVI_6919/MVI_6919_loop_08_0.97_dur_4_fade_0.5_01.mp4",
    render_only = true,
  },

  loop_layers = {
    {
      track = 1,
      id = "1_rain",
      name = "小雨主雨势",
      vol = 1.0,
      paths = {
        "assets/sound_effect/rain_sound/1_rain/intensity/light/179242_Rain,_Vegetation,_Light_Rain_In_A_Field_Of_Bananas_Trees_01.mp3",
      },
      vol_envelope = {
        shape = "single_wave",
        depth = 0.08,
        peak_at = "center",
      },
    },
    {
      track = 3,
      id = "3_environment",
      name = "环境空间",
      vol = 0.26,
      paths = {
        "assets/sound_effect/rain_sound/3_environment/ambience/forest/153479_Rain,_General,_Tropical,_Moderate_Monsoon_Rain_Open_Garage_P.mp3",
      },
    },
    {
      track = 4,
      id = "4_water",
      name = "水体/滴水",
      vol = 0.18,
      paths = {
        "assets/sound_effect/rain_sound/4_water/dripping/branch_drip/237672_Rain,_Plastic,_Drips_On_Verandah_Roof.mp3",
      },
    },
    {
      track = 6,
      id = "6_human",
      name = "炉火噼啪",
      vol = 0.38,
      paths = {
        "assets/sound_effect/rain_sound/6_human/fire/fire_crackle/N5KW5NM_Fire_Crackle_CU_Pops_Small_Campfire.mp3",
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
        "assets/sound_effect/rain_sound/2_impact/vegetation/leaves/152602_Rain,_Vegetation,_Rain,_Daytime,_Rain_Drops_Hitting_Palm_Lea.mp3",
      },
      min_gap_min = 3,
      max_gap_min = 8,
      randomness = 0.6,
      clear_existing = true,
    },
    {
      track = 5,
      id = "5_wildlife",
      name = "远处鸟鸣",
      vol = 0.22,
      paths = {
        "assets/sound_effect/rain_sound/5_wildlife/birds/Hwamei/9PBX76J_Birds.mp3",
      },
      min_gap_min = 12,
      max_gap_min = 28,
      randomness = 0.55,
      clear_existing = true,
    },
  },

  fade_sec = 0.08,
}
