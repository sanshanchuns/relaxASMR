local projects = {
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\scripts\\video_analysis\\preset_db\\natural_rain_rpps\\render_jobs\\20_WarmBuzz_FoliageDense_Water_C9_大雨_远方.rpp",
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\scripts\\video_analysis\\preset_db\\natural_rain_rpps\\render_jobs\\20_WarmBuzz_FoliageDense_WoodRoof_C1_极轻细雨_近贴.rpp",
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\scripts\\video_analysis\\preset_db\\natural_rain_rpps\\render_jobs\\20_WarmBuzz_FoliageDense_WoodRoof_C2_极轻密集_近贴.rpp",
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\scripts\\video_analysis\\preset_db\\natural_rain_rpps\\render_jobs\\20_WarmBuzz_FoliageDense_WoodRoof_C3_小阵雨_中距.rpp",
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\scripts\\video_analysis\\preset_db\\natural_rain_rpps\\render_jobs\\20_WarmBuzz_FoliageDense_WoodRoof_C4_中雨_均衡.rpp",
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\scripts\\video_analysis\\preset_db\\natural_rain_rpps\\render_jobs\\20_WarmBuzz_FoliageDense_WoodRoof_C5_中雨极湿_近贴.rpp",
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\scripts\\video_analysis\\preset_db\\natural_rain_rpps\\render_jobs\\20_WarmBuzz_FoliageDense_WoodRoof_C6_中雨极湿_远方.rpp",
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\scripts\\video_analysis\\preset_db\\natural_rain_rpps\\render_jobs\\20_WarmBuzz_FoliageDense_WoodRoof_C7_中雨密集_干燥_远方.rpp",
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\scripts\\video_analysis\\preset_db\\natural_rain_rpps\\render_jobs\\20_WarmBuzz_FoliageDense_WoodRoof_C8_大雨_近贴.rpp",
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\scripts\\video_analysis\\preset_db\\natural_rain_rpps\\render_jobs\\20_WarmBuzz_FoliageDense_WoodRoof_C9_大雨_远方.rpp",
}

for i, path in ipairs(projects) do
  reaper.Main_openProject(path)
  reaper.Main_OnCommand(42230, 0) -- Render
end
reaper.Main_OnCommand(40004, 0) -- Quit REAPER
