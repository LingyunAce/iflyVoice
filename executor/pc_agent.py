"""pc_agent 执行器 — HTTP 客户端调 Win PC agent
符合 docs/WIN_PC_AGENT_API.md v0.1 契约
"""
from __future__ import annotations
import time
from typing import Optional
import requests
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type
)
from executor.base import Executor, Intent, IntentType, ExecutorError


_RETRYABLE_HTTP = (500, 502, 503, 504, 429)


class PCAgentError(ExecutorError):
    pass


def _is_retryable_response(resp: requests.Response) -> bool:
    return resp.status_code in _RETRYABLE_HTTP


def _is_business_error(resp: requests.Response) -> bool:
    return 400 <= resp.status_code < 500 and resp.status_code != 429


def _do_http_with_retry(method: str, url: str, *, params=None, json_body=None, timeout: float = 3.0, max_attempts: int = 3) -> dict:
    """带重试的 HTTP 调用。重试：5xx/429/timeout/连接错误，指数退避 1s/2s/4s。"""
    @retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            PCAgentError,
        )),
        reraise=True,
    )
    def _inner():
        try:
            if method == "GET":
                resp = requests.get(url, params=params, timeout=timeout)
            else:
                resp = requests.post(url, json=json_body, timeout=timeout)
        except requests.exceptions.Timeout as e:
            raise PCAgentError(f"timeout: {e}") from e
        except requests.exceptions.ConnectionError as e:
            raise PCAgentError(f"connection: {e}") from e

        if _is_business_error(resp):
            try:
                return resp.json()
            except Exception:
                return {"ok": False, "err": f"PC 返回 {resp.status_code}", "code": "ERR_INTERNAL"}

        if _is_retryable_response(resp):
            raise PCAgentError(f"retryable status {resp.status_code}")

        try:
            return resp.json()
        except Exception as e:
            raise PCAgentError(f"invalid json: {e}") from e

    return _inner()


class PCAgentExecutor(Executor):
    """HTTP 客户端 executor，对接 Win PC agent.exe"""

    def __init__(self, base_url: str, timeout: float = 3.0, max_retries: int = 2):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._consecutive_failures: int = 0
        self._last_failure_time: float = 0.0

    _ROUTES = {
        IntentType.SET_BRIGHTNESS:       ("POST", "/display/brightness",     ["value", "monitor_index"]),
        IntentType.ADJUST_BRIGHTNESS:     ("POST", "/display/brightness",     ["delta", "monitor_index"]),
        IntentType.SET_CONTRAST:         ("POST", "/display/contrast",       ["value", "monitor_index"]),
        IntentType.ADJUST_CONTRAST:      ("POST", "/display/contrast",       ["delta", "monitor_index"]),
        IntentType.SET_COLOR_TEMP:       ("POST", "/display/color_temp",     ["value", "monitor_index"]),
        IntentType.SET_INPUT:            ("POST", "/display/input",          ["code", "monitor_index"]),
        IntentType.LIST_INPUTS:          ("GET",  "/display/inputs",         ["monitor_index"]),
        IntentType.SET_VOLUME:           ("POST", "/volume",                 ["value"]),
        IntentType.ADJUST_VOLUME:        ("POST", "/volume",                 ["delta"]),
        IntentType.LAUNCH_APP:           ("POST", "/apps/launch",            ["name"]),
        IntentType.CLOSE_APP:            ("POST", "/apps/close",             ["name"]),
        IntentType.FOCUS_APP:            ("POST", "/apps/focus",             ["name"]),
        IntentType.LIST_APPS:            ("GET",  "/apps/installed",         []),
        IntentType.BILIBILI_SEARCH:      ("GET",  "/bilibili/search",        ["keyword"]),
    }

    def execute(self, intent: Intent) -> dict:
        route = self._ROUTES.get(intent.type)
        if not route:
            return {"ok": False, "err": f"pc_agent 不支持意图 {intent.type.value}", "code": "ERR_INTERNAL"}

        method, path, param_keys = route
        params = {k: intent.params[k] for k in param_keys if k in intent.params}
        url = f"{self.base_url}{path}"

        try:
            if method == "GET":
                result = _do_http_with_retry("GET", url, params=params,
                                              timeout=self.timeout, max_attempts=self.max_retries + 1)
            else:
                result = _do_http_with_retry("POST", url, json_body=params,
                                              timeout=self.timeout, max_attempts=self.max_retries + 1)
        except PCAgentError as e:
            self._record_failure()
            return {"ok": False, "err": f"PC agent 不可达：{e}", "code": "ERR_INTERNAL"}
        except Exception as e:
            self._record_failure()
            return {"ok": False, "err": f"调用 PC 异常：{e}", "code": "ERR_INTERNAL"}

        if result.get("ok"):
            self._record_success()
        return result

    def health_check(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=self.timeout)
            return resp.status_code == 200 and resp.json().get("ok") is True
        except Exception:
            return False

    def _record_failure(self):
        self._consecutive_failures += 1
        self._last_failure_time = time.time()

    def _record_success(self):
        self._consecutive_failures = 0

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures
