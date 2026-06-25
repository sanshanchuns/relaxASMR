# 雨声声音设计（Rain Sound Design）

> 基于 [level.md](level.md) 整合优化。高质量 Rain ASMR 通常由 **7 层 Layer + 10~30 条独立声源** 叠加，而非单条雨声音轨。

## 架构总览

```
Rain ASMR
├── 1. Base Layer（底噪层）      — 空气、风、远处环境底噪
├── 2. Rain Layer（雨层）        — 主体雨势
├── 3. Impact Layer（击打层）    — 雨滴击打不同表面
├── 4. Water Layer（水体层）     — 二次水声
├── 5. Environment Layer（环境层）— 地点感
├── 6. Life Layer（生物层）      — 鸟鸣、蛙鸣等
└── 7. Comfort Layer（心理舒适层）— 安全感、放松感；Rain 系列画龙点睛
```

## 混音原则

| 原则 | 说明 |
|------|------|
| 持续稳定 > 丰富变化 | 专注/睡眠赛道以稳定底床为主 |
| 主体环境声 70~90% | Base + Rain + Impact + Water 占主体 |
| 点缀声 5~20% | Life + Comfort 低频或持续心理锚点 |
| 音轨数 | 成品工程通常 8~15 条，素材库每层 3~8 条候选 |
| **长时时间感** | 无限循环成片须 **缓慢宏观起伏**（见下 §Macro Dynamics），避免 3h 听感与 5min 完全相同 |
| **Group 总线 EQ** | 轨 1–7 进 **Folder/Group** 后统一 **ReaEQ 削 3–8kHz**（见下 §Group Bus），比逐轨 EQ 更易维护 |

### 频段避让

| 层级 | 主要频段 | 混音建议 |
|------|----------|----------|
| Base | 100Hz~8kHz 宽频 | 音量最低，铺底不抢戏；EQ 可略削 200~400Hz 避免浑浊 |
| Rain | 500Hz~6kHz | 主体，占 30~50% 听感 |
| Impact | 2k~8kHz | 与 Rain 高频重叠，Impact 音量宜低于 Rain 20~30% |
| Water | 200Hz~4kHz | 中低频流动感，与 Base 低频注意平衡 |
| Life | 1k~6kHz 瞬态 | 稀疏触发，避免与 Impact 同时密集出现 |
| Comfort | 80Hz~2kHz 稳态/近场 | **持续**心理锚点，loop 为主；可叠 2~3 条；区别于普通雨 ASMR 的关键 |

### 素材时长建议

| 类型 | 建议时长 | 循环方式 |
|------|----------|----------|
| Base / Rain | ≥60s | 无缝循环或长片段 |
| Impact | 10~60s | 随机 scatter 叠加 |
| Water | 30~120s | 循环或长 fade |
| Life / Comfort | 3~120s | Comfort 宜长 loop；Life 事件触发 |

---

## 长时时间感 · Macro Dynamics（无限循环核心）

真实世界里 **风变大/变小、雨忽强忽弱、鸟叫一阵停一阵**；5 分钟、10 分钟、30 分钟听起来应 **略有不同**，但睡眠/专注赛道 **不宜剧烈跳变**。

对应 [`rule.md`](../rule.md) §六 **20% 变化**：由 **稀疏层 + 主雨层慢变包络** 共同承担；10% 惊喜仍由 Life scatter 承担。

### 原则

| 要点 | 说明 |
|------|------|
| 载体 | **2_rain 主雨层 loop 轨** 的 Volume 包络（Reaper 轨音量自动化） |
| 周期 | **整段成片一个起伏**（如 3h 仅一个波峰或波谷），非每分钟抖动 |
| 幅度 | `depth` **0.06–0.10**（相对 unity 约 ±6–10%）；超过 0.12 易觉「忽大忽小」 |
| 形状 | `single_wave`：正弦半周期；`peak_at=center` 中段略强，`peak_at=edges` 中段略弱 |
| 勿叠 | 不在 Base/Comfort 上重复同周期包络，避免全床同步起伏 |

### 配方字段（`asmr_config.lua`）

```lua
vol_envelope = {
  shape = "single_wave",
  depth = 0.08,        -- 两端约 −8%，中段回到基准（peak_at=center 时）
  peak_at = "center",  -- 或 "edges"（中段雨歇）
},
```

### 工程操作

1. `asmr_apply_recipe.lua` 铺循环后会 **自动写入** 带 `vol_envelope` 的 loop 层包络  
2. 单独重刷包络：`asmr_apply_vol_envelope.lua`（不改 item 长度）

---

## Group 总线 · 统一削高频（安全感）

多层雨声叠床后 **3–8kHz 易超标**（打分 `highfreq_restraint` 主要短板）。睡眠系列推荐：

