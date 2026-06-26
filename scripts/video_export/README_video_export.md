# 成片导出（视频 + 音频）

循环 looper 视频 + Reaper 导出的长音频 → YouTube 用 MP4。

## 脚本

| 文件 | 说明 |
|------|------|
| `export_mp4.sh` | ffmpeg 合成：`-stream_loop` 视频 + 音频，`-shortest` 跟音频时长 |
| `generate_youtube_material.sh` | 缩略图 + `youtube.md` 物料（export 成功后可选自动调用） |
| `generate_youtube_material.py` | 物料生成（`auto_from_scene` 预设按画面推断标题/说明/标签；`--thumb-title` / `--thumb-subtitle` 可覆盖） |
| `youtube_presets.json` | 各系列标题/说明模板 |

## 用法

在仓库根目录：

```bash
scripts/video_render/export_mp4.sh \
  -v assets/rain_video/MVI_6918/MVI_6918_loop_3_fade_0.5.mp4 \
  -a Reaper/Projects/Rain/subprojects/MVI_6918/MVI_6918.wav \
  -o Reaper/Projects/Rain/subprojects/MVI_6918/MVI_6918_final.mp4 \
  --encoder nvenc
```

编码过程中同一行刷新 **Elapsed / Remaining / 进度%**。

| 参数 | 说明 |
|------|------|
| `--encoder cpu` | libx264（默认） |
| `--encoder nvenc` | NVIDIA GPU `h264_nvenc` |
| `-d SEC` | 限制输出时长（默认跟音频全长） |

旧路径 `Reaper/Projects/*/scripts/export_mp4.sh` 仍可用（转发到 `scripts/video_render/`）。

## 依赖

- `ffmpeg`（NVENC 需对应构建）
- 物料生成：`pip install pillow`
