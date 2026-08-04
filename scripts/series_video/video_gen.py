"""图 → 5s loop 视频：可热插拔的 provider 注册表。

Gemini 不参与这一步。agy（Antigravity Gemini）的 ``fetchAvailableModels`` 里只有
``gemini-3.1-flash-image`` 能出图，没有任何视频模型，所以 Gemini 在本项目只负责
「种子图 / 系列图」，视频一律走外部服务。

默认注册的 provider（GUI 下拉只显示这些；**回退顺序写死**）：

===============  =========================================================
id               说明
===============  =========================================================
``jimeng_web``   即梦画布 Playwright · 720p/5s loop；见 ``cli/jimeng_web/``。
``elevenlabs_http``  ElevenLabs Firebase Bearer HTTP · 480p/5s；见 ``cli/elevenlabs_http/``。
``elevenlabs_web``   ElevenLabs Image & Video 页 Playwright · 480p/5s；见 ``cli/elevenlabs_web/``。
===============  =========================================================

``seedance`` / ``ffmpeg`` 仍保留实现；设 ``SERIES_VIDEO_EXTRA_PROVIDERS=1`` 才会注册。

新增 provider 只需实现 ``VideoProvider`` 协议并调用 ``register()``，GUI 的下拉框
会自动出现新选项，不需要改界面代码。

配置（环境变量优先，其次 ``scripts/config/series_video.json``）::

    ELEVENLABS_VIDEO_API_KEY   elevenlabs_video_api_key   （官方 Key，常被挡）
    ELEVENLABS_VIDEO_MODEL     elevenlabs_video_model     （默认 bytedance-seedance-v2-fast）
    ELEVENLABS_WEB_BEARER / cli/elevenlabs_http/bearer.md （HTTP Firebase ID Token）
    ELEVENLABS_FIREBASE_REFRESH_TOKEN / refresh_token.md （可自动续期）
    JIMENG_HEADLESS / ELWEB_HEADLESS   Playwright 无头开关（默认有头）
    ARK_API_KEY                ark_api_key
    SEEDANCE_MODEL             seedance_model
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "scripts" / "config" / "series_video.json"

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_SEEDANCE_MODEL = "doubao-seedance-2-0-260128"

ELEVEN_BASE_URL = "https://api.elevenlabs.io"
ELEVEN_WEB_HOST = "https://api.us.elevenlabs.io"
DEFAULT_ELEVEN_MODEL = "bytedance-seedance-v2-fast"

#: 本项目的默认档位：便宜优先。480p 的 5s loop 放大到 720p 输出也够用。
DEFAULT_RESOLUTION = "480p"
DEFAULT_DURATION_SEC = 5

LogFn = Callable[[str], None]


# ------------------------------------------------------------------ 配置


def _load_config() -> dict:
    if not CONFIG_PATH.is_file():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _cfg_value(env_key: str, cfg_key: str, default: str = "") -> str:
    env = os.environ.get(env_key, "").strip()
    if env:
        return env
    return str(_load_config().get(cfg_key) or default).strip()


def ark_api_key() -> str:
    return _cfg_value("ARK_API_KEY", "ark_api_key")


def seedance_model() -> str:
    return _cfg_value("SEEDANCE_MODEL", "seedance_model", DEFAULT_SEEDANCE_MODEL)


def elevenlabs_api_key() -> str:
    """图生视频专用的 ElevenLabs key；没配就退回通用的 ``ELEVENLABS_API_KEY``。"""
    key = _cfg_value("ELEVENLABS_VIDEO_API_KEY", "elevenlabs_video_api_key")
    return key or os.environ.get("ELEVENLABS_API_KEY", "").strip()


def elevenlabs_model() -> str:
    return _cfg_value("ELEVENLABS_VIDEO_MODEL", "elevenlabs_video_model", DEFAULT_ELEVEN_MODEL)


# ------------------------------------------------------------ provider 协议


def _part_path(out_path: Path) -> Path:
    return out_path.with_name(out_path.name + ".part")


def _publish(part: Path, out_path: Path) -> None:
    """把写完的 *part* 原子地改名为 *out_path*。

    生成过程中断时磁盘上只会留下 ``.part``，不会出现半截的 .mp4 被
    预览/缩略图读到（否则 ffmpeg 会刷 "partial file" / "Invalid NAL unit size"）。
    """
    if not part.is_file() or part.stat().st_size == 0:
        raise VideoProviderError(f"生成结果为空：{out_path.name}")
    os.replace(part, out_path)


@dataclass
class VideoRequest:
    image_path: Path
    prompt: str
    out_path: Path
    duration_sec: int = DEFAULT_DURATION_SEC
    resolution: str = DEFAULT_RESOLUTION
    aspect_ratio: str = "16:9"
    progress_fn: Callable[[int], None] | None = None


class VideoProvider(Protocol):
    id: str
    label: str

    def available(self) -> tuple[bool, str]:
        """返回 (是否可用, 原因)。不可用时原因会直接显示给用户。"""

    def generate(self, req: VideoRequest, log_fn: LogFn | None = None) -> Path:
        """生成视频并写入 ``req.out_path``，返回该路径。"""


class VideoProviderError(RuntimeError):
    pass


_REGISTRY: dict[str, VideoProvider] = {}


def register(provider: VideoProvider) -> None:
    _REGISTRY[provider.id] = provider


def get_provider(provider_id: str) -> VideoProvider:
    try:
        return _REGISTRY[provider_id]
    except KeyError:
        raise VideoProviderError(f"未注册的视频 provider：{provider_id}") from None


def list_providers() -> list[VideoProvider]:
    return list(_REGISTRY.values())


def default_provider_id() -> str:
    """优先返回第一个当前真正可用的 provider。"""
    for p in providers_fallback_order():
        return p.id
    return next(iter(_REGISTRY), "")


def providers_fallback_order() -> list[VideoProvider]:
    """Jimeng Web → ElevenLabs HTTP → ElevenLabs Web，只返回当前可用的 provider。"""
    order = ("jimeng_web", "elevenlabs_http", "elevenlabs_web")
    out: list[VideoProvider] = []
    for pid in order:
        try:
            p = get_provider(pid)
        except VideoProviderError:
            continue
        try:
            ok, _ = p.available()
        except Exception:  # noqa: BLE001
            continue
        if ok:
            out.append(p)
    return out


# ------------------------------------------------------------ Seedance 2.0


def _data_uri(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime or 'image/png'};base64,{b64}"


class SeedanceProvider:
    """火山方舟 Ark 的 Seedance 2.0 图生视频（异步任务）。"""

    id = "seedance"
    label = "Seedance 2.0（火山方舟）"

    #: 轮询上限，5s 视频通常 1–3 分钟出结果。
    poll_timeout_sec = 900

    def available(self) -> tuple[bool, str]:
        if not ark_api_key():
            return False, (
                "缺少 ARK API Key。请设置环境变量 ARK_API_KEY，"
                f"或在 {CONFIG_PATH.relative_to(REPO_ROOT)} 里写 "
                '{"ark_api_key": "…"}'
            )
        return True, f"model={seedance_model()}"

    def generate(self, req: VideoRequest, log_fn: LogFn | None = None) -> Path:
        log = log_fn or (lambda _m: None)
        ok, reason = self.available()
        if not ok:
            raise VideoProviderError(reason)

        import requests

        key = ark_api_key()
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        payload = {
            "model": seedance_model(),
            "content": [
                {"type": "text", "text": req.prompt},
                {"type": "image_url", "image_url": {"url": _data_uri(req.image_path)}},
            ],
            "resolution": req.resolution,
            "ratio": req.aspect_ratio,
            "duration": req.duration_sec,
            "watermark": False,
        }

        log(f"[Seedance] 提交任务（{req.resolution}/{req.aspect_ratio}/{req.duration_sec}s）…")
        resp = requests.post(
            f"{ARK_BASE_URL}/contents/generations/tasks",
            headers=headers,
            json=payload,
            timeout=60,
        )
        if resp.status_code >= 400:
            raise VideoProviderError(f"提交失败 HTTP {resp.status_code}: {resp.text[:400]}")
        task_id = (resp.json() or {}).get("id")
        if not task_id:
            raise VideoProviderError(f"提交响应里没有 task id：{resp.text[:400]}")
        log(f"[Seedance] task={task_id}，开始轮询 …")

        video_url = self._poll(task_id, headers, log)
        log("[Seedance] 生成完成，下载中 …")
        req.out_path.parent.mkdir(parents=True, exist_ok=True)
        part = _part_path(req.out_path)
        # video_url 24 小时后失效，必须立刻落盘。
        try:
            with requests.get(video_url, stream=True, timeout=300) as r:
                r.raise_for_status()
                with part.open("wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        if chunk:
                            f.write(chunk)
            _publish(part, req.out_path)
        finally:
            part.unlink(missing_ok=True)
        log(f"[Seedance] 已保存：{req.out_path.name}（{req.out_path.stat().st_size} bytes）")
        return req.out_path

    def _poll(self, task_id: str, headers: dict, log: LogFn) -> str:
        import requests

        deadline = time.time() + self.poll_timeout_sec
        wait = 10
        while time.time() < deadline:
            time.sleep(wait)
            r = requests.get(
                f"{ARK_BASE_URL}/contents/generations/tasks/{task_id}",
                headers=headers,
                timeout=60,
            )
            if r.status_code == 429:
                wait = min(wait * 2, 60)
                log("[Seedance] 并发受限，退避重试 …")
                continue
            if r.status_code >= 400:
                raise VideoProviderError(f"轮询失败 HTTP {r.status_code}: {r.text[:400]}")
            data = r.json() or {}
            status = data.get("status")
            if status == "succeeded":
                url = (data.get("content") or {}).get("video_url")
                if not url:
                    raise VideoProviderError(f"任务成功但没有 video_url：{data}")
                return url
            if status in ("failed", "expired", "cancelled"):
                detail = data.get("error") or data
                raise VideoProviderError(f"任务 {status}：{detail}")
            log(f"[Seedance] status={status}，{wait}s 后再查 …")
            wait = min(wait * 2, 60)
        raise VideoProviderError(f"轮询超时（{self.poll_timeout_sec}s），task={task_id}")


# --------------------------------------------------------------- ElevenLabs


class ElevenLabsHttpProvider:
    """ElevenLabs Seedance 2.0 Fast 图生视频（HTTP / Firebase Bearer）。

    鉴权优先级：

    1. **HTTP 网页会话**（``cli/elevenlabs_http/`` 的 Firebase Bearer / refresh_token）
       —— 与浏览器 Image & Video 同通道，payload 用 ``model_parameters`` +
       ``content_asset_id``，host 默认 ``api.us.elevenlabs.io``。
    2. **官方 API Key**（``ELEVENLABS_VIDEO_API_KEY``）—— 许多工作区会 403
       「Programmatic access … not available」，即使 Key 本身无限制。
    """

    id = "elevenlabs_http"
    label = "ElevenLabs · HTTP · Seedance 2.0 Fast（480p/5s）"

    poll_timeout_sec = 900
    _RESOLUTIONS = ("480p", "720p")

    def available(self) -> tuple[bool, str]:
        web_ok, web_msg = self._web_available()
        if web_ok:
            return True, web_msg
        key_ok, key_msg = self._api_key_available()
        if key_ok:
            return True, key_msg
        # 两条都挂时，优先展示网页通道的指引（那是当前能打通的路）。
        return False, f"{web_msg} ｜ API Key：{key_msg}"

    def _web_available(self) -> tuple[bool, str]:
        try:
            from scripts.config.paths import ensure_cli_path

            ensure_cli_path()
            from elevenlabs_http.web_client import ElevenLabsWebClient
        except ImportError:
            return False, "未找到 cli/elevenlabs_http 包（请确认 PYTHONPATH 含 cli/）"
        client = ElevenLabsWebClient(model=elevenlabs_model(), host=ELEVEN_WEB_HOST)
        return client.available()

    def _api_key_headers(self) -> dict[str, str]:
        return {"xi-api-key": elevenlabs_api_key(), "Content-Type": "application/json"}

    def _api_key_available(self) -> tuple[bool, str]:
        if not elevenlabs_api_key():
            return False, "未配置 ELEVENLABS_VIDEO_API_KEY"
        import requests

        model = elevenlabs_model()
        try:
            r = requests.get(
                f"{ELEVEN_BASE_URL}/v1/content-generation/models-available",
                headers=self._api_key_headers(),
                timeout=30,
            )
        except Exception as exc:  # noqa: BLE001
            return False, f"无法连接：{exc}"
        if r.status_code == 401:
            return False, "API Key 无效"
        if r.status_code >= 400:
            return False, f"models-available HTTP {r.status_code}"
        models = {m.get("model_id"): m for m in (r.json() or {}).get("models") or []}
        if model not in models:
            return False, f"账号未开通 {model}"
        # 探 programmatic 门禁
        try:
            probe = requests.post(
                f"{ELEVEN_BASE_URL}/v1/content/generations",
                headers=self._api_key_headers(),
                json={"model_id": model},
                timeout=30,
            )
        except Exception as exc:  # noqa: BLE001
            return False, f"探路失败：{exc}"
        if probe.status_code == 403:
            return False, "工作区未开放 programmatic access（Key 裸奔也没用）"
        return True, f"api-key/{model}"

    def generate(self, req: VideoRequest, log_fn: LogFn | None = None) -> Path:
        log = log_fn or (lambda _m: None)
        resolution = req.resolution if req.resolution in self._RESOLUTIONS else DEFAULT_RESOLUTION
        if resolution != req.resolution:
            log(f"[ElevenLabs] {req.resolution} 不支持，改用 {resolution}")

        web_ok, web_msg = self._web_available()
        if web_ok:
            log(f"[ElevenLabs] 使用网页会话通道 · {web_msg}")
            return self._generate_via_web(req, resolution=resolution, log=log)

        key_ok, key_msg = self._api_key_available()
        if key_ok:
            log(f"[ElevenLabs] 使用 API Key 通道 · {key_msg}")
            return self._generate_via_api_key(req, resolution=resolution, log=log)

        raise VideoProviderError(f"ElevenLabs 不可用：{web_msg} ｜ API Key：{key_msg}")

    def _generate_via_web(
        self, req: VideoRequest, *, resolution: str, log: LogFn
    ) -> Path:
        try:
            from scripts.config.paths import ensure_cli_path

            ensure_cli_path()
            from elevenlabs_http.web_client import ElevenLabsWebClient, WebClientError
        except ImportError as exc:
            raise VideoProviderError(f"无法导入 HTTP 客户端：{exc}") from exc
        client = ElevenLabsWebClient(model=elevenlabs_model(), host=ELEVEN_WEB_HOST)
        try:
            return client.generate_video(
                image_path=req.image_path,
                prompt=req.prompt,
                out_path=req.out_path,
                duration_sec=req.duration_sec,
                resolution=resolution,
                aspect_ratio=req.aspect_ratio,
                generate_audio=False,
                log_fn=log,
            )
        except WebClientError as exc:
            raise VideoProviderError(str(exc)) from exc

    def _generate_via_api_key(
        self, req: VideoRequest, *, resolution: str, log: LogFn
    ) -> Path:
        import requests

        asset_id = self._upload_image_api_key(req.image_path, log)
        # 对齐网页字段，提高 Key 一旦放开后的成功率。
        payload = {
            "prompt": req.prompt,
            "model_id": elevenlabs_model(),
            "generations_count": 1,
            "model_parameters": {
                "aspect_ratio": req.aspect_ratio,
                "duration_secs": max(4, int(req.duration_sec)),
                "resolution": resolution,
                "generate_audio": False,
                "start_frame": {"content_asset_id": asset_id},
            },
        }
        log(
            f"[ElevenLabs] 提交任务（{elevenlabs_model()} / {resolution} / "
            f"{payload['model_parameters']['duration_secs']}s）…"
        )
        r = requests.post(
            f"{ELEVEN_BASE_URL}/v1/content/generations",
            headers=self._api_key_headers(),
            json=payload,
            timeout=60,
        )
        if r.status_code >= 400:
            raise VideoProviderError(f"提交失败 HTTP {r.status_code}: {r.text[:400]}")
        data = r.json() or {}
        gen_id = data.get("id") or data.get("generation_id")
        if not gen_id:
            raise VideoProviderError(f"提交响应里没有 generation id：{str(data)[:300]}")
        log(f"[ElevenLabs] generation={gen_id}，开始轮询 …")
        url = self._poll_api_key(str(gen_id), log)
        return self._download(url, req.out_path, log)

    def _upload_image_api_key(self, image_path: Path, log: LogFn) -> str:
        import requests

        mime = mimetypes.guess_type(image_path.name)[0] or "image/png"
        raw = image_path.read_bytes()
        log(f"[ElevenLabs] 上传首帧 {image_path.name}（{len(raw)} bytes）…")
        r = requests.post(
            f"{ELEVEN_BASE_URL}/v1/assets/internal/upload-sessions",
            headers=self._api_key_headers(),
            json={"file_name": image_path.name, "mime_type": mime, "size_bytes": len(raw)},
            timeout=60,
        )
        if r.status_code >= 400:
            raise VideoProviderError(f"建上传会话失败 HTTP {r.status_code}: {r.text[:300]}")
        session = r.json() or {}
        asset_id = session.get("asset_id") or session.get("content_asset_id") or session.get("id")
        upload_url = session.get("upload_url") or session.get("url")
        if not asset_id or not upload_url:
            raise VideoProviderError(f"上传会话响应缺字段：{str(session)[:300]}")
        put = requests.put(upload_url, data=raw, headers={"Content-Type": mime}, timeout=300)
        if put.status_code >= 400:
            raise VideoProviderError(f"上传字节失败 HTTP {put.status_code}: {put.text[:200]}")
        fin = requests.post(
            f"{ELEVEN_BASE_URL}/v1/assets/internal/{asset_id}/finalize",
            headers=self._api_key_headers(),
            json={},
            timeout=60,
        )
        if fin.status_code >= 400:
            raise VideoProviderError(f"finalize 失败 HTTP {fin.status_code}: {fin.text[:300]}")
        return str(asset_id)

    def _poll_api_key(self, gen_id: str, log: LogFn) -> str:
        import requests

        deadline = time.time() + self.poll_timeout_sec
        wait = 10
        while time.time() < deadline:
            time.sleep(wait)
            r = requests.get(
                f"{ELEVEN_BASE_URL}/v1/content/generations/{gen_id}",
                headers=self._api_key_headers(),
                timeout=60,
            )
            if r.status_code == 429:
                wait = min(wait * 2, 60)
                log("[ElevenLabs] 并发受限，退避重试 …")
                continue
            if r.status_code >= 400:
                raise VideoProviderError(f"轮询失败 HTTP {r.status_code}: {r.text[:300]}")
            data = r.json() or {}
            status = str(data.get("status") or "").lower()
            if status in ("completed", "succeeded", "success"):
                url = _first_output_url(data)
                if not url:
                    raise VideoProviderError(f"任务完成但没有输出地址：{str(data)[:300]}")
                return url
            if status in ("failed", "error", "cancelled", "canceled", "expired"):
                raise VideoProviderError(f"任务 {status}：{data.get('error') or str(data)[:300]}")
            log(f"[ElevenLabs] status={status or '?'}，{wait}s 后再查 …")
            wait = min(wait * 2, 60)
        raise VideoProviderError(f"轮询超时（{self.poll_timeout_sec}s），generation={gen_id}")

    def _download(self, url: str, out_path: Path, log: LogFn) -> Path:
        import requests

        log("[ElevenLabs] 生成完成，下载中 …")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        part = _part_path(out_path)
        try:
            with requests.get(url, stream=True, timeout=300) as r:
                r.raise_for_status()
                with part.open("wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        if chunk:
                            f.write(chunk)
            _publish(part, out_path)
        finally:
            part.unlink(missing_ok=True)
        log(f"[ElevenLabs] 已保存：{out_path.name}（{out_path.stat().st_size} bytes）")
        return out_path


def _first_output_url(data: dict) -> str:
    """从生成结果里挖出视频地址；不同字段名都兜一下。"""
    for key in ("url", "video_url", "download_url"):
        val = data.get(key)
        if isinstance(val, str) and val:
            return val
    outputs = data.get("output") or data.get("outputs") or []
    if isinstance(outputs, dict):
        outputs = [outputs]
    for item in outputs:
        if not isinstance(item, dict):
            continue
        for key in ("url", "video_url", "download_url", "signed_url"):
            val = item.get(key)
            if isinstance(val, str) and val:
                return val
    return ""


# --------------------------------------------------------- 本地 ffmpeg 占位


class FfmpegStillProvider:
    """把静态图压成固定镜头的 5s mp4。

    只做流水线占位：没有真实运动，水不会动。用于在没接入视频 API 时验证
    「系列图 → 视频槽位 → 预览播放」这条链路是通的。
    """

    id = "ffmpeg"
    label = "本地 ffmpeg 静帧占位（无运动）"

    _SIZES = {"480p": (854, 480), "720p": (1280, 720), "1080p": (1920, 1080)}

    def available(self) -> tuple[bool, str]:
        from shutil import which

        if which("ffmpeg") is None:
            return False, "未找到 ffmpeg 可执行文件"
        return True, "仅生成静帧占位视频，不含真实运动"

    def generate(self, req: VideoRequest, log_fn: LogFn | None = None) -> Path:
        log = log_fn or (lambda _m: None)
        ok, reason = self.available()
        if not ok:
            raise VideoProviderError(reason)

        w, h = self._SIZES.get(req.resolution, (1280, 720))
        req.out_path.parent.mkdir(parents=True, exist_ok=True)
        part = _part_path(req.out_path)
        scale = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"
        )
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1", "-i", str(req.image_path),
            "-t", str(req.duration_sec),
            "-r", "24",
            "-vf", scale,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
            "-f", "mp4",
            str(part),
        ]
        log(f"[ffmpeg] 生成静帧占位视频 {w}x{h}/{req.duration_sec}s …")
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                raise VideoProviderError(f"ffmpeg 失败：{(proc.stderr or '').strip()[:400]}")
            _publish(part, req.out_path)
        finally:
            part.unlink(missing_ok=True)
        log(f"[ffmpeg] 已保存：{req.out_path.name}")
        return req.out_path


class JimengWebProvider:
    """即梦画布 Playwright 图生视频（``cli/jimeng_web``）。"""

    id = "jimeng_web"
    label = "Jimeng · 即梦网页（Seedance 2.0 VIP · 720p/5s loop）"

    def available(self) -> tuple[bool, str]:
        try:
            from scripts.config.paths import ensure_cli_path

            ensure_cli_path()
            from jimeng_web.client import JimengWebClient
        except ImportError:
            return False, "未找到 cli/jimeng_web 包（请确认 PYTHONPATH 含 cli/）"
        return JimengWebClient().available()

    def generate(self, req: VideoRequest, log_fn: LogFn | None = None) -> Path:
        log = log_fn or (lambda _m: None)
        try:
            from scripts.config.paths import ensure_cli_path

            ensure_cli_path()
            from jimeng_web.client import JimengWebClient, JimengWebError
        except ImportError as exc:
            raise VideoProviderError(f"未找到 jimeng_web 包：{exc}") from exc

        client = JimengWebClient()
        ok, reason = client.available()
        if not ok:
            raise VideoProviderError(reason)

        req.out_path.parent.mkdir(parents=True, exist_ok=True)
        part = _part_path(req.out_path)
        # 即梦网页实测档：VIP + 首尾帧（同图）+ 16:9 720P + 5s
        duration = int(req.duration_sec or DEFAULT_DURATION_SEC)
        try:
            client.generate_i2v(
                req.image_path,
                req.prompt,
                part,
                duration_sec=duration,
                aspect_ratio=req.aspect_ratio or "16:9",
                log=log,
                progress=req.progress_fn,
            )
            _publish(part, req.out_path)
        except JimengWebError as exc:
            raise VideoProviderError(str(exc)) from exc
        finally:
            part.unlink(missing_ok=True)
        return req.out_path


class ElevenLabsWebProvider:
    """ElevenLabs Image & Video 页 Playwright 图生视频（``cli/elevenlabs_web``）。"""

    id = "elevenlabs_web"
    label = "ElevenLabs · Web · Seedance 2.0 Fast（480p/5s）"

    def available(self) -> tuple[bool, str]:
        try:
            from scripts.config.paths import ensure_cli_path

            ensure_cli_path()
            from elevenlabs_web.client import ElevenLabsWebUiClient
        except ImportError:
            return False, "未找到 cli/elevenlabs_web 包（请确认 PYTHONPATH 含 cli/）"
        return ElevenLabsWebUiClient().available()

    def generate(self, req: VideoRequest, log_fn: LogFn | None = None) -> Path:
        log = log_fn or (lambda _m: None)
        try:
            from scripts.config.paths import ensure_cli_path

            ensure_cli_path()
            from elevenlabs_web.client import ElevenLabsWebUiClient, ElevenLabsWebUiError
        except ImportError as exc:
            raise VideoProviderError(f"未找到 elevenlabs_web 包：{exc}") from exc

        resolution = req.resolution if req.resolution in ("480p", "720p") else DEFAULT_RESOLUTION
        client = ElevenLabsWebUiClient()
        ok, reason = client.available()
        if not ok:
            raise VideoProviderError(reason)

        req.out_path.parent.mkdir(parents=True, exist_ok=True)
        part = _part_path(req.out_path)
        try:
            client.generate_i2v(
                req.image_path,
                req.prompt,
                part,
                duration_sec=req.duration_sec or DEFAULT_DURATION_SEC,
                resolution=resolution,
                log=log,
            )
            _publish(part, req.out_path)
        except ElevenLabsWebUiError as exc:
            raise VideoProviderError(str(exc)) from exc
        finally:
            part.unlink(missing_ok=True)
        return req.out_path


register(JimengWebProvider())
register(ElevenLabsHttpProvider())
register(ElevenLabsWebProvider())

# 调试用：火山 Ark / 本地 ffmpeg 静帧
if os.environ.get("SERIES_VIDEO_EXTRA_PROVIDERS", "").strip() in ("1", "true", "yes"):
    register(SeedanceProvider())
    register(FfmpegStillProvider())
