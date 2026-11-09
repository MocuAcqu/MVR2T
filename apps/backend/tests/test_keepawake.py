"""Keep the computer awake while tasks run (app/core/keepawake.py)."""
from __future__ import annotations

import sys
import threading

import pytest

from app.core.keepawake import KeepAwake, _WindowsPowerRequest
from app.services.tasks import TaskManager, UserFacingError


class Recorder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def enable(self) -> None:
        self.calls.append("on")

    def disable(self) -> None:
        self.calls.append("off")


def test_reference_counted_across_overlapping_tasks():
    rec = Recorder()
    ka = KeepAwake(rec)
    ka.acquire()
    ka.acquire()
    ka.release()
    assert rec.calls == ["on"] and ka.active
    ka.release()
    ka.release()  # extra release is harmless
    assert rec.calls == ["on", "off"] and not ka.active


def test_task_manager_holds_the_request_only_while_a_task_runs():
    rec = Recorder()
    tm = TaskManager(keep_awake=KeepAwake(rec))
    started, finish = threading.Event(), threading.Event()

    def work(_task):
        started.set()
        finish.wait(5)
        return "ok"

    t = tm.start("s", "transcribe", work)
    assert started.wait(5)
    assert rec.calls == ["on"]
    finish.set()
    t.thread.join(5)
    assert t.status == "completed" and rec.calls == ["on", "off"]


def test_released_when_the_task_fails():
    rec = Recorder()
    tm = TaskManager(keep_awake=KeepAwake(rec))

    def boom(_task):
        raise UserFacingError("壞了")

    t = tm.start("s", "extract", boom)
    t.thread.join(5)
    assert t.status == "failed" and rec.calls == ["on", "off"]


def test_a_failing_power_api_never_fails_the_task(capsys):
    class Broken:
        def enable(self) -> None:
            raise OSError("denied")

        def disable(self) -> None:
            raise OSError("denied")

    tm = TaskManager(keep_awake=KeepAwake(Broken()))
    t = tm.start("s", "extract", lambda _t: 1)
    t.thread.join(5)
    assert t.status == "completed"
    assert "could not enable" in capsys.readouterr().out


@pytest.mark.skipif(sys.platform != "win32", reason="Windows power request API")
def test_windows_power_request_really_works():
    req = _WindowsPowerRequest()  # raises WinError if the API call fails
    req.enable()
    req.disable()
