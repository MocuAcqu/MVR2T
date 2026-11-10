"""假的 llama-server（測試 app/engines/llm/server.py 用，不需要模型）。

行為由環境變數控制：
    FAKE_LLAMA_MODE=ok          正常：/health 先回 503 一小段時間再回 200；chat 回傳 FAKE_LLAMA_REPLY（JSON 字串）
    FAKE_LLAMA_MODE=oom         啟動後印出記憶體不足訊息並結束
    FAKE_LLAMA_MODE=slow        chat 會卡住很久（測試取消）
"""
from __future__ import annotations

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

args = sys.argv[1:]
port = int(args[args.index("--port") + 1])
key = args[args.index("--api-key") + 1]
mode = os.environ.get("FAKE_LLAMA_MODE", "ok")
reply = os.environ.get("FAKE_LLAMA_REPLY", '{"overview": "測試摘要"}')
ready_at = time.monotonic() + 0.4

if mode == "oom":
    print("llama_model_load: error loading model: failed to allocate buffer", flush=True)
    sys.exit(1)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a: object) -> None:
        pass

    def _auth(self) -> bool:
        if self.headers.get("Authorization") != f"Bearer {key}":
            self.send_response(401)
            self.end_headers()
            return False
        return True

    def do_GET(self) -> None:
        if not self._auth():
            return
        self.send_response(200 if time.monotonic() >= ready_at else 503)
        self.end_headers()

    def do_POST(self) -> None:
        if not self._auth():
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body["response_format"]["type"] == "json_schema"
        if mode == "slow":
            time.sleep(60)
        out = json.dumps({
            "choices": [{"message": {"content": reply}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "timings": {"prompt_ms": 1.0, "predicted_ms": 1.0, "cache_n": 0},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


print(f"main: server is listening on http://127.0.0.1:{port}", flush=True)
ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
