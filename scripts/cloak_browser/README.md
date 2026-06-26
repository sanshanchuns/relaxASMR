# CloakBrowser 共享能力

各站点 API / 网页填充脚本在 curl 被 **Cloudflare Turnstile** 拦截时，用 [CloakBrowser](https://github.com/CloakHQ/cloakbrowser) 持久化浏览器会话绕过检测。

## 安装

```bash
pip install -r scripts/cloak_browser/requirements.txt
```

首次运行自动下载 stealth Chromium 二进制（约 200MB）。

## 快速用法

```python
import sys
from pathlib import Path

# 将 scripts/ 加入 path（若不在 scripts/ 子项目内运行）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloak_browser import CloakBrowserSession, is_cloudflare_challenge

with CloakBrowserSession(
    profile_name="my_site",
    warm_up_url="https://example.com/",
    warm_up_wait_for="example",
    cookies="session=...; cf_clearance=...",  # 可选
    cookie_domain=".example.com",
) as browser:
    html = browser.fetch(
        "https://example.com/api/list",
        wait_for="items",
        success_check=lambda t: "items" in t,
    )
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `HTTPS_PROXY` / `ALL_PROXY` 等 | 自动传给浏览器（WSL 代理） |
| `CLOAK_BROWSER_PROFILES_DIR` | profile 根目录，默认 `scripts/cloak_browser/.profiles/` |
| `CLOAKBROWSER_LICENSE_KEY` | CloakBrowser Pro 密钥（可选） |

## Profile

每个站点建议独立 `profile_name`，Cookie / 登录态会保留在 `.profiles/<name>/`。

Envato 示例：`profile_name="envato"` + `warm_up_url=https://elements.envato.com/`

## 接入方

- [envato_audio](../envato_audio/README.md) — Envato Elements 音效下载
- [epidemic_audio](../epidemic_audio/README.md) — Epidemic Sound 音效下载
