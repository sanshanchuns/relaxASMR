# RS-PASS 音频 Benchmark

对 Rain 系列**渲染成品**（mp4 / wav）做 **RS-PASS**（雨声舒缓安逸度）自动打分。  
理论依据：[theory.md](theory.md) §四 · 人工对照规则：[design/rain_series/scoring_rubric.md](../design/rain_series/scoring_rubric.md)

## 文件

| 文件 | 说明 |
|------|------|
| `score.py` | 命令行入口 |
| `rs_pass.py` | 七维测量与加权计分 |
| `theory.md` | RS-PASS 指标定义与目标域 |

## 用法

在**仓库根目录**运行：

```bash
# 默认：sleep 模式 · 分析前 300 秒 · Markdown 打印到终端
python3 benchmark/score.py path/to/render.mp4

# 写入报告（benchmark.md + benchmark.json）
python3 benchmark/score.py path/to/render.mp4 \
  --output-dir Reaper/Projects/Rain/subprojects/MVI_6927/output/material/MVI_6927

# 专注向 / 自定义时长 / JSON  stdout
python3 benchmark/score.py path/to/mix.wav --mode focus --duration 300 --json
```

### 参数

| 参数 | 说明 |
|------|------|
| `input` | mp4、wav 等 ffmpeg 可读文件 |
| `--duration SEC` | 只分析开头 N 秒，默认 **300** |
| `--mode sleep\|focus` | 响度目标：sleep ≤3 Sone / focus ≤8 Sone |
| `--output-dir DIR` | 输出 `benchmark.md`、`benchmark.json` |
| `--report-stem NAME` | 报告文件名前缀，默认 `benchmark` |
| `--json` | JSON 打印到 stdout |
| `--markdown` | Markdown 打印到 stdout |

### 输出示例

```
==> RS-PASS: 87.3 / 100 (优秀, 前 300s) → .../benchmark.json
```

`benchmark.md` 含总分、七项得分、原始代理测量值。

## 七项指标（权重）

| 指标 | 权重 | 说明 |
|------|------|------|
| N_5 动态峰值响度 | 22% | 响度甜区 + P95−P5 宏观起伏 |
| S_50 尖锐度 | 18% | 过高/过低均扣分 |
| R_5 粗糙度 | 13% | |
| IACC | 13% | 过低=假宽，过高=窄 |
| F_50 波动强度 | 9% | |
| SI 光谱不规则度 | 9% | |
| T_max 纯音色调度 | 6% | |
| Crest 峰均差 | 10% | 稀疏层/导出尖峰 |

## 等级

| 总分 | 等级 | 含义 |
|------|------|------|
| ≥88 | 极品 | 各维接近甜区中心（应少见） |
| 81–87 | 优秀 | 明显好于平均，可出片 |
| 62–80 | 普通 | 合格日常雨片，有优化空间 |
| <62 | 劣质 | 需返工 |

> **v2 校准**：由「不超标即满分」改为 **ideal 甜区** 打分；普通安静雨片多在 **62–80**，勿与旧版 100 分直接对比。代理量非实验室级，可按盲听微调 `rs_pass.py` 中 `TARGETS`。

## 流水线集成

**生成 YouTube 物料时**（默认附带 benchmark）：

```bash
python3 scripts/video_export/generate_youtube_material.py path/to.mp4
# → output/material/<stem>/benchmark.md
```

**export_mp4 合成成功后**同样会跑物料 + benchmark；跳过：

```bash
scripts/video_export/export_mp4.sh ... --skip-benchmark
scripts/video_export/generate_youtube_material.py ... --skip-benchmark
```

## 注意

- 打分对象是**混音后的成品**，不是单轨；距离层 / 配方结构请对照 `asmr_config.lua` 人工检查（见 scoring_rubric.md）。
- 与 `Reaper/scripts/score_mix.py` 不是同一套标准；新片以 **RS-PASS / benchmark** 为准。
