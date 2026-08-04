# ElevenLabs 网页通道（图生视频）

官方 `xi-api-key` 对 content generation 经常 403  
（`Programmatic access … not available for this workspace`）。  
网页通道用 **Firebase Bearer**，模型默认 `bytedance-seedance-v2-fast`。

## 自动续期（推荐）

Bearer 约 1 小时过期。一次导出 `refresh_token` 后即可全自动换新：

```bash
# 依赖
pip install playwright
playwright install chromium

# 1) 有头浏览器登录一次（Google 登录 → 进入 Image & Video）
PYTHONPATH=cli:. python -m elevenlabs_http login

# 若报 ERR_PROXY_CONNECTION_FAILED（常见于 ALL_PROXY=socks 端口未开）：
# PYTHONPATH=cli:. python -m elevenlabs_http login --no-proxy
# 或指定可用 HTTP 代理：
# PYTHONPATH=cli:. python -m elevenlabs_http login --proxy http://127.0.0.1:7890

# 2) 之后任意时刻（status 会打印 character 已用/总额）
PYTHONPATH=cli:. python -m elevenlabs_http status
PYTHONPATH=cli:. python -m elevenlabs_http refresh

# 3) 可选：后台每 10 分钟检查并续期
PYTHONPATH=cli:. python -m elevenlabs_http watch
```

GUI / `ElevenLabsWebClient` 在每次请求前会调用 `ensure_fresh_auth()`：  
有 `refresh_token.md` 时，剩余不足 ~3 分钟会自动向 Firebase 换新 Bearer。

### 挂到已开的 Chrome（可选）

```bash
# Windows 示例：先开远程调试 Chrome，再在里面登录 elevenlabs.io
chrome.exe --remote-debugging-port=9222 --user-data-dir="%TEMP%\el-debug"

PYTHONPATH=cli:. python -m elevenlabs_http connect --cdp http://127.0.0.1:9222
```

WSL 访问 Windows Chrome 时，把 `127.0.0.1` 换成 Windows 主机 IP，并放行 9222。

### 可选：profile 失效时自动 headless 再同步

```bash
export ELEVENLABS_AUTO_BROWSER_SYNC=1
```

需要本机已有 `cli/elevenlabs_http/.profile/`（先跑过 `login`）。

## 临时方式（无 refresh 时）

把 Network 里 `content/generations` 的整段 curl 贴进 `mock/generations.md`，  
会自动同步 Bearer / hCaptcha（约 1h 后仍要重贴）。

## 鉴权说明

| 项 | 值 |
|---|---|
| Host | `https://api.us.elevenlabs.io` |
| 鉴权 | `Authorization: Bearer <Firebase ID Token>` |
| 长期凭据 | `refresh_token.md`（IndexedDB `stsTokenManager.refreshToken`） |
| Cookie / fern_token | **不够**，API 不认 |

## 自检

```bash
PYTHONPATH=cli:. python -m elevenlabs_http status
```
