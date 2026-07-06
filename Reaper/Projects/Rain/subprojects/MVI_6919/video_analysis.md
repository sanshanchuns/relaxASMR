# 视频分析 · MVI_6919

> 子工程：`subprojects/MVI_6919`
> 视频：`assets/loop_video/rain_video/MVI_6919/MVI_6919_loop_08_0.97_dur_4_fade_0.5_01.mp4`
> 分析日期：2026-07-06
> 状态：**Looper 首帧代表全片**（`create_rain_subproject.py` 自动生成，§一 请人工核对）
> 系列：**Rain 睡眠**
> 成片时长：**3 h**

---

# 一、视频画面拆解

## 1.1 技术摘要

| 项 | 值 |
|----|-----|
| 分辨率 | 3840×2160（h264） |
| 时长 | 3.47 s |
| 内嵌音轨 | 有 |
| 文件名线索 | loop=8 fade=0.5 |

## 1.2 画面描述

**自动启发**：首帧 **绿色偏多** → 倾向林间/草地雨景（启发式）。

**是**：（待补）
**不是**：（待补）

---
# 二、视频原声拆解

> 嵌入式音轨自动分析（FFT 频段 + 瞬态计数）。Looper 循环段整体代表全片听感。
> 源文件：`/Users/angel/Documents/workspace/relaxASMR/assets/loop_video/rain_video/MVI_6919/MVI_6919_loop_08_0.97_dur_4_fade_0.5_01.mp4`

## 2.1 音轨技术摘要

| 项 | 值 |
|----|-----|
| 音轨时长 | 3.48 s |
| RMS | -120.0 dB |
| 峰值 | -120.0 dB |
| 瞬态群（粗估） | 0 |

## 2.2 频段能量分布

| 频段 | 范围 | 占比 | 可能对应 |
|------|------|------|----------|
| sub_low | 20–200 Hz | 0.0% | 底噪 / 远雷 / 湖面低频 |
| low_mid | 200–500 Hz | 0.0% | 水体 / 环境厚度 |
| mid | 500 Hz–2 kHz | 0.0% | **雨层主体** |
| high_mid | 2–6 kHz | 0.0% | 雨丝 / 击打 |
| high | 6 kHz+ | 0.0% | 细小雨滴 / 空气 |

## 2.3 七层听感（原声客观拆解）

| 层 | 原声强弱 | 听感线索 |
|----|----------|----------|
| 1_rain 雨层 | **无/极弱** | 500 Hz–6 kHz 连续能量 · 雨势主体 |
| 2_impact 击打 | **无/极弱** | 2–8 kHz 瞬态峰 · 雨滴撞击 |
| 3_environment 环境 | **无/极弱** | 空气/风/地点包络 · 空间感 |
| 4_water 水体 | **无/极弱** | 200 Hz–2 kHz 流动 · 滴水/溪流 |
| 5_wildlife 生物 | **无/极弱** | 1–6 kHz 稀疏瞬态 · 鸟鸣等 |
| 6_human 人类 | **无/极弱** | 80Hz–2kHz 近场 · 安全感锚点 |

本节仅描述 **视频内嵌音轨** 的客观听感，最终混音配方见 **§三**（可在原声基础上创新，但须符合画面逻辑）。

---

# 三、六层配方 + Dynamic（自动初版）

> 架构：[rain_sound_design.md](../../../../design/rain_series/rain_sound_design.md)
> 轨 1–6 = 素材层 · 轨 7 = 视频 · **Dynamic** = `1_rain` 音量包络（无独立轨）

## 3.1 配方总览

| 轨 | layer_id | 名称 | 模式 | 音量 |
|----|----------|------|------|------|
| 1 | `1_rain` | 小雨主雨势 | loop + **Dynamic** | 1.0 |
| 3 | `3_environment` | 环境空间 | loop | 0.26 |
| 4 | `4_water` | 水体/滴水 | loop | 0.18 |
| 6 | `6_human` | 炉火噼啪 | loop | 0.38 |
| 2 | `2_impact` | 雨打树叶 | scatter (3–8 min) | 0.5 |
| 5 | `5_wildlife` | 远处鸟鸣 | scatter (12–28 min) | 0.22 |
| 7 | video | Video · MVI_6919 loop | render_only | mute |

详细路径见 `scripts/asmr_config.lua` · 生成：`create_rain_subproject.py` / GUI

## 3.2 声源选取理由

| layer_id | 素材 | 选取理由 |
|----------|------|----------|
| `1_rain` | `179242_Rain,_Vegetation,_Light_Rain_In_A_Field_Of_Bananas_Trees_01.mp3` | Rain 睡眠系列默认轻雨主层 · 从 `rain_sound/1_rain/intensity/light` 按字母序选取 `179242_Rain,_Vegetation,_Light_Rain_In_A_Field_Of_Bananas_Trees_01.mp3` |
| `2_impact` | `152602_Rain,_Vegetation,_Rain,_Daytime,_Rain_Drops_Hitting_Palm_Lea.mp3` | 默认雨打树叶（vegetation/leaves） · 从 `rain_sound/2_impact/vegetation/leaves` 按字母序选取 `152602_Rain,_Vegetation,_Rain,_Daytime,_Rain_Drops_Hitting_Palm_Lea.mp3` |
| `3_environment` | `153479_Rain,_General,_Tropical,_Moderate_Monsoon_Rain_Open_Garage_P.mp3` | 首帧绿色偏多 → 强化林间 ambience · 从 `rain_sound/3_environment/ambience/forest` 按字母序选取 `153479_Rain,_General,_Tropical,_Moderate_Monsoon_Rain_Open_Garage_P.mp3` |
| `4_water` | `237672_Rain,_Plastic,_Drips_On_Verandah_Roof.mp3` | 默认滴水/细流 · 从 `rain_sound/4_water/dripping` 按字母序选取 `237672_Rain,_Plastic,_Drips_On_Verandah_Roof.mp3` |
| `5_wildlife` | `9PBX76J_Birds.mp3` | 从 `rain_sound/5_wildlife/birds` 按字母序选取 `9PBX76J_Birds.mp3` · 原声 wildlife「无/极弱」→ scatter 音量降至 0.22 |
| `6_human` | `N5KW5NM_Fire_Crackle_CU_Pops_Small_Campfire.mp3` | 从 `rain_sound/6_human/fire` 按字母序选取 `N5KW5NM_Fire_Crackle_CU_Pops_Small_Campfire.mp3` |

打开工程后运行 **`asmr_apply_recipe.lua`**（铺循环/稀疏 + **`1_rain` 长时音量包络**）。
