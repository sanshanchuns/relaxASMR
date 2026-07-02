# 成片导出（视频 + 音频）

循环 looper 视频 + Reaper 导出的长音频 → YouTube 用 MP4。

## 脚本

| 文件 | 说明 |
|------|------|
| `export_mp4.sh` | ffmpeg 合成：`-stream_loop` 视频 + 音频，`-shortest` 跟音频时长 |
| `generate_youtube_material.sh` | 缩略图 + `youtube.md` 物料（export 成功后可选自动调用） |
| `generate_youtube_material.py` | 物料生成 + **RS-PASS**（`material/<stem>/benchmark.md`） |
| `scoring_bridge.py` | 调用本仓库 [`benchmark/`](../../benchmark/README.md) |
| `youtube_presets.json` | 各系列标题/说明模板 |

## RS-PASS 打分

核心在 **`benchmark/`**（本仓库内置）。Reaper Lua 与导出物料经 `scoring_bridge.py` 调用，**不依赖** sibling `youtube_analysis`。

```bash
python3 benchmark/score.py path/to/render.mp4
```

YouTube 批量 / 频道 / 细分调研 → 可选 sibling [`../youtube_analysis`](../youtube_analysis/README.md)。

## 用法

```bash
scripts/video_export/export_mp4.sh \
  -v assets/loop_video/rain_video/MVI_6918/MVI_6918_loop_3_fade_0.5.mp4 \
  -a Reaper/Projects/Rain/subprojects/MVI_6918/output/MVI_6918_3h.wav
```

| 参数 | 说明 |
|------|------|
| `--skip-benchmark` | 跳过 RS-PASS 打分 |
| `--benchmark-duration SEC` | 分析时长（默认 300；不足则全长） |

## 依赖

- `ffmpeg` · 物料：`pip install pillow` · 打分：`numpy`
