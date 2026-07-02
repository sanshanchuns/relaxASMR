# scripts

| 目录 | 用途 |
|------|------|
| [cloak_browser/](cloak_browser/README.md) | **共享** CloakBrowser 会话（过 Cloudflare，供各 API 填充脚本复用） |
| [envato_audio/](envato_audio/README.md) | Envato Elements 分层音效下载 |
| [epidemic_audio/](epidemic_audio/README.md) | Epidemic Sound 分层音效下载 |
| [capcut_audio/](capcut_audio/README.md) | 剪映音效 / 音乐下载 |
| [elevenlabs_audio/](elevenlabs_audio/README.md) | ElevenLabs AI 音效生成 |
| [ai_audio/](ai_audio/) | AI 音效生成与试听 |
| [video_export/](video_export/README_video_export.md) | 成片 MP4 导出、YouTube 物料 |
| [../benchmark/README.md](../benchmark/README.md) | 声学理论参考 · 爆款声纹（规划中） |

新做「网页/API 填充」脚本时，若遇 Cloudflare，优先复用 `cloak_browser.CloakBrowserSession`。
