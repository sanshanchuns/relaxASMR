-- LakeHealMac · 工程配置
-- 主脚本：LakeHealMac/scripts/lakeheal_setup_bird_layers.lua
--
-- 轨 1/2 已是 3h · 不动
-- 轨 3–5 按组随机铺满至 duration_hours：
--   每组：轨3 ×1 · 轨4 ×4 · 轨5 ×1
--   轨3 与 轨5 时间不重叠（编排区不同列）
--   组间 gap 随机

return {
  project_name = "LakeHealMac",
  duration_hours = 3,

  random_seed = nil,

  bird_group = {
    first_pos = 0,

    track3 = { track = 3, name = "远鸟声", count = 1 },
    track4 = { track = 4, name = "麻雀", count = 4, step = 5, offset = 3 },
    track5 = { track = 5, name = "鲸头鹳", count = 1 },

    -- 组间：上一组最晚 item 结束 → 下一组起点
    group_gap_min = 2.0,
    group_gap_max = 4.0,

    -- 轨3/5 随机落点最大重试
    placement_max_tries = 64,
  },

  clear_existing = true,
  fade_sec = 0,
}
