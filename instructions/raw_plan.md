这是一个典型的 **“内容逆向工程 + 特征量化 + AI生成闭环”** 项目。

如果目标是让 Claude Code、Codex、Cursor 这类 Agent 能长期维护，建议拆成：

```text
Discovery Layer
    ↓
Feature Layer
    ↓
Scoring Layer
    ↓
Generation Layer
    ↓
Validation Layer
```

---

# spec.yaml

```yaml
project:
  name: audio-intelligence-engine
  version: 1.0

domain:
  categories:
    - focus
    - asmr
    - sleep
    - meditation
    - ambience

youtube:
  videos_per_category: 500
  min_duration_min: 30
  metrics:
    - views
    - likes
    - comments
    - retention

audio:
  stem_separation:
    enabled: true

  sources:
    detect_min_confidence: 0.75

  features:
    loudness: true
    frequency: true
    rhythm_density: true
    event_frequency: true
    source_ratio: true
    dynamic_range: true

video:
  scene_analysis: true

  features:
    lighting
    weather
    motion
    color_palette
    camera_movement
    environment_type

scoring:
  target:
    views
    retention

  similarity_min: 0.85

generation:
  sound_library: true
  ai_generation: true

validation:
  human_review: true
  prediction_error_max: 15%
```

---

# 整体架构

```text
YouTube

    ↓

Video Collector

    ↓

Feature Extractor

    ├─ Visual Analyzer
    ├─ Audio Analyzer
    └─ Metadata Analyzer

    ↓

Feature Database

    ↓

Scoring Engine

    ↓

Top Pattern Discovery

    ↓

Audio Generator

    ↓

Popularity Predictor
```

---

# 模块1：量化视频特征

## 输入

```text
关键词：

focus
deep focus
study
sleep
asmr
rain
fireplace
lake
meditation
```

抓取：

```text
标题
频道
发布时间
时长
观看数
点赞数
评论数
```

---

## 视频层分析

Claude负责语义分析：

```text
湖边
篝火
咖啡馆
雨夜
森林
雪景
书房
火车
海浪
```

输出：

```json
{
  "environment":"lake",
  "time":"sunset",
  "weather":"clear",
  "mood":"calm",
  "motion":"slow"
}
```

---

## 视觉特征

### 光照

```text
sunset
golden hour
night
daylight
```

### 色彩

```text
warm
cold
neutral
```

### 动态程度

```text
0~100
```

例如：

```text
静态湖面
15

海浪
45

暴雨
75
```

---

## 情绪标签

Claude打标签：

```text
safe
cozy
peaceful
lonely
nostalgic
immersive
```

输出：

```json
{
  "cozy":92,
  "peaceful":88,
  "immersive":80
}
```

---

# 音频分析模块

这里才是核心。

---

## Stem Separation

推荐：

### Demucs

[Demucs](https://github.com/facebookresearch/demucs?utm_source=chatgpt.com)

---

### AudioSep

[AudioSep](https://github.com/Audio-AGI/AudioSep?utm_source=chatgpt.com)

---

### BirdNET

如果包含鸟叫

[BirdNET](https://birdnet.cornell.edu?utm_source=chatgpt.com)

---

拆出来：

```text
rain
bird
wind
fire
water
paddle
footstep
music
piano
voice
```

---

# 声源量化

例如：

```json
{
  "water_lap": {
      "ratio":35,
      "avg_lufs":-24,
      "events_per_min":18
  },

  "bird": {
      "ratio":5,
      "avg_lufs":-30,
      "events_per_min":3
  },

  "piano": {
      "ratio":40,
      "avg_lufs":-22
  }
}
```

---

# 更高级分析

## Temporal Structure

统计：

```text
前5分钟

中间20分钟

最后5分钟
```

声源变化。

例如：

```text
鸟叫逐渐减少

风声增加

钢琴更稀疏
```

很多高质量 ASMR 都有这种规律。

---

# 特征数据库

最终形成：

```json
{
  "lake":0.87,
  "sunset":0.78,
  "water_lap":0.93,
  "bird":0.65,
  "felt_piano":0.91
}
```

---

# 模块2：单体分析

输入：

```text
一个爆款视频
```

例如：

```text
Lake at Sunset
3M views
```

输出：

---

## 场景

```json
{
  "lake":95,
  "sunset":88,
  "mountain":40
}
```

---

## 声源

```json
{
  "water_lap":40,
  "bird":8,
  "wind":12,
  "felt_piano":40
}
```

---

## 时间结构

```json
{
  "bird_density":"decrease",
  "piano_density":"stable",
  "wind":"increase"
}
```

---

# 一键复刻模块

不是复制原音频。

而是生成：

```text
Feature Clone
```

例如：

```json
{
  "water_lap":35,
  "bird":5,
  "wind":10,
  "felt_piano":50
}
```

然后：

```text
声音库
+
ElevenLabs
+
自建生成模型
```

组合。

---

# 打分系统

核心目标：

```text
Quality Score
```

训练集：

```text
Top 500 视频
```

特征：

```text
视觉特征
音频特征
结构特征
情绪特征
```

标签：

```text
观看数
观看时长
点赞率
```

训练：

```text
XGBoost
LightGBM
CatBoost
```

输出：

```json
{
  "predicted_views":1200000,
  "predicted_retention":72,
  "quality_score":88
}
```

---

# validate.yaml

```yaml
dataset:
  min_videos: 1000

audio_detection:
  precision_min: 0.90

source_classification:
  f1_min: 0.85

score_prediction:
  mae_max: 15%

generation:
  similarity_min: 0.85

human_eval:
  mean_score_min: 8.0

performance:
  analysis_time_max: 120s
```

---

如果是我来设计 v1 → v3 路线，会这样切：

### v1（2周）

只做分析

```text
YouTube抓取
+
Demucs
+
Claude总结
+
特征数据库
```

输出：

```text
为什么这个视频火
```

---

### v2（1个月）

加入评分模型

```text
输入视频
↓
输出质量分
```

开始具备预测能力。

---

### v3（2个月）

加入生成

```text
输入爆款
↓
自动拆解
↓
自动生成类似音频
↓
自动评分
```

形成闭环：

```text
Analyze
    ↓
Learn
    ↓
Generate
    ↓
Predict
    ↓
Optimize
```

这个阶段已经接近一个“ASMR内容研究与自动生产平台”了，而不仅仅是音频分析工具。
