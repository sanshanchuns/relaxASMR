local projects = {
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\design\\vst\\render_jobs\\13_ForestWhisper_FoliageDense_Concrete_C9_极轻_密集_极湿_近贴.rpp",
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\design\\vst\\render_jobs\\11_ExpansiveShower_FoliageDense_StoneEchoing_C7_大雨_密集_极湿_远方.rpp",
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\design\\vst\\render_jobs\\19_ThickShower_FoliageDense_StoneEchoing_C1_极轻细雨_近贴.rpp",
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\design\\vst\\render_jobs\\16_SlowWaterfall_FoliageDense_FoliageYielding_C4_中雨_极湿_近贴.rpp",
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\design\\vst\\render_jobs\\07_ColdStream_FoliageCanopy_StoneEchoing_C3_中雨_均衡.rpp",
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\design\\vst\\render_jobs\\01_AiryBreeze_FoliageDense_Concrete_C1_极轻细雨_近贴.rpp",
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\design\\vst\\render_jobs\\04_BalancedSizzle_FoliageDense_FoliageLush_C8_中雨_密集_干燥_远方.rpp",
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\design\\vst\\render_jobs\\13_ForestWhisper_FoliageDense_StoneEchoing_C3_中雨_均衡.rpp",
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\design\\vst\\render_jobs\\06_BroadbandShower_FoliageCanopy_Water_C4_中雨_极湿_近贴.rpp",
  "\\\\wsl.localhost\\Ubuntu\\home\\leo\\workspace\\relaxASMR\\design\\vst\\render_jobs\\18_StrongHiss_FoliageCanopy_Water_C5_中雨_极湿_远方.rpp",
}

for i, path in ipairs(projects) do
  reaper.Main_openProject(path)
  
  -- Render
  reaper.Main_OnCommand(42230, 0)
  
  -- Prevent Save project prompt by saving silently via API
  reaper.Main_SaveProject(0, false)
end
reaper.Main_OnCommand(40004, 0) -- Quit REAPER
