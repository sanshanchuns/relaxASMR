如果这个项目只有两个 AI 主力（Claude Code 和 Cursor Composer 2.5），我的建议是：

## 分工原则

### Claude：负责“理解和判断”

擅长：

```text
语义分析
模式发现
内容总结
特征设计
Prompt生成
研究型任务
复杂重构
```

例如：

```text
分析100个ASMR视频

总结：
- 什么场景最常见
- 什么声音组合最常见
- 什么时间结构最常见
- 哪些因素和观看时长强相关
```

这是 Claude 的强项。

---

### Composer：负责“执行和编码”

擅长：

```text
快速写代码
补全代码
修改代码
搭项目框架
写接口
写测试
修Bug
```

例如：

```text
实现 Demucs 调用

实现 BirdNET 调用

实现 Youtube 抓取

实现 Feature Store
```

Composer 通常速度更快。

---

# 在你的项目里的具体分工

## 1. Architecture

### Claude

让 Claude 输出：

```text
spec.yaml

schema.sql

feature_definition.md

scoring_design.md

roadmap.md
```

例如：

```text
定义：

bird_density

计算公式

单位

取值范围

权重建议
```

这种属于架构设计。

---

## 2. Youtube Collector

### Composer

直接写：

```python
youtube_collector.py
```

包括：

```text
yt-dlp
youtube api

sqlite

postgres
```

这些 Composer 很强。

---

## 3. Audio Pipeline

### Composer

写：

```text
Demucs

AudioSep

BirdNET

Librosa
```

相关调用。

例如：

```python
extract_stems()
detect_birds()
calculate_lufs()
```

直接让它生成。

---

## 4. 声源分类体系

### Claude

这个不要让 Composer 设计。

例如：

```text
water
```

到底拆成：

```text
waterfall
river
lake_lap
ocean_wave
rain
```

还是：

```text
water
```

这是知识设计问题。

Claude 更适合。

---

## 5. Feature Engineering

最适合 Claude。

例如：

分析1000个视频后：

```text
哪些特征保留？

哪些没价值？

哪些需要合并？
```

Claude 可以看统计结果后给建议。

例如：

```text
bird_density
bird_species_count
```

高度相关。

Claude会建议：

```text
合并
```

---

## 6. 数据库设计

### 第一版

Claude

设计：

```sql
videos

audio_features

video_features

scores

predictions
```

---

### 落地

Composer

生成：

```sql
migration
orm
repository
```

---

## 7. Scoring Engine

### Claude

设计：

```text
quality score

engagement score

immersion score

cozy score
```

以及：

```text
权重
```

---

### Composer

实现：

```python
xgboost

lightgbm

catboost
```

训练代码。

---

## 8. 爆款分析报告

这是 Claude 的主场。

输入：

```json
100个特征
```

输出：

```markdown
为什么这个视频火：

1. 日落湖景
2. 暖色调
3. 低密度钢琴
4. 水声占比38%
5. 鸟叫每分钟2~4次
```

这部分非常适合 Claude。

---

## 9. 一键复刻

### Composer

负责：

```text
调用 ElevenLabs

调用音频库

混音

导出
```

---

### Claude

负责生成：

```json
{
  "bird": 5,
  "water": 35,
  "piano": 40,
  "wind": 20
}
```

即：

```text
生成蓝图
```

---

# Agent 工作流

实际上这个项目最舒服的模式是：

```text
Claude
    ↓
输出规范

Composer
    ↓
实现代码

Claude
    ↓
Review代码

Composer
    ↓
修复

Claude
    ↓
分析结果
```

形成循环。

---

# 甚至可以直接建三个目录

```text
/docs
```

Claude负责

```text
spec.yaml
feature_definition.md
research.md
```

---

```text
/backend
```

Composer负责

```text
collector
pipeline
database
api
```

---

```text
/reports
```

Claude负责

```text
爆款分析报告
趋势分析
评分解释
```

---

对于你这个 ASMR 项目，我会把 AI 工作量大概分成：

```text
Claude      60%
Composer    40%
```

因为真正难的部分不是：

```text
怎么拆音频
```

而是：

```text
什么特征值得拆
什么特征和爆款相关
如何定义评分体系
如何从爆款归纳规律
```

这些都属于“研究员”工作，而不是“程序员”工作，Claude 通常比 Composer 更适合。