| 步骤 | 操作 |
|------|------|
| 1 | 选中轨 **1–7**（**不要含 video**），`G` 成 Folder，父轨命名 `Group` |
| 2 | 在 **Group 父轨** 加 FX：**ReaEQ**（必要时再加 **ReaComp**） |
| 3 | 确认子轨 **路由进 Folder**（路由钮显示送入父轨，而非直出 Master） |
| 4 | 渲染成品 wav → `score_mix.py` 复测 **3–8kHz 占比**（目标 ≤10% 满分） |

**ReaEQ 参考（ReaEQ 4-band，按 Program 1 改）：**

| 频段 | 类型 | 频率 | Gain | Q | 作用 |
|------|------|------|------|---|------|
| 1 | High-pass | **120 Hz** | 0 | 0.7 | 去极低 rumble，保留托底 |
| 2 | Band | **3.5 kHz** | **−3 dB** | 1.2 | rule §五 敏感区中心 |
| 3 | Band | **6 kHz** | **−5 dB** | 0.8 | 雨丝 / 鸟叫尖感 |
| 4 | High-shelf | **8 kHz** | **−4 dB** | — | 整体柔化 |

从实测 ~28% 压到 ~10% 往往需 **累计约 4–8 dB** 的 3–8k 削减；以耳朵为准，每次改完 **重渲染 160s 样本** 再打分。

**ReaComp（若在 Group 上）：** 阈值偏高、ratio 2:1 左右，避免把高频瞬态「挤亮」。若仍刺，可在 **Comp 后再挂一颗 ReaEQ** 只削 5–8k。

**不要**只在 Master 削高频而不走 Group——Master 只做 **ReaLimit / 响度** 即可，频段整形放在 Group。

---

## 混音打分（包裹感 / 安全感）

成品混音按可执行规则打分，详见 **[`scoring_rubric.md`](scoring_rubric.md)**。

| 工具 | 用途 |
|------|------|
| `Reaper/scripts/score_mix.py` | 成品 wav 声学测量 + `--scene` 读配方结构 |
| `scoring_rubric.md` | 权重、阈值、距离层映射、安全声源白名单 |

**要点**：成品测声学（连续床、尖峰、高频、立体声宽度）；配方读结构（近中远、安全声源、**2_rain 是否配置 macro 包络**）。  
配置合理 `vol_envelope` 时，安全感子项 **macro_drift** 并入密度吻合度评估（对应 rule §六 20% 变化）。

---

## 1. Base Layer（底噪层）

**作用**：真实世界的雨不是孤立的「雨声」，而是空气噪声 + 风噪 + 远处环境底噪 + 雨声。缺少底噪层听起来很假。

**频段**：100Hz~8kHz 宽频，非常平稳。

### 子元素

| 子元素 | 英文 | 特征 | 搜索关键词 |
|--------|------|------|------------|
| 空气底噪 | Air Tone | 森林/山谷/湖边空气，平稳宽频 | `风声`, `微风`, `森林环境`, `白噪音` |
| 无风 | Calm | ASMR 最常见，几乎无风感 | `微风` |
| 微风 | Light Breeze | 树叶轻微摆动 | `微风`, `风声` |
| 阵风 | Gust | 偶尔出现，增加动态 | `风声` |

**推荐音轨数**：1~2 条  
**占比区间**：5~15%

**本地目录**：`assets/rain_sound/1_base/<keyword>/`

---

## 2. Rain Layer（雨层）

**作用**：整个作品的主体，决定雨势大小与情绪基调。

**频段**：500Hz~6kHz，毛毛雨高频多、暴雨低频冲击强。

### 子元素

| 子元素 | 英文 | 特征 | 适用场景 | 搜索关键词 |
|--------|------|------|----------|------------|
| 毛毛雨 | Drizzle | 高频多、密度低 | 阅读、睡眠 | `毛毛雨` |
| 小雨 | Light Rain | 最常见 | 通用 | `小雨`, `下雨` |
| 中雨 | Moderate Rain | YouTube 热门最多 | 专注 | `下雨` |
| 大雨 | Heavy Rain | 冲击感强 | 沉浸 | `大雨` |
| 暴雨 | Storm Rain | 常配雷声 | 刺激感 | `暴雨` |
| 雾雨 | Mist Rain | 接近白噪音 | 极简 | `下雨`, `白噪音` |

**推荐音轨数**：1~3 条（选一种主雨势 + 可选叠加）  
**占比区间**：30~50%

**本地目录**：`assets/rain_sound/2_rain/<keyword>/`

**长时成片**：loop 铺好后在轨 Volume 上写 **单周期慢变包络**（见 §Macro Dynamics）；本层是唯一应做宏观起伏的持续层。

---

## 3. Impact Layer（击打层）

