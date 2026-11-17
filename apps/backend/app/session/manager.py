"""單次 Session 與暫存資料夾（PROJECT_SPEC §8）。

Phase 04 只實作媒體處理需要的部分；完整的 Session 生命週期（匯出、重新整理清除…）在 Phase 08。

- 這是單一視窗的桌面程式：建立新 Session 時，舊 Session 一律結束並刪除暫存。
  所以使用者重新整理畫面（Renderer 狀態消失 → 建立新 Session）時，上一次的暫存檔也會被清掉（規格 §8.3）。
- 後端啟動時清除上次異常結束留下的暫存（規格 §8.4）；正常結束時也會清除。
- 刪除前一定確認路徑位於 sessions_root 之內，避免誤刪其他資料夾。
"""
from __future__ import annotations

import shutil
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.tasks import TaskManager


@dataclass
class MediaRecord:
    id: str
    display_name: str  # 使用者的檔名，只用於顯示，不用於任何路徑
    ext: str
    kind: str  # video / audio
    size: int
    path: Path  # <session>/media/<id>/original.<ext>
    info: dict[str, Any]  # 回傳給前端的 MediaInfo
    audio: dict[str, Any] | None = None  # 抽取完成後的結果（給 Phase 05 使用）
    transcript: dict[str, Any] | None = None  # 語音辨識結果（Phase 05；只存在本次 Session）
    summary: dict[str, Any] | None = None  # 摘要結果（Phase 06；只存在本次 Session）

    @property
    def dir(self) -> Path:
        return self.path.parent


@dataclass
class Session:
    id: str
    dir: Path
    media: MediaRecord | None = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


def _is_within(child: Path, root: Path) -> bool:
    try:
        child.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def safe_rmtree(path: Path, root: Path) -> None:
    """只刪除 root 底下的資料夾；不存在或不在範圍內就略過。"""
    if path.exists() and _is_within(path, root) and path.resolve() != root.resolve():
        shutil.rmtree(path, ignore_errors=True)


class SessionManager:
    def __init__(self, root: Path, tasks: TaskManager) -> None:
        self.root = root
        self.tasks = tasks
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def cleanup_stale(self) -> int:
        """刪除 sessions_root 下所有殘留資料夾（後端啟動時呼叫）。回傳刪除數量。"""
        if not self.root.exists():
            return 0
        count = 0
        for child in self.root.iterdir():
            if child.is_dir():
                safe_rmtree(child, self.root)
                count += 1
        return count

    def create(self) -> Session:
        self.end_all()
        sid = uuid.uuid4().hex
        d = self.root / sid
        d.mkdir(parents=True, exist_ok=False)
        s = Session(id=sid, dir=d)
        with self._lock:
            self._sessions[sid] = s
        return s

    def active_dirs(self) -> list[Path]:
        with self._lock:
            return [s.dir for s in self._sessions.values()]

    def inactive_dirs(self) -> list[Path]:
        """sessions_root 下不屬於任何進行中工作階段的資料夾（設定頁的「清除暫存」）。"""
        if not self.root.exists():
            return []
        active = {d.resolve() for d in self.active_dirs()}
        return [c for c in self.root.iterdir() if c.is_dir() and c.resolve() not in active]

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.get(session_id)

    def end(self, session_id: str) -> bool:
        with self._lock:
            s = self._sessions.pop(session_id, None)
        if s is None:
            return False
        self.tasks.cancel_session(session_id)  # 先停止 FFmpeg，再刪檔
        safe_rmtree(s.dir, self.root)
        return True

    def end_all(self) -> None:
        with self._lock:
            ids = list(self._sessions)
        for sid in ids:
            self.end(sid)

    def clear_media(self, session: Session) -> None:
        """換檔案時：取消這個 Session 的工作並刪除舊媒體。"""
        self.tasks.cancel_session(session.id)
        if session.media is not None:
            safe_rmtree(session.media.dir, self.root)
            session.media = None
