# 视频分析 · \<场景 ID\>

> 子工程：`subprojects/<场景 ID>`  
> 视频：`assets/loop_video/rain_video/<文件名>.mp4`  
> 分析日期：YYYY-MM-DD  
> 状态：**Looper 首帧代表全片**（循环段变化极小）  
> 系列：**Rain 睡眠**（专注 / 钢琴 solo 属 **Lake**，勿混用）  
> 成片时长：**3 h**（`duration_hours` 可配置）

---

# 一、视频画面拆解

## 1.1 技术摘要

| 项 | 值 |
|----|-----|
| 分辨率 | |
| 时长 | |
| 编码 | |
| 文件名线索 | |

## 1.2 画面描述

**是**：  
**不是**：

## 1.3 场景归类与标签

### 推荐场景标签（Rain · 睡眠向）

| 标签 | 匹配度 | 说明 |
|------|--------|------|
| | | |

---

# 二、视频原声拆解

> 工具：`python3 Reaper/scripts/analyze_video_audio.py --scene <场景 ID> --update-doc`

## 2.1 音轨技术摘要

## 2.2 频段能量分布

## 2.3 六层听感（原声客观拆解）

| 层 | 原声强弱 | 听感线索 |
|----|----------|----------|
| `1_rain` 雨层 | | |
| `2_impact` 击打 | | |
| `3_environment` 环境 | | |
| `4_water` 水体 | | |
| `5_wildlife` 生物 | | |
| `6_human` 人类 | | |

本节仅描述视频内嵌音轨；最终配方见 **§三**。

---

# 三、六层配方 + Dynamic（最终）

> 架构：[rain_sound_design.md](../../../../design/rain_series/rain_sound_design.md)  
> 轨 1–6 = 素材层 · 轨 7 = 视频 · **Dynamic** = `1_rain` 音量包络（无独立轨）

## 3.1 配方总览

| 轨 | layer_id | 名称 | 模式 | 音量 | 素材 | 原因 |
|----|----------|------|------|------|------|------|
| 1 | `1_rain` | | loop + Dynamic | | | |
| 2 | `2_impact` | | scatter | | | |
| 3 | `3_environment` | | loop | | | |
| 4 | `4_water` | | loop | | | |
| 5 | `5_wildlife` | | scatter | | | |
| 6 | `6_human` | | loop | | | |
| 7 | video | | render_only | mute | | |

## 3.2 各层详解

（每层：关键词、优先级、理由、选用）

## 3.3 工程操作

| 文件 | 说明 |
|------|------|
| `scripts/asmr_config.lua` | Reaper 配方（与 §3.1 同步） |

生成：`python3 Reaper/scripts/generate_subproject.py --scene <场景 ID>`

打开工程后运行 **`asmr_apply_recipe.lua`**（铺循环/稀疏 + **`1_rain` 长时音量包络**）。

---

## 待确认 / 后续

- [x] Looper 首帧代表全片
