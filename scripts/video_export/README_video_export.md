# 成片导出（视频 + 音频）

循环 looper 视频 + Reaper 导出的长音频 → YouTube 用 MP4。

## 脚本

| 文件 | 说明 |
|------|------|
| `export_mp4.sh` | ffmpeg 合成：`-stream_loop` 视频 + 音频，`-shortest` 跟音频时长 |
| `generate_youtube_material.sh` | 缩略图 + `youtube.md` 物料（export 成功后可选自动调用） |
| `generate_youtube_material.py` | 物料生成 + **benchmark**（`material/<stem>/benchmark.md`） |
| `youtube_presets.json` | 各系列标题/说明模板 |
| [`../../benchmark/score.py`](../../benchmark/score.py) | RS-PASS 单独打分（默认前 300s） |

## 用法

在仓库根目录：

```bash
scripts/video_export/export_mp4.sh \
  -v assets/loop_video/rain_video/MVI_6918/MVI_6918_loop_3_fade_0.5.mp4 \
  -a Reaper/Projects/Rain/subprojects/MVI_6918/output/MVI_6918_3h.wav
# 默认输出：与音频同目录 · <stem>_4k.mp4
```

编码过程中同一行刷新 **Elapsed / Remaining / 进度%**。

| 参数 | 说明 |
|------|------|
| `--encoder cpu` | libx264（默认） |
| `--encoder nvenc` | NVIDIA GPU `h264_nvenc` |
| `-d SEC` | 限制输出时长（默认跟音频全长） |
| `--skip-benchmark` | 跳过 theory 音频 benchmark |
| `--benchmark-duration SEC` | benchmark 分析时长（默认 300） |

合成成功后会自动跑 **YouTube 物料**（含 benchmark）。若物料失败，export 会在 mp4 同目录写入 `<stem>_benchmark.json`。

单独 RS-PASS 打分：

```bash
python3 benchmark/score.py path/to/render.mp4
python3 benchmark/score.py path/to/mix.wav --mode sleep --duration 300
```

单独生成物料 + benchmark：

```bash
scripts/video_export/generate_youtube_material.sh path/to/render.mp4
```

## 依赖

- `ffmpeg`（NVENC 需对应构建）
- 物料生成：`pip install pillow`
