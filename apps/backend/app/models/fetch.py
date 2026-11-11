"""下載單一檔案（Phase 09 模型管理）：可續傳、可取消、回報進度。只用標準函式庫。

- 續傳：暫存檔已有部分內容時送 Range；伺服器回 206 就接著寫，回 200 就從頭寫。
- 網路暫時中斷：自動重試（每次都從目前的位置續傳）。
- 使用作業系統的憑證（Windows 憑證存放區）：防毒軟體的 HTTPS 掃描或公司代理伺服器的根憑證也能通過。
- Hugging Face 的大檔會轉址到 CDN；urllib 轉址時保留 Range 標頭。
"""
from __future__ import annotations

import errno
import http.client
import socket
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

CHUNK = 256 * 1024  # 取消的反應時間：最多一個區塊
RETRIES = 4
USER_AGENT = "MVR2T-model-manager"
#: 連線與「多久沒收到資料」的逾時（秒）。卡住時（2026-11-11 Windows：防毒軟體的網路過濾偶爾讓連線停住）
#: 逾時後自動重連、從目前位置續傳；太長會讓使用者乾等，太短在慢速網路上會一直重連。
TIMEOUT = 30.0
#: 重試前的等待：BACKOFF × 2^次數 秒（測試可調小）
BACKOFF = 1.0


class FetchCancelled(Exception):
    pass


class FetchError(Exception):
    """給使用者看的錯誤（繁體中文）。"""


def _friendly(err: BaseException) -> str:
    if isinstance(err, urllib.error.HTTPError):
        if err.code in (401, 403):
            return f"下載伺服器拒絕存取（HTTP {err.code}）。"
        if err.code == 404:
            return "下載伺服器上找不到這個檔案（HTTP 404），可能是版本已下架。"
        return f"下載伺服器回應錯誤（HTTP {err.code}），請稍後再試。"
    reason = getattr(err, "reason", err)
    if isinstance(reason, ssl.SSLError) or isinstance(err, ssl.SSLError):
        return "安全連線（SSL）驗證失敗。如果有防毒軟體的 HTTPS 掃描或公司的代理伺服器，請確認它的憑證已安裝在系統中。"
    if isinstance(reason, (socket.timeout, TimeoutError)) or isinstance(err, (socket.timeout, TimeoutError)):
        return "網路連線逾時，請檢查網路後再試。"
    return "無法連線到下載伺服器，請檢查網路連線後再試。"


def fetch(
    url: str,
    dest: Path,
    size: int,
    on_bytes: Callable[[int], None] = lambda n: None,
    is_cancelled: Callable[[], bool] = lambda: False,
    timeout: float | None = None,
    retries: int = RETRIES,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """把 url 下載到 dest（續傳）。完成時 dest 大小 = size（雜湊由呼叫端驗證）。on_bytes 收到「這次新增的位元組數」。

    重試：連線失敗、逾時、伺服器 5xx、連線提早關閉都會重試並續傳；有下載到新資料的那次不算失敗次數
    （長時間下載中偶爾斷線不會累積到放棄）。連續 retries 次沒有進展才放棄。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    timeout = TIMEOUT if timeout is None else timeout
    attempt = 0
    while True:
        have = dest.stat().st_size if dest.exists() else 0
        if have > size:
            dest.unlink()
            have = 0
        if have == size:
            return
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        if have:
            req.add_header("Range", f"bytes={have}-")
        error: BaseException | None = None
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310 - fixed https URL from the registry
                mode = "ab" if have and res.status == 206 else "wb"
                if mode == "wb" and have:
                    on_bytes(-have)  # 伺服器不支援續傳：從頭開始，進度退回
                    have = 0
                with dest.open(mode) as out:
                    while chunk := res.read(CHUNK):
                        if is_cancelled():
                            raise FetchCancelled()
                        out.write(chunk)
                        on_bytes(len(chunk))
            got = dest.stat().st_size
            if got == size:
                return
            if got > size:
                raise FetchError(f"下載的檔案大小不符（{got} ≠ {size}）。")
            error = ConnectionError("connection closed early")  # 提早結束：續傳
        except FetchCancelled:
            raise
        except urllib.error.HTTPError as e:
            if e.code == 416:  # 範圍不正確：重新下載
                dest.unlink(missing_ok=True)
            elif e.code < 500:
                raise FetchError(_friendly(e)) from None
            error = e
        except (urllib.error.URLError, OSError, ssl.SSLError, http.client.HTTPException) as e:
            if isinstance(e, urllib.error.URLError) and isinstance(e.reason, ssl.SSLError):
                raise FetchError(_friendly(e)) from None
            # 本機檔案的問題（磁碟滿、沒有權限）不是網路問題，不重試
            if isinstance(e, OSError) and not isinstance(e, (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError)):
                if e.errno == errno.ENOSPC:
                    raise FetchError("磁碟空間不足，請清出空間後再下載。") from None
                if isinstance(e, PermissionError):
                    raise FetchError(f"無法寫入 {dest.parent}（沒有權限，或被防毒軟體阻擋）。") from None
            error = e
        progressed = (dest.stat().st_size if dest.exists() else 0) > have
        attempt = 1 if progressed else attempt + 1
        if attempt > retries:
            raise FetchError(_friendly(error)) from None
        for _ in range(max(1, int(BACKOFF * 2**attempt * 10))):  # 等待時仍可取消
            if is_cancelled():
                raise FetchCancelled()
            sleep(0.1)
