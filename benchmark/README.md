# RS-PASS 音频 Benchmark（本仓库内置）

对 Rain 系列**渲染成品**或 **Reaper 混音预览**做 **RS-PASS** 七维 + 色噪声类型打分。  
理论：[theory.md](theory.md) · 人工对照：[design/rain_series/scoring_rubric.md](../design/rain_series/scoring_rubric.md)

> **Reaper / 导出流水线**使用本目录，**不依赖** sibling `youtube_analysis`。  
> `youtube_analysis` 仍保留 YouTube 批量、频道、细分调研等扩展能力。

## 文件

| 文件 | 说明 |
|------|------|
| `score.py` | CLI + `run_benchmark()` |
| `rs_pass.py` | 七维测量与加权计分 |
| `noise_type.py` | 粉/白/棕噪声分类 |
| `recommendations.py` | 文本修改建议 |
| `track_actions.py` | 轨级可执行建议（供 Reaper 一键应用） |
| `rpp_context.py` | 解析 `.rpp` + `asmr_config.lua` |
| `theory.md` | RS-PASS 指标定义 |

## 用法

```bash
# 单文件（默认前 300s，不足则全长）
python3 benchmark/score.py path/to/render.mp4

# Reaper 混音打分（Lua asmr_score_mix.lua 内部调用 scoring_bridge → 本目录）
python3 scripts/video_export/scoring_bridge.py preview.wav \
  --output-dir output/scoring --rpp path/to/scene.rpp \
  --report-stem mix_score --summary-file output/scoring/mix_score_summary.txt

# 带 RPP 轨级建议
python3 benchmark/score.py path/to/mix.wav \
  --rpp Reaper/Projects/Rain/subprojects/MVI_6918/MVI_6918.rpp
```

## Reaper 集成

- **`Reaper/scripts/asmr_score_mix.lua`** — 渲染混音 → `scoring_bridge.py` → 本 benchmark
- 输出 `output/scoring/mix_score.md` + `mix_score_actions.lua`（轨级一键修改）

## 依赖

- Python 3 · numpy · ffmpeg · ffprobe
- 与 `youtube_analysis` 的 `scoring/` 同源，可独立演进
