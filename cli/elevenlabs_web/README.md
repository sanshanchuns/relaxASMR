# ElevenLabs 网页 Playwright（UI 自动化）

与 `cli/elevenlabs_http/`（Firebase Bearer HTTP）并存。系列视频回退链在 HTTP 失败时使用本包。

```bash
PYTHONPATH=cli:. python -m elevenlabs_web login
PYTHONPATH=cli:. python -m elevenlabs_web status
PYTHONPATH=cli:. python -m elevenlabs_web generate \
  --image series_001.png --prompt "..." --out series_001.mp4
```

Profile：`cli/elevenlabs_web/.profile/`

HTTP 鉴权（token）：`PYTHONPATH=cli:. python -m elevenlabs_http login`
