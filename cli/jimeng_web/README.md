# 即梦网页 Playwright

入口：[即梦视频生成首页](https://jimeng.jianying.com/ai-tool/home?type=video&workspace=undefined)

```bash
pip install playwright && playwright install chromium
PYTHONPATH=cli:. python -m jimeng_web login
PYTHONPATH=cli:. python -m jimeng_web status
PYTHONPATH=cli:. python -m jimeng_web generate \
  --image /path/series_001.png \
  --prompt "Animate the provided image..." \
  --out /path/series_001.mp4
PYTHONPATH=cli:. python -m jimeng_web generate-t2v \
  --prompt "固定机位拍摄原始热带雨林，大暴雨…" \
  --out /path/out.mp4 \
  --duration 4
PYTHONPATH=cli:. python -m jimeng_web agentic \
  --prompt "场景：原始热带雨林；雨型：暴雨；请输出六槽原子 JSON" \
  --out /tmp/agent_reply.txt
```

Agent 入口默认：`type=agentic`（可用 `JIMENG_AGENTIC_URL` 覆盖）。

Profile：`cli/jimeng_web/.profile/`（已 gitignore）

环境变量：
- `JIMENG_CANVAS_URL` — 画布 URL
- `JIMENG_AGENTIC_URL` — Agent 页 URL
- `JIMENG_VIDEO_MODEL` — 默认 `Seedance 2.0 VIP`（非 mini / Fast VIP）
- `JIMENG_REF_MODE` — 默认 `首尾帧`（同图作首+尾，利于 seamless loop；可选 `全能参考`）
- `JIMENG_DURATION_SEC` — 默认 `5`
- `JIMENG_HEADLESS=1` — 无头模式（默认有头）

注意：Agent 对话与视频生成、额度刷新共用同一 Chromium profile，不可并行。