**作用**：决定真实感的核心。只有 Rain Layer 会像白噪音（嘶——），加入击打层（啪、滴、嗒）立刻变真实。

**频段**：2k~8kHz，瞬态明显。

### 子元素

| 子元素 | 英文 | 特征 | 搜索关键词 |
|--------|------|------|------------|
| 打树叶 | Rain on Leaves | 森林系最常见 | `雨打树叶` |
| 打草地 | Rain on Grass | 柔和 | `雨打树叶` |
| 打泥土 | Rain on Soil | 低频多 | `下雨` |
| 打石头 | Rain on Stone | 清脆 | `雨打窗户` |
| 打木头 | Rain on Wood | 温暖 | `雨打屋顶` |
| 打屋顶 | Rain on Roof | 经典睡眠声（铁皮/木屋/瓦片） | `雨打屋顶` |
| 打帐篷 | Rain on Tent | 露营热门 | `雨打屋顶` |
| 打雨伞 | Rain on Umbrella | 近场 ASMR | `雨伞` |
| 打窗户 | Rain on Window | 城市雨景 | `雨打窗户` |

**推荐音轨数**：2~5 条（不同表面 scatter）  
**占比区间**：10~20%

**混音注意**：音量低于 Rain 层 20~30%，避免高频刺耳。

**本地目录**：`assets/rain_sound/3_impact/<keyword>/`

---

## 4. Water Layer（水体层）

**作用**：雨产生大量二次水声，很多优秀作品这一层最丰富。

**频段**：200Hz~4kHz，流动感与中低频为主。

### 子元素

| 子元素 | 英文 | 特征 | 搜索关键词 |
|--------|------|------|------------|
| 水滴 | Water Drop | 滴、答、滴 | `水滴` |
| 屋檐滴水 | Roof Drip | 非常催眠 | `屋檐滴水` |
| 排水沟 | Gutter | 持续流水 | `流水` |
| 水坑 | Puddle | 啪嗒 | `水滴` |
| 积水流动 | Surface Runoff | 地面径流 | `流水` |
| 小溪 | Creek | 远处溪流 | `溪流` |
| 河流 | River | 持续水声 | `流水` |
| 湖边浪声 | Lake Lap | 雨天湖泊、西湖等 | `湖水` |

**推荐音轨数**：2~4 条  
**占比区间**：10~25%

**本地目录**：`assets/rain_sound/4_water/<keyword>/`

---

## 5. Environment Layer（环境层）

**作用**：决定地点感，将「雨」锚定到具体场景。

**频段**：依场景而异，多为宽频环境混合。

### 子元素

| 子元素 | 英文 | 组成 | 搜索关键词 |
|--------|------|------|------------|
| 森林雨 | Forest Rain | 树叶 + 远风 + 雨 | `森林 雨` |
| 湖边雨 | Lakeside Rain | 雨 + 湖浪 + 远山回响 | `湖水` |
| 山谷雨 | Mountain Rain | 雨 + 风 + 远处溪流 | `森林 雨` |
| 竹林雨 | Bamboo Rain | 雨打竹叶，细碎 | `竹林 雨` |
| 城市雨 | Urban Rain | 雨 + 远车流 | `城市 雨` |
| 乡村雨 | Countryside Rain | 雨 + 鸡鸣 + 狗叫 | `森林 雨` |

**推荐音轨数**：1~2 条  
**占比区间**：5~15%

**本地目录**：`assets/rain_sound/5_env/<keyword>/`

---

## 6. Life Layer（生物层）

**作用**：最容易出精品的部分。头部频道往往有生命层，纯雨频道较少。

**频段**：1k~6kHz 瞬态，稀疏出现。

### 子元素

| 子元素 | 英文 | 特征 | 搜索关键词 |
|--------|------|------|------------|
| 鸟鸣 | Birds | 雨前活跃、雨中少、雨后极多 | `鸟鸣` |
| 青蛙 | Frog | 雨夜神器 | `蛙鸣` |
| 蟋蟀 | Cricket | 夏夜雨 | `蟋蟀` |
| 蝉鸣 | Cicada | 东亚特色 | `蝉鸣` |
| 鸭子 | Duck | 湖边场景 | `鸭子` |
| 水鸟 | Water Birds | 鸬鹚、白鹭、鸳鸯等 | `鸟鸣` |

**推荐音轨数**：1~3 条  
**占比区间**：5~15%

**触发建议**：间隔 15~60s，避免与 Impact 密集区重叠。

**本地目录**：`assets/rain_sound/6_life/<keyword>/`

---

## 7. Comfort Layer（心理舒适层）

