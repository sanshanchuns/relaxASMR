# 雨声声音设计（Rain Sound Design）

> 设计框架：[layers.md](layers.md) · 高质量 Rain ASMR = **6 层素材轨 + 1 层 Dynamic（自动化）**。

## 架构总览

```text
Rain Sound Design
│
├── 1. Rain Layer（主体雨层）           → 轨 `1_rain`
├── 2. Impact Layer（雨滴击打层）       → 轨 `2_impact`
├── 3. Environment Layer（环境空间层）  → 轨 `3_environment`
├── 4. Water Layer（二次水层）          → 轨 `4_water`
├── 5. Wildlife Layer（自然生命层）     → 轨 `5_wildlife`
├── 6. Human Layer（人类存在层）        → 轨 `6_human`
└── 7. Dynamic Layer（动态变化层）      → 无轨 · 穿插调节前 6 层包络/稀疏
```

| 轨号 | layer_id | 概念层 | 推荐素材数 |
|------|----------|--------|------------|
| 1 | `1_rain` | Rain | 3–5 |
| 2 | `2_impact` | Impact | 8–15 |
| 3 | `3_environment` | Environment | 2–4 |
| 4 | `4_water` | Water | 2–5 |
| 5 | `5_wildlife` | Wildlife | 1–3 |
| 6 | `6_human` | Human | 1–3 |
| 7 | video | 循环视频 | 1 |
| — | Dynamic | 自动化 | `1_rain` 慢变包络等 |

**核心思路**：`Rain = 雨本身 + 雨打在不同材质上`。场景差异来自 **Impact 材质组合**（见 layers.md 优先级：Vegetation · Roof · Glass · Water 优先收集）。

---

## 混音原则

| 原则 | 说明 |
|------|------|
| 持续稳定 > 丰富变化 | Dynamic 承担长时变化，素材层保持稳 |
| 主体 70~90% | Rain + Impact + Environment + Water |
| 点缀 5~20% | Wildlife + Human，稀疏、轻 |
| Group 总线 | 轨 1–6 → **ReaEQ + ReaComp**；`5_wildlife` 可加 **ReaVerbate** |

### 频段避让

| 层级 | 主要频段 | 混音建议 |
|------|----------|----------|
| Rain | 500Hz~6kHz | 主体 30~50% |
| Impact | 2k~8kHz | 低于 Rain 20~30% |
| Environment | 宽频 | 空间底，不抢 Bed |
| Water | 200Hz~4kHz | 中低频流动 |
| Wildlife | 1k~6kHz | scatter 15~60s |
| Human | 80Hz~2kHz | 极轻 loop |

---

## ⑦ Dynamic Layer（动态变化层）

**无素材**。Automation 穿插调节前 6 层，避免 3h 听感完全重复。

| 手段 | 载体 |
|------|------|
| Rain Volume 慢变 ±6–10% | 手动运行 **`asmr_vol_envelope.lua`**（`1_rain`） |
| 稀疏间隔随机 | Wildlife / Impact scatter |
| Wind / 密度微调 | Environment（可选） |

```lua
-- 在 Reaper 中手动运行 asmr_vol_envelope.lua
-- 参数：时长、点数、最大/最小 dB、正弦或余弦
```

对 **`1_rain`** 轨运行 `asmr_vol_envelope.lua` 写入长时 Volume 包络。

---

## ① Rain Layer · `1_rain`

| 子类 | 关键词（layers.md） |
|------|---------------------|
| Intensity | Drizzle, Light, Moderate, Heavy, Downpour |
| Distance（可选） | Far, Mid, Near, Overhead |
| Perspective（可选） | Indoor, Outdoor, Covered, Open |

目录：`assets/sound_effect/rain_sound/1_rain/intensity/` · `distance/` · `perspective/`

---

## ② Impact Layer · `2_impact`

按 **材质** 分子目录（收集优先级见 [layers.md](layers.md)）：

| 材质 | 子目录示例 |
|------|------------|
| Vegetation | `vegetation/leaves`, `grass`, `moss`, `bamboo` |
| Wood | `wood/wood_roof`, `cabin_roof`, `deck` |
| Metal | `metal/tin_roof`, `metal_roof` |
| Glass | `glass/window` |
| Stone | `stone/gravel`, `rock` |
| Ground | `ground/concrete`, `asphalt` |
| Water | `water/puddle`, `lake` |
| Fabric | `fabric/umbrella`, `tent` |

---

## ③ Environment Layer · `3_environment`

| 子类 | 示例 |
|------|------|
| Air | Forest Air, Lake Air, Wetland Air |
| Wind | Forest Wind, Canopy Wind, Mountain Wind |
| Ambience | Forest, Lake, Mountain, Wetland, Countryside |
| Room Tone | Forest Room, Cabin Room |

（旧 `1_base` 空气/风素材归入本层。）

---

## ④ Water Layer · `4_water`

| 子类 | 示例 |
|------|------|
| Dripping | Leaf/Roof/Window Drip |
| Flow | Gutter, Drain, Runoff |
| Stream | Creek, Brook, Small Waterfall |
| Standing Water | Puddle, Ripples, Splash |

---

## ⑤ Wildlife Layer · `5_wildlife`

Birds · Amphibians · Insects · Mammals（可选）— **随机、偶尔、不连续**。

---

## ⑥ Human Layer · `6_human`

Fire · Cabin/House · Reading/Working · Tent · Indoor — **很轻、很少、不抢雨**。

---

## 声源库

  **单一性原则**：每条素材只应含 **≤2 类独立声源**（雨+鸟+风 = 3 类 → 拒绝；「雨打树叶」不算多类）。见 `sound_purity.py`。

| 路径 | 说明 |
|------|------|
| `assets/sound_effect/rain_sound/` | 六层规范目录 |
| `rain_sound/before_backup/` | 旧库备份 |
| `rain_sound/_rejected_mixed/` | 审计移出的混合素材 |

填充工具（仓库根目录）：

```bash
python3 scripts/sound_effect/fill_rain_sound.py --init-dirs
python3 scripts/sound_effect/fill_rain_sound.py --from-backup   # 自动 pass 混合
python3 scripts/sound_effect/fill_rain_sound.py --from-boom
python3 scripts/sound_effect/fill_rain_sound.py --audit-purity  # 审计现有库
python3 scripts/sound_effect/fill_rain_sound.py --purge-mixed     # 移出混合素材
```

下载（次级，英文关键词）：`scripts/capcut_audio/download.py` · envato · epidemic — 配置 `rain_layers.json`；下载前检查 `before_backup` 是否已有同名文件。

---

## Group 总线 · ReaEQ

| 频段 | 类型 | 频率 | Gain |
|------|------|------|------|
| 1 | High-pass | 120 Hz | 0 |
| 2 | Band | 3.5 kHz | −3 dB |
| 3 | Band | 6 kHz | −5 dB |
| 4 | High-shelf | 8 kHz | −4 dB |

---

## 分层索引

| layer_id | 目录 |
|----------|------|
| `1_rain` | `rain_sound/1_rain/` |
| `2_impact` | `rain_sound/2_impact/` |
| `3_environment` | `rain_sound/3_environment/` |
| `4_water` | `rain_sound/4_water/` |
| `5_wildlife` | `rain_sound/5_wildlife/` |
| `6_human` | `rain_sound/6_human/` |

---

## 相关文件

- [layers.md](layers.md) · [scoring_rubric.md](scoring_rubric.md)
- `Reaper/Projects/Rain/scripts/layer_template.lua`
- `scripts/sound_effect/rain_library_schema.json`
- `scripts/capcut_audio/rain_layers.json`
