# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 設定（Phase 11，PROJECT_SPEC §13.1：onedir）。
# 用法：在 apps/backend 執行 `python -m scripts.build_backend`（會呼叫 PyInstaller 並跑 --self-test）。
# 輸出：apps/backend/dist/mvr2t-backend/（mvr2t-backend.exe ＋ _internal/），由 electron-builder 放進 resources/backend/。
#
# 為什麼要列這些：
# - transformers 依模型類型「動態」匯入模組（AutoProcessor → qwen3_asr 的 processor、feature extractor、tokenizer），
#   PyInstaller 靜態分析看不到 → collect_submodules 指定會用到的模型資料夾。
# - OpenCC（簡轉繁）的 C 擴充與 .json／.ocd2 字典、python-docx 的預設範本都是資料檔 → collect_all／collect_data_files。
# - uvicorn 依設定動態載入 loop／protocol 模組。
# - 排除用不到的大型套件（tkinter、測試、開發工具），縮小安裝檔。
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata

HERE = SPECPATH  # noqa: F821 - PyInstaller 提供：這個 .spec 所在的資料夾（apps/backend/packaging）
BACKEND = os.path.dirname(HERE)

datas, binaries, hiddenimports = [], [], []

for pkg in ("opencc",):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

datas += collect_data_files("docx")  # templates/default.docx 等
datas += collect_data_files("transformers", includes=["**/*.json", "**/*.jinja"])
# transformers 會在匯入時檢查相依套件的版本（importlib.metadata）
for dist in ("transformers", "tokenizers", "safetensors", "huggingface_hub", "numpy", "torch", "tqdm", "regex",
             "requests", "filelock", "packaging", "pyyaml", "fastapi", "starlette", "pydantic", "uvicorn", "python-docx", "lxml"):
    try:
        datas += copy_metadata(dist)
    except Exception:  # noqa: BLE001 - 沒有安裝的套件略過
        pass

hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("app")
for model in ("qwen3_asr", "qwen2", "qwen3", "whisper"):
    hiddenimports += collect_submodules(f"transformers.models.{model}")

a = Analysis(
    [os.path.join(HERE, "mvr2t_backend.py")],
    pathex=[BACKEND],  # apps/backend：讓 `import app` 找得到
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib", "IPython", "jupyter", "notebook", "pytest", "PIL.ImageTk",
        "torch.utils.tensorboard", "tensorboard", "torchvision", "torchaudio",
        "llama_cpp",  # 沙盒比較模型時用過的 llama-cpp-python；正式版使用獨立的 llama-server
        "triton",  # PyTorch 的 GPU 編譯器（Linux CUDA 版才有；CPU 推論用不到，約 900 MB）
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="mvr2t-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX 壓縮常被防毒軟體誤判，也會拖慢啟動
    console=True,  # 由 Electron 以 CREATE_NO_WINDOW 啟動，不會出現視窗；需要 stdin／stdout 管線
    icon=os.path.join(BACKEND, "..", "desktop", "build", "icon.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="mvr2t-backend",
)