**作用**：Rain 睡眠系列与普通「下雨白噪音」的 **分水岭**。不追求画面还原或物理真实，而是营造 **安全感、包裹感、被保护感、可闭眼入睡的放松感**。可以是任何合逻辑的声音或 **多条叠加**（loop 为主）。

**频段**：80Hz~2kHz 中低频包裹 + 可选轻柔高频纹理；宜 **稳、柔、近**，避免惊吓性瞬态。

### 设计原则

| 原则 | 说明 |
|------|------|
| 画龙点睛 | 音量不必大，但听感应「有这一层就不一样了」 |
| 心理 > 物理 | 素材可与画面无直接对应（如伞下声强化安全），须有叙事理由 |
| 持续为主 | 优先 **loop 铺底**；稀疏点缀仅当能增强安心感 |
| 可叠加 | 同轨或多轨叠 2~3 条（如伞下波波 + 极弱炉火噼啪） |

### 子元素（示例）

| 子元素 | 心理功能 | 搜索/来源 |
|--------|----------|-----------|
| 伞下近场 | 被遮挡、安全、波波低频 | `雨伞`（常从 `3_impact` 目录取） |
| 帐篷/屋檐庇护 | 封闭感、避雨 | `雨打屋顶`、帐篷雨 |
| 温暖底噪 | 体温感、室内安心 | 极弱篝火噼啪（`7_accent/篝火`） |
| 柔软包裹 | 毛毯/羽绒质感 | 低频 wind、极柔白噪 |
| 远雷（极弱） | 远处有边界的雨世界 | `雷声`（须极稀疏且远，睡眠向慎用） |

**推荐音轨数**：1~3 条（loop 叠加）  
**占比区间**：5~15% 听感，但 **心理权重高**

**与旧「点缀层」关系**：原 Accent（雷、风铃、船）侧重 **偶发画面事件**；Comfort 侧重 **持续情绪锚点**。雷/风铃等若出现，应服务于安心而非刺激，且多数睡眠场景 **留白即可**。

**本地目录**：`assets/rain_sound/7_accent/`（下载分类暂用）+ 跨层引用 `3_impact/雨伞` 等

---

## （附录）原 Accent 类素材

雷声、风铃、篝火、划船等 **场景点缀** 素材仍在 `assets/rain_sound/7_accent/`。按场景判断是否进入 Comfort 层（如极弱远雷）或 **不使用**。

**本地目录**：`assets/rain_sound/7_accent/<keyword>/`

---

## 分层 → 关键词 → 本地目录对照索引

| 层级 ID | 名称 | 关键词 | 本地目录 |
|---------|------|--------|----------|
| `1_base` | 底噪层 | 风声, 微风, 森林环境, 白噪音 | `assets/rain_sound/1_base/` |
| `2_rain` | 雨层 | 小雨, 下雨, 大雨, 暴雨, 毛毛雨 | `assets/rain_sound/2_rain/` |
| `3_impact` | 击打层 | 雨打树叶, 雨打屋顶, 雨打窗户, 雨伞 | `assets/rain_sound/3_impact/` |
| `4_water` | 水体层 | 水滴, 屋檐滴水, 溪流, 流水, 湖水 | `assets/rain_sound/4_water/` |
| `5_env` | 环境层 | 竹林 雨, 森林 雨, 城市 雨 | `assets/rain_sound/5_env/` |
| `6_life` | 生物层 | 鸟鸣, 蛙鸣, 蟋蟀, 蝉鸣, 鸭子 | `assets/rain_sound/6_life/` |
| `7_comfort` | 心理舒适层 | 雨伞, 篝火, 庇护感素材 | `assets/rain_sound/7_accent/` + 跨层 |

每层 manifest：`assets/rain_sound/<layer_id>/manifest.json`

---

## 参考工程结构示例

> 夏季西湖雨天 + 湖水拍岸 + 鸟鸣 + Felt Piano

```
Base     ├─ Air Tone, Light Wind
Rain     ├─ Light Rain, Rain On Leaves
Water    ├─ Lake Lap, Roof Drip
Life     ├─ Oriental Magpie Robin, White Wagtail
Accent   ├─ Wooden Boat Creak, Paddle Splash   （场景点缀，非 Comfort 必选）
Comfort  ├─ Umbrella Near-field Loop         （心理舒适 · 示例）
Music    ├─ Felt Piano + Hall Reverb
```

成品约 **8~15 条音轨**，听起来自然而非单条雨声循环。

---

## 相关文件

- 原始分层笔记：[level.md](level.md)
- **混音打分**：[scoring_rubric.md](scoring_rubric.md) · `Reaper/scripts/score_mix.py`
- 音效库配置：[scripts/capcut_audio/rain_layers.json](../../scripts/capcut_audio/rain_layers.json)
- 批量下载：[scripts/capcut_audio/download.py](../../scripts/capcut_audio/download.py)
