"""一次性本機連線憑證驗證（規格 §3.3 / §11）。

Electron 每次啟動後端時產生新的隨機憑證，只交給自己的視窗。
其他本機網頁或程式即使知道連接埠，也無法呼叫 API。
"""
from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

AUTH_HEADER = "authorization"
AUTH_SCHEME = "bearer"


def token_matches(header_value: str | None, expected: str) -> bool:
    """以固定時間比較，避免從回應時間推測憑證。"""
    if not header_value or not expected:
        return False
    scheme, _, value = header_value.partition(" ")
    if scheme.lower() != AUTH_SCHEME:
        return False
    return hmac.compare_digest(value.strip().encode(), expected.encode())


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """所有請求都必須帶 `Authorization: Bearer <token>`。

    CORS preflight（OPTIONS）不會帶自訂標頭，由外層的 CORSMiddleware 先處理，不會進到這裡。
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method == "OPTIONS" or token_matches(request.headers.get(AUTH_HEADER), self._token):
            return await call_next(request)
        return JSONResponse({"detail": "Missing or invalid session token"}, status_code=401)
