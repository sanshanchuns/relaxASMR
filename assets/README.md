# 素材库（assets）

| 目录 | 内容 | 来源 |
|------|------|------|
| `sound_effect/rain_sound/` | 雨声系列分层音效 | 剪映 / Envato / Epidemic 下载 + curate |
| `sound_effect/lake_sound/` | 湖泊系列分层音效与音乐 | 剪映 API 下载 + curate |
| `sound_effect/elevenlabs_sound/` | AI 生成音效（按分类子目录） | ElevenLabs API |
| `loop_video/rain_video/` | 雨景循环视频 | 实拍 / 后期 |
| `loop_video/lake_video/` | 湖景循环视频 | 实拍 / 后期 |

## sound_effect 分层目录

雨声 / 湖声均按设计文档七层（或扩展层）组织，每层含关键词子目录与 `manifest.json`（多来源合并，`source` 区分 capcut / envato_elements / epidemic_sound 等）。

下载脚本见 `scripts/capcut_audio`、`scripts/envato_audio`、`scripts/epidemic_audio`。

## elevenlabs_sound 命名

- 目录：`<category>/`（如 `bird/`、`rain/`、`water/`）
- 音频：`api_<id>.mp3`（ElevenLabs PCM → ffmpeg 转 MP3，无额外后期）
- 描述：`api_<id>.json`（提示词、响度、生成参数）
- 单条无 id 时自动递增：`misc/api_001.mp3` …

生成与试听见 [scripts/elevenlabs_audio/README.md](../scripts/elevenlabs_audio/README.md)。
