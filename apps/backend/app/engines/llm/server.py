"""llama-server（llama.cpp 官方 HTTP 伺服器）的啟動、呼叫與關閉（PROJECT_SPEC §5.3／§5.4）。

為什麼用獨立程序：
- 使用 llama.cpp 官方預先編譯的執行檔，Windows 上不需要 C++ 編譯器；換 GPU 版只要換執行檔（Phase 10）。
- 依序載入（§5.4）：產生摘要時才啟動、做完就結束程序，模型記憶體完全還給系統，不與語音辨識同時常駐。
- 取消：直接終止程序，正在進行的生成立刻停止。

安全：只監聽 127.0.0.1、隨機連接埠、每次啟動產生新的 API key，其他本機程式無法使用。
子程序以 app/core/childproc.spawn_tied 啟動：後端異常結束時也會一起結束，不留下佔記憶體的孤兒程序。
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.childproc import spawn_tied


class LlmError(Exception):
    """給使用者看的錯誤（繁體中文）。"""


class LlmCancelled(Exception):
    pass


@dataclass(frozen=True)
class ServerOptions:
    executable: Path
    model: Path
    ctx_size: int = 8192
    threads: int = 0  # 0 = 交給 llama.cpp 自動決定
    startup_timeout: float = 300.0  # 第一次從磁碟讀 2.5 GB 的模型可能要一兩分鐘
    extra_args: tuple[str, ...] = ()
    #: 放在執行檔前面的指令（測試用：以 Python 執行假的 llama-server）
    launcher: tuple[str, ...] = ()


@dataclass
class ChatResult:
    content: str
    prompt_tokens: int
    completion_tokens: int
    prompt_ms: float
    predicted_ms: float
    cached_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class LlamaServer:
    """一個 llama-server 程序。用 with 區塊確保一定會關閉：

        with LlamaServer(opts) as srv:
            srv.chat(messages, ...)
    """

    def __init__(self, opts: ServerOptions) -> None:
        self.opts = opts
        self.port = 0
        self._key = secrets.token_urlsafe(24)
        self._proc: subprocess.Popen[bytes] | None = None
        self._log: deque[str] = deque(maxlen=60)
        self._killed = threading.Event()
        self.load_seconds = 0.0

    # --- 生命週期 -------------------------------------------------------------
    def start(self) -> None:
        exe = self.opts.executable
        if not exe.is_file():
            raise LlmError(f"找不到 llama-server（{exe}）。請先執行模型下載腳本安裝 llama.cpp。")
        if not self.opts.model.is_file():
            raise LlmError(f"找不到摘要模型檔案（{self.opts.model.name}）。請先下載模型。")
        self.port = _free_port()
        args = [
            *self.opts.launcher,
            str(exe),
            "--model", str(self.opts.model),
            "--host", "127.0.0.1",
            "--port", str(self.port),
            "--api-key", self._key,
            "--ctx-size", str(self.opts.ctx_size),
            "--parallel", "1",  # 只有一個請求，整個 context 給它
            "--no-webui",
            "--jinja",
            # 關閉「思考模式」：摘要不需要，且會大幅增加生成時間（Qwen3 / Qwen3.5 的 chat template 支援）
            "--reasoning-budget", "0",
            "--chat-template-kwargs", '{"enable_thinking": false}',
            # 不另存 prompt 快取到主記憶體（預設最多 8 GB）；同一請求槽內的前段共用（cache_prompt）仍然有效
            "--cache-ram", "0",
            *self.opts.extra_args,
        ]
        if self.opts.threads > 0:
            args += ["--threads", str(self.opts.threads)]
        creationflags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW：不跳出主控台視窗
        started = time.monotonic()
        self._proc = spawn_tied(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(exe.parent),  # Windows：同資料夾的 ggml*.dll
            creationflags=creationflags,
        )
        threading.Thread(target=self._drain, name="llama-server-log", daemon=True).start()
        self._wait_ready(started)
        self.load_seconds = time.monotonic() - started

    def _drain(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        for raw in self._proc.stdout:
            line = raw.decode("utf-8", "replace").rstrip()
            if line:
                self._log.append(line)

    def _wait_ready(self, started: float) -> None:
        while time.monotonic() - started < self.opts.startup_timeout:
            if self._killed.is_set():
                raise LlmCancelled()
            if self._proc is not None and self._proc.poll() is not None:
                raise LlmError(self._startup_failure_message())
            try:
                with urllib.request.urlopen(self._request("/health"), timeout=2) as res:  # noqa: S310 - 127.0.0.1 only
                    if res.status == 200:
                        return
            except urllib.error.HTTPError as e:
                if e.code != 503:  # 503 = 模型還在載入
                    raise LlmError(f"llama-server 回應異常（HTTP {e.code}）。") from e
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
                pass  # 還沒開始監聽
            time.sleep(0.25)
        self.stop()
        raise LlmError("摘要模型載入逾時。請確認電腦有足夠的記憶體（建議可用 6 GB 以上），再試一次。")

    def _startup_failure_message(self) -> str:
        log = "\n".join(self._log)
        low = log.lower()
        if "failed to allocate" in low or "out of memory" in low or "cannot allocate" in low:
            return "記憶體不足，無法載入摘要模型。請關閉其他程式後再試一次。"
        if "unknown model architecture" in low:
            return "目前的 llama.cpp 版本不支援這個模型。請更新 llama.cpp。"
        if "failed to load model" in low or "error loading model" in low:
            return "摘要模型檔案無法讀取，可能已損壞。請重新下載模型。"
        return "摘要模型啟動失敗。" + (f"（{self._log[-1]}）" if self._log else "")

    def kill(self) -> None:
        """取消用：立即終止（可從其他執行緒呼叫）。"""
        self._killed.set()
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.kill()

    def stop(self) -> None:
        proc = self._proc
        if proc is None:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(10)
        if proc.stdout is not None:
            proc.stdout.close()
        self._proc = None

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc is not None else None

    def __enter__(self) -> LlamaServer:
        try:
            self.start()
        except BaseException:
            self.stop()
            raise
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    @property
    def log_tail(self) -> list[str]:
        return list(self._log)

    # --- 呼叫 -----------------------------------------------------------------
    def _request(self, path: str, body: dict[str, Any] | None = None) -> urllib.request.Request:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method="POST" if data else "GET")
        req.add_header("Authorization", f"Bearer {self._key}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        return req

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.3,
        timeout: float = 1800.0,
    ) -> ChatResult:
        body: dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": 0.8,
            "top_k": 20,
            "min_p": 0.0,
            "repeat_penalty": 1.05,
            "cache_prompt": True,  # 同一份逐字稿的多次請求共用前段，不必重算
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if json_schema is not None:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "result", "schema": json_schema}}
        try:
            with urllib.request.urlopen(self._request("/v1/chat/completions", body), timeout=timeout) as res:  # noqa: S310
                payload = json.loads(res.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            if self._killed.is_set():
                raise LlmCancelled() from e
            if self._proc is not None and self._proc.poll() is not None:
                raise LlmError(
                    "摘要模型在處理中結束了，可能是記憶體不足。請關閉其他程式後再試一次。"
                ) from e
            detail = ""
            if isinstance(e, urllib.error.HTTPError):
                try:
                    detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
                except (ValueError, AttributeError, OSError):
                    detail = ""
                if "context" in detail.lower() and ("exceed" in detail.lower() or "too long" in detail.lower()):
                    raise LlmError("這一段內容超過模型一次能處理的長度。") from e
            raise LlmError(f"呼叫摘要模型失敗。{detail}".strip()) from e
        choice = payload["choices"][0]
        usage = payload.get("usage", {})
        timings = payload.get("timings", {})
        return ChatResult(
            content=choice["message"].get("content") or "",
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            prompt_ms=float(timings.get("prompt_ms", 0.0)),
            predicted_ms=float(timings.get("predicted_ms", 0.0)),
            cached_tokens=int(timings.get("cache_n", 0)),
            raw=payload,
        )


def default_threads() -> int:
    """環境變數 MVR2T_LLM_THREADS；未設定時 0（llama.cpp 自動）。"""
    try:
        return max(0, int(os.environ.get("MVR2T_LLM_THREADS", "0")))
    except ValueError:
        return 0
