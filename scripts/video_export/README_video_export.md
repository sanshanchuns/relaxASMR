# video_export

成片 MP4 导出与 YouTube 物料生成。

| 脚本 | 用途 |
|------|------|
| `export_mp4.sh` | 循环视频 + 音频 → MP4（H.264 + AAC） |
| `generate_youtube_material.py` | 缩略图 + `youtube.md`（默认 **forest_rain** 爆款文案） |
| `generate_youtube_material.sh` | 上述 Python 的 shell 入口 |

## 典型流程

```bash
# 1. Reaper 渲染 wav 后合成 mp4（默认输出名按视频宽度加 _4k / _fhd / _720p 后缀）
scripts/video_export/export_mp4.sh \
  -v assets/loop_video/rain_video/MVI_6918/MVI_6918_loop_3_fade_0.5.mp4 \
  -a Reaper/Projects/Rain/subprojects/MVI_6918/output/MVI_6918_3h.wav

# 2. 单独生成 YouTube 物料（export 成功后也会自动调用）
scripts/video_export/generate_youtube_material.sh output/MVI_6918_3h_4k.mp4
```

默认 `--style forest_rain`，标题/描述/Tags/封面叠字遵循 [`material_ref/forest_rain.md`](material_ref/forest_rain.md)。经典风格：`--style classic`。

也可在 GUI 中一键生成：[`gui/README.md`](../../gui/README.md) 第 4 步。

## 混音质量评估

RS-PASS 自动打分已移除（见 [`benchmark/README.md`](../../benchmark/README.md)）。  
后续将通过 **爆款声纹** 对标指导；当前以 [`design/rain_series/scoring_rubric.md`](../../design/rain_series/scoring_rubric.md) 人工量表为主。
