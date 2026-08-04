"""ElevenLabs Image & Video：网页会话通道（Firebase Bearer）+ 辅助工具。

官方 ``xi-api-key`` 对 content generation 仍可能返回
「Programmatic access … not available for this workspace」（工作区级门禁，
与 Key 是否「限制密钥」无关）。网页通道绕开该门禁。

包名故意用 ``elevenlabs_http``，避免挡住 PyPI 上的官方 ``elevenlabs`` SDK
（音效脚本 ``scripts/elevenlabs_audio`` 仍依赖后者）。

自动续期::

    PYTHONPATH=cli:. python -m elevenlabs_http login     # 一次有头登录 → refresh_token.md
    PYTHONPATH=cli:. python -m elevenlabs_http refresh   # 立刻换 Bearer
    PYTHONPATH=cli:. python -m elevenlabs_http watch     # 后台续期

凭据文件（均已 gitignore）::

    cli/elevenlabs_http/cookie.md          浏览器 Cookie（alone 不够调 API）
    cli/elevenlabs_http/bearer.md          Firebase ID Token（约 1h）
    cli/elevenlabs_http/refresh_token.md   Firebase refresh_token（自动换 Bearer）
    cli/elevenlabs_http/hcaptcha_token.md  可选 hCaptcha
    cli/elevenlabs_http/.profile/          Playwright 持久登录态
"""

from .auth import ElevenLabsWebAuth, ensure_fresh_auth, load_web_auth
from .web_client import ElevenLabsUsage, ElevenLabsWebClient, WebClientError

__all__ = [
    "ElevenLabsUsage",
    "ElevenLabsWebAuth",
    "ElevenLabsWebClient",
    "WebClientError",
    "ensure_fresh_auth",
    "load_web_auth",
]
