# 视频分析 · MVI_6953

> 子工程：`subprojects/MVI_6953`
> 视频：`assets/loop_video/rain_video/MVI_6953/MVI_6953_loop_0.95_dur_8_fade_0.5.mp4`
> 分析日期：2026-07-07
> 状态：**Looper 首帧代表全片**（`create_rain_subproject.py` 自动生成，§一 请人工核对）
> 系列：**Rain 睡眠**
> 成片时长：**3 h**

---

# 一、视频画面拆解

## 1.1 技术摘要

| 项 | 值 |
|----|-----|
| 分辨率 | 3840×2160（h264） |
| 时长 | 7.34 s |
| 内嵌音轨 | **无** |
| 文件名线索 | loop=0 fade=0.5 |

## 1.2 画面描述

**自动启发**：首帧 **绿色偏多** → 倾向林间/草地雨景（启发式）。

**是**：（待补）
**不是**：（待补）

---
# 二、视频原声拆解

> 本文件 **无内嵌音轨**，配方依据画面启发 + 睡眠系列默认模板。

---
# 三、六层配方 + Dynamic（自动初版）

> 架构：[rain_sound_design.md](../../../../design/rain_series/rain_sound_design.md)
> 轨 1–6 = 素材层 · 轨 7 = 视频 · **Dynamic** = `1_rain` 音量包络（无独立轨）

## 3.1 配方总览

| 轨 | layer_id | 名称 | 模式 | 音量 |
|----|----------|------|------|------|
| 1 | `1_rain` | 小雨主雨势 | loop | 1.0 |
| 3 | `3_environment` | 环境空间 | loop | 0.26 |
| 4 | `4_water` | 水体/滴水 | loop | 0.18 |
| 6 | `6_human` | 留白（待选） | loop | 0.0 |
| 2 | `2_impact` | 雨打树叶 | scatter（手动散布） | 0.5 |
| 5 | `5_wildlife` | 远处鸟鸣 | scatter（手动散布） | 0.28 |
| 7 | video | Video · MVI_6953 loop | render_only | mute |

详细路径见 `scripts/asmr_config.lua` · 生成：`create_rain_subproject.py` / GUI

打开工程后运行 **`asmr_apply_recipe.lua`**（铺循环 + **`1_rain` 音量包络**），再逐轨运行 **`asmr_scatter_track.lua`** 散布稀疏层。
