-- StreamHeal · 工程配置
-- 位置：StreamHeal/scripts/asmr_config.lua
-- 主脚本：StreamHeal/scripts/asmr_setup_project.lua
--
-- 轨 1 bgm_main · 轨 2 video → 循环 3 h

return {
  project_name = "StreamHeal",
  duration_hours = 3,

  loop_tracks = {
    { track = 1, name = "bgm_main" },
    { track = 2, name = "video" },
  },
}
