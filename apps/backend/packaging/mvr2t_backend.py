"""PyInstaller 進入點（Phase 11）：打包後的 mvr2t-backend(.exe)。

- multiprocessing.freeze_support()：語音辨識在 spawn 的子程序中執行（app/engines/asr/worker.py）；
  打包後子程序會以同一個 exe 啟動，必須先交給 multiprocessing 處理，否則子程序會再啟動一個後端。
- 其餘與開發時的 `python -m app.main` 相同（設定都來自 Electron 傳入的環境變數）。
"""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if "--self-test" in sys.argv[1:]:
        from app.selftest import run_self_test

        raise SystemExit(run_self_test(sys.argv[1:]))
    if "--version" in sys.argv[1:]:
        from app.core.config import APP_VERSION

        print(APP_VERSION)
        raise SystemExit(0)
    from app.main import run

    run()
