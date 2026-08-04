"""ElevenLabs 网页态图生视频客户端（Firebase Bearer + 网页 payload）。"""

from __future__ import annotations

import mimetypes
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .auth import (
    ElevenLabsWebAuth,
    auth_status_message,
    ensure_fresh_auth,
    load_web_auth,
)

DEFAULT_HOST = "https://api.us.elevenlabs.io"
FALLBACK_HOST = "https://api.elevenlabs.io"
DEFAULT_MODEL = "bytedance-seedance-v2-fast"

LogFn = Callable[[str], None]


class WebClientError(RuntimeError):
    pass


@dataclass
class ElevenLabsUsage:
    """来自 ``GET /v1/user/internal``。"""

    character_count: int = 0  # 已用
    character_limit: int = 0  # 总额
    email: str = ""
    tier: str = ""

    @property
    def remaining(self) -> int:
        return max(0, self.character_limit - self.character_count)

    @property
    def ok(self) -> bool:
        return self.character_limit > 0


class ElevenLabsWebClient:
    def __init__(
        self,
        auth: ElevenLabsWebAuth | None = None,
        *,
        host: str = DEFAULT_HOST,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self.auth = auth or load_web_auth()
        self.host = host.rstrip("/")
        self.model = model
        self.poll_timeout_sec = 900

    def ensure_auth(self, *, force_refresh: bool = False) -> ElevenLabsWebAuth:
        # 每次请求前保证 Bearer 至少还有几分钟；有 refresh_token 则全自动续。
        try:
            self.auth = ensure_fresh_auth(
                min_ttl_sec=180,
                force_refresh=force_refresh,
            )
        except Exception as exc:  # noqa: BLE001
            if force_refresh or not self.auth.ok:
                self.auth = load_web_auth(force_refresh=force_refresh)
            if not self.auth.ok:
                raise WebClientError(f"{auth_status_message(self.auth)}（续期失败：{exc}）") from exc
        if not self.auth.ok:
            raise WebClientError(auth_status_message(self.auth))
        return self.auth

    def _headers(self) -> dict[str, str]:
        self.ensure_auth()
        return {
            "Authorization": self.auth.authorization_header(),
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Origin": "https://elevenlabs.io",
            "Referer": "https://elevenlabs.io/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/150.0.0.0 Safari/537.36"
            ),
            "x-generation-actor": "User",
            "x-generation-surface": "Image Video",
        }

    def fetch_usage(self) -> ElevenLabsUsage:
        """拉取账号字符额度（总额 / 已用）。"""
        import requests

        self.ensure_auth()
        r = requests.get(
            f"{self.host}/v1/user/internal",
            headers=self._headers(),
            timeout=30,
        )
        if r.status_code == 401 and self.auth.refresh_token:
            self.ensure_auth(force_refresh=True)
            r = requests.get(
                f"{self.host}/v1/user/internal",
                headers=self._headers(),
                timeout=30,
            )
        if r.status_code >= 400:
            raise WebClientError(f"user/internal HTTP {r.status_code}: {r.text[:200]}")
        data = r.json() or {}
        sub = data.get("subscription") or {}
        if not isinstance(sub, dict):
            sub = {}
        try:
            used = int(sub.get("character_count") or data.get("character_count") or 0)
        except (TypeError, ValueError):
            used = 0
        try:
            limit = int(sub.get("character_limit") or 0)
        except (TypeError, ValueError):
            limit = 0
        return ElevenLabsUsage(
            character_count=used,
            character_limit=limit,
            email=str(data.get("email") or self.auth.email or ""),
            tier=str(sub.get("tier") or ""),
        )

    def available(self) -> tuple[bool, str]:
        try:
            self.ensure_auth()
        except WebClientError as exc:
            return False, str(exc)
        import requests

        try:
            r = requests.get(
                f"{self.host}/v1/content-generation/models-available",
                headers=self._headers(),
                timeout=30,
            )
        except Exception as exc:  # noqa: BLE001
            return False, f"无法连接 {self.host}：{exc}"
        if r.status_code == 401 and self.auth.refresh_token:
            try:
                self.ensure_auth(force_refresh=True)
                r = requests.get(
                    f"{self.host}/v1/content-generation/models-available",
                    headers=self._headers(),
                    timeout=30,
                )
            except Exception as exc:  # noqa: BLE001
                return False, f"Bearer 刷新后仍失败：{exc}"
        if r.status_code == 401:
            return (
                False,
                "Bearer 无效或已过期；请 `python -m elevenlabs_http login` "
                "或更新 refresh_token.md",
            )
        if r.status_code >= 400:
            # us host 偶发区域问题，提示可切主站
            return False, f"models-available HTTP {r.status_code}: {r.text[:200]}"
        models = {m.get("model_id"): m for m in (r.json() or {}).get("models") or []}
        info = models.get(self.model)
        if info is None:
            known = ", ".join(sorted(models)[:8]) or "(空)"
            return False, f"账号没有模型 {self.model}；可见：{known}"
        who = self.auth.email or "session"
        return True, f"web/{who} · {self.model}"

    def upload_image(self, image_path: Path, log: LogFn | None = None) -> str:
        """上传首帧，返回 content_asset_id。"""
        import requests

        log = log or (lambda _m: None)
        self.ensure_auth()
        mime = mimetypes.guess_type(image_path.name)[0] or "image/png"
        raw = image_path.read_bytes()
        log(f"[ElevenLabs/web] 上传首帧 {image_path.name}（{len(raw)} bytes）…")

        r = requests.post(
            f"{self.host}/v1/assets/internal/upload-sessions",
            headers=self._headers(),
            json={
                "file_name": image_path.name,
                "mime_type": mime,
                "size_bytes": len(raw),
            },
            timeout=60,
        )
        if r.status_code >= 400:
            raise WebClientError(f"建上传会话失败 HTTP {r.status_code}: {r.text[:300]}")
        session = r.json() or {}
        asset_id = (
            session.get("asset_id")
            or session.get("content_asset_id")
            or session.get("id")
        )
        upload_url = session.get("upload_url") or session.get("url")
        if not asset_id or not upload_url:
            raise WebClientError(f"上传会话响应缺字段：{str(session)[:300]}")

        put = requests.put(
            upload_url, data=raw, headers={"Content-Type": mime}, timeout=300
        )
        if put.status_code >= 400:
            raise WebClientError(f"上传字节失败 HTTP {put.status_code}: {put.text[:200]}")

        fin = requests.post(
            f"{self.host}/v1/assets/internal/{asset_id}/finalize",
            headers=self._headers(),
            json={},
            timeout=60,
        )
        if fin.status_code >= 400:
            raise WebClientError(f"finalize 失败 HTTP {fin.status_code}: {fin.text[:300]}")
        fin_data = fin.json() if fin.content else {}
        # 网页 payload 用 content_asset_id；finalize 可能回写同名字段。
        content_id = (
            (fin_data or {}).get("content_asset_id")
            or (fin_data or {}).get("asset_id")
            or asset_id
        )
        return str(content_id)

    def generate_video(
        self,
        *,
        image_path: Path,
        prompt: str,
        out_path: Path,
        duration_sec: int = 5,
        resolution: str = "480p",
        aspect_ratio: str = "16:9",
        generate_audio: bool = False,
        log_fn: LogFn | None = None,
    ) -> Path:
        import requests

        log = log_fn or (lambda _m: None)
        self.ensure_auth()
        asset_id = self.upload_image(image_path, log)

        payload: dict = {
            "prompt": prompt,
            "display_prompt": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": prompt}],
                    }
                ],
            },
            "model_id": self.model,
            "generations_count": 1,
            "model_parameters": {
                "aspect_ratio": aspect_ratio,
                "duration_secs": max(4, int(duration_sec)),
                "resolution": resolution,
                "generate_audio": bool(generate_audio),
                "start_frame": {"content_asset_id": asset_id},
            },
        }
        if self.auth.hcaptcha_token:
            payload["hcaptcha_token"] = self.auth.hcaptcha_token

        log(
            f"[ElevenLabs/web] 提交（{self.model} / {resolution} / "
            f"{payload['model_parameters']['duration_secs']}s / {aspect_ratio}）…"
        )
        r = requests.post(
            f"{self.host}/v1/content/generations",
            headers=self._headers(),
            json=payload,
            timeout=60,
        )
        if r.status_code == 401 and self.auth.refresh_token:
            self.ensure_auth(force_refresh=True)
            r = requests.post(
                f"{self.host}/v1/content/generations",
                headers=self._headers(),
                json=payload,
                timeout=60,
            )
        if r.status_code >= 400:
            detail = r.text[:400]
            if "captcha" in detail.lower() or "hcaptcha" in detail.lower():
                raise WebClientError(
                    f"提交失败（需要 hCaptcha）：把网页 Network 里同名字段贴到 "
                    f"cli/elevenlabs_http/hcaptcha_token.md。原始响应：{detail}"
                )
            raise WebClientError(f"提交失败 HTTP {r.status_code}: {detail}")

        data = r.json() or {}
        gen_id = data.get("id") or data.get("generation_id")
        if not gen_id:
            # 有时直接返回 generations 列表
            gens = data.get("generations") or []
            if gens and isinstance(gens[0], dict):
                gen_id = gens[0].get("id") or gens[0].get("generation_id")
        if not gen_id:
            raise WebClientError(f"提交响应里没有 generation id：{str(data)[:300]}")
        log(f"[ElevenLabs/web] generation={gen_id}，轮询中 …")
        url = self._poll(str(gen_id), log)
        return self._download(url, out_path, log)

    def _poll(self, gen_id: str, log: LogFn) -> str:
        import requests

        deadline = time.time() + self.poll_timeout_sec
        wait = 8
        while time.time() < deadline:
            time.sleep(wait)
            r = requests.get(
                f"{self.host}/v1/content/generations/{gen_id}",
                headers=self._headers(),
                timeout=60,
            )
            if r.status_code == 429:
                wait = min(wait * 2, 60)
                log("[ElevenLabs/web] 并发受限，退避 …")
                continue
            if r.status_code >= 400:
                raise WebClientError(f"轮询失败 HTTP {r.status_code}: {r.text[:300]}")
            data = r.json() or {}
            status = str(data.get("status") or "").lower()
            if status in ("completed", "succeeded", "success"):
                url = _first_output_url(data)
                if not url:
                    raise WebClientError(f"完成但无输出地址：{str(data)[:300]}")
                return url
            if status in ("failed", "error", "cancelled", "canceled", "expired"):
                raise WebClientError(
                    f"任务 {status}：{data.get('error') or str(data)[:300]}"
                )
            log(f"[ElevenLabs/web] status={status or '?'}，{wait}s 后再查 …")
            wait = min(wait * 2, 45)
        raise WebClientError(f"轮询超时（{self.poll_timeout_sec}s），generation={gen_id}")

    def _download(self, url: str, out_path: Path, log: LogFn) -> Path:
        import os
        import requests

        log("[ElevenLabs/web] 下载中 …")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        part = out_path.with_name(out_path.name + ".part")
        try:
            with requests.get(url, stream=True, timeout=300) as r:
                r.raise_for_status()
                with part.open("wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        if chunk:
                            f.write(chunk)
            if not part.is_file() or part.stat().st_size == 0:
                raise WebClientError(f"下载结果为空：{out_path.name}")
            os.replace(part, out_path)
        finally:
            part.unlink(missing_ok=True)
        log(f"[ElevenLabs/web] 已保存：{out_path.name}（{out_path.stat().st_size} bytes）")
        return out_path


def _first_output_url(data: dict) -> str:
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
