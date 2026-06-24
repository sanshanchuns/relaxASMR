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
└── 7. Accent Layer（点缀层）    — 雷声、风铃、篝火等
```

## 混音原则

| 原则 | 说明 |
|------|------|
| 持续稳定 > 丰富变化 | 专注/睡眠赛道以稳定底床为主 |
| 主体环境声 70~90% | Base + Rain + Impact + Water 占主体 |
| 点缀声 5~20% | Life + Accent 低频出现 |
| 音轨数 | 成品工程通常 8~15 条，素材库每层 3~8 条候选 |

### 频段避让

| 层级 | 主要频段 | 混音建议 |
|------|----------|----------|
| Base | 100Hz~8kHz 宽频 | 音量最低，铺底不抢戏；EQ 可略削 200~400Hz 避免浑浊 |
| Rain | 500Hz~6kHz | 主体，占 30~50% 听感 |
| Impact | 2k~8kHz | 与 Rain 高频重叠，Impact 音量宜低于 Rain 20~30% |
| Water | 200Hz~4kHz | 中低频流动感，与 Base 低频注意平衡 |
| Life | 1k~6kHz 瞬态 | 稀疏触发，避免与 Impact 同时密集出现 |
| Accent | 全频 | 极低密度，远雷/风铃等间隔 30s+ |

### 素材时长建议

| 类型 | 建议时长 | 循环方式 |
|------|----------|----------|
| Base / Rain | ≥60s | 无缝循环或长片段 |
| Impact | 10~60s | 随机 scatter 叠加 |
| Water | 30~120s | 循环或长 fade |
| Life / Accent | 3~30s | 事件触发，不循环 |

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

**本地目录**：`scripts/capcut_audio/output/1_base/<keyword>/`

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

**本地目录**：`scripts/capcut_audio/output/2_rain/<keyword>/`

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

**本地目录**：`scripts/capcut_audio/output/3_impact/<keyword>/`

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

**本地目录**：`scripts/capcut_audio/output/4_water/<keyword>/`

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

**本地目录**：`scripts/capcut_audio/output/5_env/<keyword>/`

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

**本地目录**：`scripts/capcut_audio/output/6_life/<keyword>/`

---

## 7. Accent Layer（点缀层）

**作用**：频率低，但极大提升沉浸感。

**频段**：全频，事件型。

### 子元素

| 子元素 | 英文 | 特征 | 搜索关键词 |
|--------|------|------|------------|
| 远雷 | Distant Thunder | 最舒服 | `雷声` |
| 近雷 | Close Thunder | 刺激 | `雷声` |
| 木船声 | Boat Creak | 湖边常见 | `划船` |
| 划桨声 | Paddle | 湖边核心元素 | `划船` |
| 风铃 | Wind Chime | 日式雨景 | `风铃` |
| 柴火 | Fireplace | 雨夜小屋 | `篝火` |

**推荐音轨数**：0~2 条  
**占比区间**：0~10%

**触发建议**：远雷间隔 30s+，风铃/篝火极低密度。

**本地目录**：`scripts/capcut_audio/output/7_accent/<keyword>/`

---

## 分层 → 关键词 → 本地目录对照索引

| 层级 ID | 名称 | 关键词 | 本地目录 |
|---------|------|--------|----------|
| `1_base` | 底噪层 | 风声, 微风, 森林环境, 白噪音 | `scripts/capcut_audio/output/1_base/` |
| `2_rain` | 雨层 | 小雨, 下雨, 大雨, 暴雨, 毛毛雨 | `scripts/capcut_audio/output/2_rain/` |
| `3_impact` | 击打层 | 雨打树叶, 雨打屋顶, 雨打窗户, 雨伞 | `scripts/capcut_audio/output/3_impact/` |
| `4_water` | 水体层 | 水滴, 屋檐滴水, 溪流, 流水, 湖水 | `scripts/capcut_audio/output/4_water/` |
| `5_env` | 环境层 | 竹林 雨, 森林 雨, 城市 雨 | `scripts/capcut_audio/output/5_env/` |
| `6_life` | 生物层 | 鸟鸣, 蛙鸣, 蟋蟀, 蝉鸣, 鸭子 | `scripts/capcut_audio/output/6_life/` |
| `7_accent` | 点缀层 | 雷声, 篝火, 风铃, 划船 | `scripts/capcut_audio/output/7_accent/` |

每层 manifest：`scripts/capcut_audio/output/<layer_id>/manifest.json`

---

## 参考工程结构示例

> 夏季西湖雨天 + 湖水拍岸 + 鸟鸣 + Felt Piano

```
Base     ├─ Air Tone, Light Wind
Rain     ├─ Light Rain, Rain On Leaves
Water    ├─ Lake Lap, Roof Drip
Life     ├─ Oriental Magpie Robin, White Wagtail
Accent   ├─ Wooden Boat Creak, Paddle Splash
Music    ├─ Felt Piano + Hall Reverb
```

成品约 **8~15 条音轨**，听起来自然而非单条雨声循环。

---

## 相关文件

- 原始分层笔记：[level.md](level.md)
- 音效库配置：[scripts/capcut_audio/layers.json](../../scripts/capcut_audio/layers.json)
- 批量下载：[scripts/capcut_audio/download.py](../../scripts/capcut_audio/download.py)
