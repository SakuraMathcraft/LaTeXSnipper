"""Automation API client used on behalf of the add-in pages.

The Office pages never see the rotating Automation API token: this relay reads
the private discovery file, as the Windows plugin's ``AutomationApiClient``
does, and forwards only the ``next_result`` subscription and owned-job routes.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from latexsnipper_office.paths import automation_connection_file

DESKTOP_UNAVAILABLE = (
    "无法连接到 LaTeXSnipper 识别服务。请在桌面端“设置”中开启“自动化接口”，然后重试。"
)
CONNECTION_INFO_INVALID = (
    "LaTeXSnipper 连接信息无效。请在桌面端关闭并重新开启“自动化接口”，然后重试。"
)
REQUEST_TIMEOUT = "LaTeXSnipper 响应超时，请确认桌面端仍在运行，然后重试。"
INVALID_RESPONSE = "LaTeXSnipper 返回了无法识别的数据，请重启桌面端后再试。"
RECOGNITION_FAILED = "截图识别未能完成，请重试。"

# Same wording as AutomationApiUserMessages.ForErrorCode in the Windows plugin.
ERROR_MESSAGES = {
    "unauthorized": "连接凭据已失效，请在桌面端重新开启“自动化接口”后再试。",
    "forbidden": "当前连接没有执行此操作的权限。",
    "queue_full": "识别任务较多，请稍后再试。",
    "next_result_busy": "已有客户端正在等待下一次识别结果，请稍后再试。",
    "recognition_failed": RECOGNITION_FAILED,
    "model_unavailable": "MathCraft 模型当前不可用，请检查桌面端模型状态。",
    "backend_unavailable": "外部模型尚未配置或当前不可用。",
    "backend_unsupported": "当前外部模型不支持此类识别。",
    "mode_unsupported": "当前识别引擎不支持所选识别模式。",
    "upstream_timeout": "外部模型响应超时，请稍后再试。",
    "upstream_error": "外部模型调用失败，请检查桌面端的外部模型配置。",
    "timeout": "等待识别结果超时，请在桌面端发起识别后重试。",
    "canceled": "截图识别已取消。",
    "empty_formula": "未识别到公式内容，请在桌面端重新识别后再试。",
    "empty_text": "未识别到文本内容，请在桌面端重新识别后再试。",
    "empty_content": "未检测到可识别内容，请在桌面端重新识别后再试。",
    "rate_limited": "请求过于频繁，请稍后再试。",
    "job_not_found": "识别任务已失效，请重新等待下一次识别结果。",
    "job_expired": "识别任务已失效，请重新等待下一次识别结果。",
    "invalid_request": "识别请求无效，请重试。",
    "invalid_backend": "识别请求无效，请重试。",
    "invalid_mode": "识别请求无效，请重试。",
}


class RecognitionRelayError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def user_message(code: str) -> str:
    return ERROR_MESSAGES.get((code or "").strip(), RECOGNITION_FAILED)


Opener = Callable[..., Any]


class AutomationRelay:
    def __init__(
        self,
        connection_file: Path | None = None,
        *,
        opener: Opener | None = None,
        request_timeout: float = 15,
    ) -> None:
        self.connection_file = connection_file or automation_connection_file()
        self._open = opener or urllib.request.urlopen
        self.request_timeout = request_timeout
        self._waiting: str | None = None

    def config(self) -> dict[str, Any]:
        return self._request("GET", "api/v1/config")

    def next_result(self, timeout: int) -> dict[str, Any]:
        """Subscribe to the next desktop result.

        Like the Windows client, a wait this host left behind (a reloaded
        page) is canceled when the desktop reports one, and the request is
        retried once after 300 ms.
        """
        body = {"input": {"type": "next_result"}, "timeout": int(timeout)}
        try:
            created = self._request("POST", "api/v1/recognition/jobs", body)
        except RecognitionRelayError as error:
            if error.code != "next_result_busy" or self._waiting is None:
                raise
            try:
                self.cancel(self._waiting)
            except RecognitionRelayError:
                pass
            time.sleep(0.3)
            created = self._request("POST", "api/v1/recognition/jobs", body)
        job = created.get("job")
        self._waiting = job.get("id") if isinstance(job, dict) else None
        return created

    def job(self, job_id: str) -> dict[str, Any]:
        return self._with_job_messages(
            self._request("GET", f"api/v1/recognition/jobs/{quote(job_id, safe='')}")
        )

    def cancel(self, job_id: str) -> dict[str, Any]:
        return self._request(
            "DELETE", f"api/v1/recognition/jobs/{quote(job_id, safe='')}"
        )

    def _with_job_messages(self, payload: dict[str, Any]) -> dict[str, Any]:
        job = payload.get("job")
        if isinstance(job, dict) and isinstance(job.get("error"), dict):
            job["error"]["message"] = user_message(str(job["error"].get("code", "")))
        return payload

    def _connection(self) -> tuple[str, str]:
        try:
            data = json.loads(self.connection_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise RecognitionRelayError(
                503, "desktop_unavailable", DESKTOP_UNAVAILABLE
            ) from None
        except (OSError, ValueError):
            raise RecognitionRelayError(
                503, "connection_invalid", CONNECTION_INFO_INVALID
            ) from None
        base_url, token = data.get("base_url"), data.get("token")
        if not isinstance(base_url, str) or not isinstance(token, str) or not token:
            raise RecognitionRelayError(
                503, "connection_invalid", CONNECTION_INFO_INVALID
            )
        parts = urlsplit(base_url)
        # The relay only ever talks to the loopback service the desktop announced.
        if parts.scheme not in {"http", "https"} or parts.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise RecognitionRelayError(
                503, "connection_invalid", CONNECTION_INFO_INVALID
            )
        return base_url.rstrip("/") + "/", token

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        base_url, token = self._connection()
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(base_url + path, data=data, method=method)
        request.add_header("Authorization", f"Bearer {token}")
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with self._open(request, timeout=self.request_timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            code = _error_code(error.read())
            raise RecognitionRelayError(error.code, code, user_message(code)) from None
        except TimeoutError:
            raise RecognitionRelayError(
                504, "request_timeout", REQUEST_TIMEOUT
            ) from None
        except (urllib.error.URLError, ConnectionError, OSError):
            raise RecognitionRelayError(
                503, "desktop_unavailable", DESKTOP_UNAVAILABLE
            ) from None
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, ValueError):
            raise RecognitionRelayError(
                502, "invalid_response", INVALID_RESPONSE
            ) from None
        if not isinstance(payload, dict):
            raise RecognitionRelayError(502, "invalid_response", INVALID_RESPONSE)
        return payload


def _error_code(raw: bytes) -> str:
    try:
        payload = json.loads(raw.decode("utf-8"))
        return str(payload["error"]["code"])
    except (UnicodeDecodeError, ValueError, KeyError, TypeError):
        return ""
