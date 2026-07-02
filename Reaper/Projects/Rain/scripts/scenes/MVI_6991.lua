-- 场景配方 · 见 subprojects/MVI_6991/video_analysis.md §三
-- 由 create_rain_subproject.py 自动生成

return {
  scene_id = "MVI_6991",
  project_name = "Rain · MVI_6991",
  series = "rain_sleep",
  duration_hours = 3,

  video = {
    track = 7,
    name = "Video · MVI_6991 loop",
    path = "assets/loop_video/rain_video/MVI_6991/MVI_6991_loop_0.58_dur_4_fade_0.5.mp4",
    render_only = true,
  },

  loop_layers = {
    {
      track = 1,
      id = "1_rain",
      name = "小雨主雨势",
      vol = 1.0,
      paths = {
        "assets/sound_effect/rain_sound/1_rain/intensity/drizzle/173647_Rain,_Vegetation,_Rain,_Daytime,_Mid_To_Hard_Rainfall,_Havelock_Island,_Second_02_Crest_F50.mp3",
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
      vol = 0.24,
      paths = {
        "assets/sound_effect/rain_sound/4_water/standing_water/puddle/ARMGJCH_Stone_Splash_in_Puddle.mp3",
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
        "assets/sound_effect/rain_sound/2_impact/vegetation/leaves/180385_Rain,_Vegetation,_Rain,_Daytime,_Rain_Drops_Hitting_Hard_Palm_Leaves,_Havelock_Island_02_Crest_F50_N5.mp3",
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
