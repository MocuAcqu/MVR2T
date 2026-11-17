"""英文介面（使用者決定 2026-11-17：多語介面 繁中／英文）：把後端回給畫面的訊息翻成英文。

後端的訊息都以繁體中文撰寫（f-string）。這裡用「訊息樣板」（{} 代表插入的值）對照英文，在回應前翻譯：
- 只翻譯給畫面看的欄位：錯誤的 detail、工作進度（stage／detail／message／warnings）、模型管理、硬體資訊、YouTube 元件、設定。
  不會碰逐字稿、摘要等使用者內容（main.py 的 LanguageMiddleware 只處理特定路徑與錯誤回應）。
- 整句對不到時，依「。」「；」切開逐句翻譯；插入的值本身是中文時（例如套件名稱）也會翻譯。
- 對不到的句子維持中文（新增訊息時請一併加入 EN，tests/test_i18n.py 會檢查）。
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

CJK = re.compile(r"[一-鿿]")

#: 中文樣板 → 英文（{0}、{1}… 依序對應樣板中的 {}）
EN: dict[str, str] = {
    # --- 進度與狀態 ---
    "  下載 {}…": "  Downloading {0}…",
    "  下載 {}（{} MB）…": "  Downloading {0} ({1} MB)…",
    "  驗證 {}…": "  Verifying {0}…",
    "0 / {} 段": "0 / {0} segments",
    "{} / {} 段": "{0} / {1} segments",
    "{} / {} 秒": "{0} / {1} s",
    "{} 句": "{0} sentences",
    "{} 段": "{0} segments",
    "第 {} / {} 段": "Segment {0} / {1}",
    "第 {}–{} / {} 段": "Segments {0}–{1} / {2}",
    "第 {} 層，第 {} / {} 組": "Level {0}, group {1} / {2}",
    "下載中": "Downloading",
    "安裝中": "Installing",
    "完成": "Done",
    "等待中": "Waiting",
    "等待其他 AI 工作完成": "Waiting for the other AI task to finish",
    "驗證檔案": "Verifying files",
    "已取消": "Cancelled",
    "已取消。": "Cancelled.",
    "已取消。已下載的部分會保留，下次可以繼續。": "Cancelled. The downloaded part is kept and the download can resume next time.",
    "下載完成並通過驗證。": "Downloaded and verified.",
    "所有檔案都完整。": "All files are intact.",
    "有檔案損壞或遺失，請按「修復」重新下載。": "Some files are damaged or missing. Click “Repair” to download them again.",
    "正在抽取音訊": "Extracting audio",
    "正在切段": "Splitting into segments",
    "正在載入語音辨識模型": "Loading the speech recognition model",
    "正在載入時間戳記對齊模型": "Loading the timestamp alignment model",
    "正在辨識語音": "Recognizing speech",
    "正在對齊時間戳記": "Aligning timestamps",
    "正在整理逐字稿": "Building the transcript",
    "正在載入摘要模型": "Loading the summary model",
    "正在閱讀逐字稿": "Reading the transcript",
    "正在整合重點": "Combining key points",
    "正在產生摘要": "Generating the summary",
    "正在產生心智圖": "Generating the mind map",
    "內容只涵蓋前段，重新整理一次": "Only the beginning was covered; reorganizing",
    "正在連線到 YouTube": "Connecting to YouTube",
    "正在下載音訊": "Downloading audio",
    "正在下載字幕": "Downloading subtitles",
    "正在檢查檔案": "Checking the file",
    "全文摘要": "Overview",
    "重點整理": "Key points",
    "條列式筆記": "Bullet notes",
    "主題分類": "Topics",
    "關鍵字": "Keywords",
    "行動事項": "Action items",
    "問題與結論": "Questions and conclusions",
    "心智圖": "Mind map",
    # --- 模型管理 ---
    "語音辨識": "Speech recognition",
    "時間戳記對齊": "Timestamp alignment",
    "摘要與心智圖": "Summary and mind map",
    "摘要 GPU 加速（NVIDIA）": "Summary GPU acceleration (NVIDIA)",
    "把影片或錄音轉成逐字稿，並對齊每一句的時間（Qwen3-ASR ＋ 時間戳記對齊模型）。":
        "Turns videos and recordings into a transcript and aligns the time of every sentence (Qwen3-ASR + timestamp alignment model).",
    "整理逐字稿，產生摘要、重點、行動事項與心智圖（Qwen3.5-4B，使用 llama.cpp 執行）。":
        "Organizes the transcript into a summary, key points, action items and a mind map (Qwen3.5-4B, run with llama.cpp).",
    "用 NVIDIA 顯示卡執行摘要與心智圖，通常比 CPU 快很多。需要先安裝「摘要與心智圖」；GPU 無法使用時會自動改用 CPU。":
        "Runs the summary and mind map on an NVIDIA graphics card, usually much faster than the CPU. Requires “Summary and mind map”; falls back to the CPU automatically when the GPU cannot be used.",
    "建議記憶體 8 GB 以上；只用 CPU 即可，24 分鐘的錄音約需 30 分鐘。":
        "8 GB of RAM or more recommended; CPU only is fine. A 24-minute recording takes about 30 minutes.",
    "建議記憶體 8 GB 以上（執行時約使用 3.5 GB）；只用 CPU 即可。": "8 GB of RAM or more recommended (uses about 3.5 GB while running); CPU only is fine.",
    "需要 NVIDIA 顯示卡（建議顯示記憶體 4 GB 以上）與較新的驅動程式。": "Requires an NVIDIA graphics card (4 GB of video memory or more recommended) and a recent driver.",
    "llama.cpp（CUDA 版）": "llama.cpp (CUDA build)",
    "llama.cpp 執行檔遺失": "The llama.cpp program is missing",
    "{}：缺少安裝紀錄": "{0}: installation record missing",
    "{}尚未安裝，無法驗證。": "{0} is not installed, so it cannot be verified.",
    "{}已在處理中。": "{0} is already being processed.",
    "{}已安裝。": "{0} is already installed.",
    "{}正在下載或驗證，請先取消。": "{0} is being downloaded or verified. Cancel it first.",
    "沒有這個模型。": "No such model.",
    "沒有這個動作。": "No such action.",
    "沒有進行中的工作。": "Nothing is in progress.",
    "找不到這個項目。": "Item not found.",
    "路徑不在模型資料夾內。": "The path is not inside the models folder.",
    "檔案正在使用中（或被防毒軟體鎖定），請稍後再試。": "The file is in use (or locked by antivirus software). Try again later.",
    "語音辨識或摘要正在使用模型，請等它完成後再刪除。": "Speech recognition or the summary is using the model. Wait until it finishes, then delete.",
    "這個作業系統目前沒有可用的 llama.cpp 執行檔。": "There is no llama.cpp program for this operating system yet.",
    "發生未預期的錯誤：{}": "Unexpected error: {0}",
    "{} 大小不符（{} ≠ {}）": "{0} has the wrong size ({1} ≠ {2})",
    "{} 雜湊不符，檔案可能損壞": "{0} has the wrong hash; the file may be damaged",
    "缺少檔案 {}": "Missing file {0}",
    "{}：{}。請重新下載。": "{0}: {1}. Please download it again.",
    "{} 目前不提供下載。": "{0} cannot be downloaded at the moment.",
    "磁碟空間不足：{} 還需要約 {} GB（目前剩 {} GB）。": "Not enough disk space: {0} needs about {1} GB more ({2} GB free).",
    "{} 驗證失敗（大小或 SHA-256 不符），請重新執行下載。": "{0} failed verification (size or SHA-256 mismatch). Please download again.",
    "llama.cpp 安裝後找不到執行檔。": "The llama.cpp program was not found after installation.",
    "{} 中找不到 {}。": "{1} was not found in {0}.",
    "{} 內含不安全的路徑：{}": "{0} contains an unsafe path: {1}",
    "{} 內含不安全的連結：{} -> {}": "{0} contains an unsafe link: {1} -> {2}",
    "{} 內含不支援的檔案類型：{}": "{0} contains an unsupported file type: {1}",
    "不支援的壓縮格式：{}": "Unsupported archive format: {0}",
    "環境變數指定的 llama-server 不存在：{}": "The llama-server set by the environment variable does not exist: {0}",
    "這個平台（{}）尚未設定 llama.cpp 執行檔版本。請先執行 python -m scripts.resolve_llama_release 並把結果填入 app/models/runtime.py。":
        "No llama.cpp version is configured for this platform ({0}).",
    # --- 下載 ---
    "下載伺服器上找不到這個檔案（HTTP 404），可能是版本已下架。": "The file was not found on the download server (HTTP 404); the version may have been removed.",
    "下載伺服器回應錯誤（HTTP {}），請稍後再試。": "The download server returned an error (HTTP {0}). Try again later.",
    "下載伺服器拒絕存取（HTTP {}）。": "The download server refused access (HTTP {0}).",
    "下載的檔案大小不符（{} ≠ {}）。": "The downloaded file has the wrong size ({0} ≠ {1}).",
    "安全連線（SSL）驗證失敗。如果有防毒軟體的 HTTPS 掃描或公司的代理伺服器，請確認它的憑證已安裝在系統中。":
        "Secure connection (SSL) verification failed. If antivirus HTTPS scanning or a company proxy is in use, make sure its certificate is installed in the system.",
    "網路連線逾時，請檢查網路後再試。": "The network connection timed out. Check your network and try again.",
    "無法連線到下載伺服器，請檢查網路連線後再試。": "Cannot reach the download server. Check your network connection and try again.",
    "磁碟空間不足，請清出空間後再下載。": "Not enough disk space. Free up some space and download again.",
    "無法寫入 {}（沒有權限，或被防毒軟體阻擋）。": "Cannot write {0} (no permission, or blocked by antivirus software).",
    # --- 硬體與運算裝置 ---
    "Apple Silicon GPU（Metal，統一記憶體）": "Apple Silicon GPU (Metal, unified memory)",
    "Apple Silicon（統一記憶體）": "Apple Silicon (unified memory)",
    "CPU（目前版本尚不支援 Intel／AMD 顯示卡加速）": "CPU (Intel/AMD graphics acceleration is not supported in this version)",
    "CPU（設定為一律使用 CPU）": "CPU (set to always use the CPU)",
    "CPU（語音辨識的 GPU 加速將在之後的版本評估）": "CPU (GPU acceleration for speech recognition may come in a later version)",
    "CPU（{}）": "CPU ({0})",
    "GPU 無法載入模型（可能是顯示記憶體不足），已改用 CPU。": "The GPU could not load the model (possibly not enough video memory); switched to the CPU.",
    "GPU 版 llama.cpp（CUDA {}.{}）需要 NVIDIA 驅動程式 {}.{} 以上。": "The GPU build of llama.cpp (CUDA {0}.{1}) requires NVIDIA driver {2}.{3} or later.",
    "Intel Mac 第一版使用 CPU（規格 §6.3）。": "Intel Macs use the CPU in this version.",
    "Metal 只在 macOS 上使用。": "Metal is only used on macOS.",
    "NVIDIA GPU 可用的 VRAM 太少（{} GB），改用 CPU。": "Too little free VRAM on the NVIDIA GPU ({0} GB); using the CPU.",
    "NVIDIA GPU（VRAM 可用 {} GB，放 {}／{} 層到 GPU，其餘用 CPU）": "NVIDIA GPU ({0} GB VRAM free; {1}/{2} layers on the GPU, the rest on the CPU)",
    "NVIDIA GPU（{}，模型全部放在 GPU）": "NVIDIA GPU ({0}, whole model on the GPU)",
    "NVIDIA 驅動程式版本 {} 太舊，需要 {}.{} 以上（請更新驅動程式）。": "NVIDIA driver {0} is too old; {1}.{2} or later is required (please update the driver).",
    "偵測到 NVIDIA 顯示卡，但無法執行 nvidia-smi（請安裝或更新 NVIDIA 驅動程式）。": "An NVIDIA graphics card was found, but nvidia-smi cannot run (install or update the NVIDIA driver).",
    "沒有偵測到 NVIDIA 顯示卡。": "No NVIDIA graphics card was detected.",
    "這個作業系統不使用 CUDA。": "This operating system does not use CUDA.",
    "這個版本還沒有提供 GPU 版的 llama.cpp。": "This version does not provide a GPU build of llama.cpp yet.",
    "可以用 NVIDIA GPU 加速：請到「模型管理」下載「摘要 GPU 加速」。": "NVIDIA GPU acceleration is available: download “Summary GPU acceleration” in Models.",
    "可用記憶體不足：產生摘要約需 {} GB，目前只有 {} GB。請關閉其他程式（例如瀏覽器分頁）後再試一次。":
        "Not enough free memory: the summary needs about {0} GB, but only {1} GB is available. Close other programs (such as browser tabs) and try again.",
    "可用記憶體偏少（{} GB，建議 {} GB 以上），摘要可能會比較慢；建議先關閉其他程式。":
        "Free memory is low ({0} GB; {1} GB or more recommended). The summary may be slow; consider closing other programs first.",
    "可用記憶體只有 {} GB（語音辨識約需 3 GB），可能會很慢或失敗；建議先關閉其他程式。":
        "Only {0} GB of memory is free (speech recognition needs about 3 GB); it may be very slow or fail. Consider closing other programs first.",
    "可用記憶體較少（{} GB），改用較短的 context（{}）；長逐字稿會分成較多段，時間會稍長。":
        "Free memory is limited ({0} GB), so a shorter context ({1}) is used; long transcripts are split into more parts and take a little longer.",
    "其他": "Other",
    "未知": "Unknown",
    "{}（組建 {}）": "{0} (build {1})",
    "{}，驅動程式 {}": "{0}, driver {1}",
    # --- 媒體 ---
    "FFmpeg 無法抽取音訊（代碼 {}）。{}": "FFmpeg could not extract the audio (code {0}). {1}",
    "上傳已取消。": "Upload cancelled.",
    "不支援這個檔案格式。": "This file format is not supported.",
    "實際上傳的資料比宣告的檔案大小還多。": "More data was uploaded than the declared file size.",
    "工作階段已結束，請重新匯入檔案。": "The session has ended. Please import the file again.",
    "找不到 FFmpeg。請先安裝 FFmpeg（Windows：winget install Gyan.FFmpeg；macOS：brew install ffmpeg），然後重新啟動程式。":
        "FFmpeg was not found. Install FFmpeg (macOS: brew install ffmpeg; Windows: winget install Gyan.FFmpeg), then restart the app.",
    "找不到這個媒體，請重新匯入。": "Media not found. Please import it again.",
    "找不到這個工作。": "Task not found.",
    "檔案不存在（可能還沒抽取音訊）。": "The file does not exist (the audio may not be extracted yet).",
    "檔案太大：上限為 {} GB。": "The file is too large: the limit is {0} GB.",
    "檔案是空的。": "The file is empty.",
    "檔案沒有完整上傳，請重新匯入。": "The file was not uploaded completely. Please import it again.",
    "缺少檔案大小資訊。": "The file size is missing.",
    "磁碟空間不足：處理這個檔案約需 {} GB 可用空間。": "Not enough disk space: processing this file needs about {0} GB free.",
    "音訊抽取已在進行中。": "Audio extraction is already running.",
    "音訊抽取尚未完成。": "Audio extraction has not finished.",
    "摘要產生中，請等它完成或取消後再重新抽取。": "A summary is being generated. Wait until it finishes or cancel it, then extract again.",
    "語音辨識進行中，請等它完成或取消後再重新抽取。": "Speech recognition is running. Wait until it finishes or cancel it, then extract again.",
    "無法取得這個檔案的長度，檔案可能已損壞或不完整。": "Cannot read the length of this file; it may be damaged or incomplete.",
    "無法讀取這個檔案的影音資訊，檔案可能已損壞。": "Cannot read the media information of this file; it may be damaged.",
    "無法讀取這個檔案，檔案可能已損壞或不是有效的影音檔。": "Cannot read this file; it may be damaged or not a valid media file.",
    "無法辨識這個檔案的影音格式，檔案可能已損壞。": "Cannot recognize the media format of this file; it may be damaged.",
    "讀取影音資訊逾時，檔案可能已損壞。": "Reading the media information timed out; the file may be damaged.",
    "這個檔案沒有音訊軌，無法進行語音辨識。": "This file has no audio track, so speech recognition is not possible.",
    # --- 語音辨識 ---
    "{} 不支援精確對齊，時間為依字數估計。": "{0} does not support precise alignment; times are estimated from the text length.",
    "尚未下載時間戳記對齊模型，時間為依字數估計。": "The timestamp alignment model is not downloaded; times are estimated from the text length.",
    "第 {} 段文字可能不完整（超過生成長度上限）。": "The text of segment {0} may be incomplete (generation length limit reached).",
    "第 {} 段無法對齊，時間為估計值。": "Segment {0} could not be aligned; times are estimated.",
    "不支援的語言：{}": "Unsupported language: {0}",
    "不支援的 dtype：{}（可用 float32 / bfloat16 / float16）": "Unsupported dtype: {0} (use float32 / bfloat16 / float16)",
    "句子的時間不正確。": "A sentence has invalid times.",
    "句子的編號不正確。": "A sentence has an invalid number.",
    "句子的順序不正確。": "The sentences are out of order.",
    "另一個 AI 工作（語音辨識或摘要）正在進行，請等它完成後再試。": "Another AI task (speech recognition or summary) is running. Wait until it finishes and try again.",
    "尚未下載語音辨識模型。請到「模型管理」下載「語音辨識」。": "The speech recognition model is not downloaded. Download “Speech recognition” in Models.",
    "語音辨識已在進行中。": "Speech recognition is already running.",
    "語音辨識進行中，請等它完成後再編輯。": "Speech recognition is running. Wait until it finishes, then edit.",
    "請先完成「抽取音訊」，再開始語音辨識。": "Extract the audio first, then start speech recognition.",
    "還沒有這個媒體的逐字稿。": "There is no transcript for this media yet.",
    "無法載入時間戳記對齊模型：{}": "Cannot load the timestamp alignment model: {0}",
    "無法載入語音辨識模型：{}": "Cannot load the speech recognition model: {0}",
    "缺少時間戳記對齊所需的套件（torch / transformers）。": "Packages needed for timestamp alignment are missing (torch / transformers).",
    "缺少語音辨識所需的套件（torch / transformers），請重新安裝後端套件。": "Packages needed for speech recognition are missing (torch / transformers). Reinstall the backend packages.",
    "記憶體不足，無法完成語音辨識。請關閉其他程式後再試。": "Not enough memory to finish speech recognition. Close other programs and try again.",
    "記憶體不足，無法載入時間戳記對齊模型。": "Not enough memory to load the timestamp alignment model.",
    "記憶體不足，無法載入語音辨識模型。請關閉其他程式後再試。": "Not enough memory to load the speech recognition model. Close other programs and try again.",
    "語音辨識發生錯誤：{}": "Speech recognition error: {0}",
    "語音辨識程序意外結束（代碼 {}），可能是記憶體不足。請關閉其他程式後再試。": "The speech recognition process ended unexpectedly (code {0}), possibly because of low memory. Close other programs and try again.",
    "音訊格式不符（需要 16 kHz 單聲道 16-bit）：{}": "Wrong audio format (16 kHz mono 16-bit required): {0}",
    "處理時發生未預期的錯誤：{}": "Unexpected error while processing: {0}",
    # --- 摘要 ---
    "llama-server 回應異常（HTTP {}）。": "llama-server returned an error (HTTP {0}).",
    "不支援的摘要類型：{}": "Unsupported summary type: {0}",
    "呼叫摘要模型失敗。{}": "Calling the summary model failed. {0}",
    "尚未下載摘要模型（{}）。": "The summary model is not downloaded ({0}).",
    "尚未安裝 llama.cpp（摘要用的執行程式）。": "llama.cpp (the program that runs the summary) is not installed.",
    "請到「模型管理」下載「摘要與心智圖」。": "Download “Summary and mind map” in Models.",
    "摘要已在產生中。": "A summary is already being generated.",
    "摘要模型啟動失敗。": "The summary model failed to start.",
    "摘要模型在處理中結束了，可能是記憶體不足。請關閉其他程式後再試一次。": "The summary model stopped while working, possibly because of low memory. Close other programs and try again.",
    "摘要模型檔案無法讀取，可能已損壞。請重新下載模型。": "The summary model file cannot be read and may be damaged. Download the model again.",
    "摘要模型的輸出格式不正確，請再試一次。": "The summary model returned an invalid format. Please try again.",
    "摘要模型載入逾時。請確認電腦有足夠的記憶體（建議可用 6 GB 以上），再試一次。": "Loading the summary model timed out. Make sure enough memory is free (6 GB or more recommended) and try again.",
    "找不到 llama-server（{}）。請先執行模型下載腳本安裝 llama.cpp。": "llama-server was not found ({0}). Install llama.cpp in Models first.",
    "找不到摘要模型檔案（{}）。請先下載模型。": "The summary model file was not found ({0}). Download the model first.",
    "目前的 llama.cpp 版本不支援這個模型。請更新 llama.cpp。": "The current llama.cpp version does not support this model. Please update llama.cpp.",
    "記憶體不足，無法載入摘要模型。請關閉其他程式後再試一次。": "Not enough memory to load the summary model. Close other programs and try again.",
    "這一段內容超過模型一次能處理的長度。": "This part is longer than the model can process at once.",
    "請先完成語音辨識，再產生摘要。": "Finish speech recognition first, then generate the summary.",
    "請等音訊抽取與語音辨識完成後再產生摘要。": "Wait for audio extraction and speech recognition to finish, then generate the summary.",
    "請至少選擇一種摘要內容。": "Select at least one kind of summary.",
    "逐字稿沒有內容，無法產生摘要。": "The transcript is empty, so no summary can be generated.",
    "還沒有這個媒體的摘要。": "There is no summary for this media yet.",
    "不支援的 GGUF 版本 {}": "Unsupported GGUF version {0}",
    "不是 GGUF 檔案": "Not a GGUF file",
    "字串長度不合理": "Invalid string length",
    "未知的型別 {}": "Unknown type {0}",
    "檔案提早結束": "Unexpected end of file",
    # --- YouTube ---
    "Unlicense（公有領域）": "Unlicense (public domain)",
    "YouTube 影片": "YouTube video",
    "YouTube 下載元件找不到 JavaScript 執行環境，請重新啟動程式後再試。": "The YouTube downloader cannot find a JavaScript runtime. Restart the app and try again.",
    "YouTube 下載元件正在處理中。": "The YouTube downloader is busy.",
    "YouTube 下載元件正在處理中，請先取消。": "The YouTube downloader is busy. Cancel it first.",
    "YouTube 下載失敗：{}。如果一直失敗，請到「模型管理」更新 YouTube 下載元件。": "YouTube download failed: {0}. If it keeps failing, update the YouTube downloader in Models.",
    "YouTube 改版，目前的下載元件無法處理。請到「模型管理」更新 YouTube 下載元件。": "YouTube has changed and the current downloader cannot handle it. Update the YouTube downloader in Models.",
    "YouTube 要求驗證（「確認您不是機器人」）。請稍後再試，或先到「模型管理」更新 YouTube 下載元件。":
        "YouTube is asking for verification (“confirm you're not a bot”). Try again later, or update the YouTube downloader in Models first.",
    "yt-dlp 正在使用中（或被防毒軟體鎖定），請稍後再試。": "yt-dlp is in use (or locked by antivirus software). Try again later.",
    "yt-dlp 的雜湊值不一致（GitHub 與 SHA2-256SUMS 不同），已停止。": "The yt-dlp hashes do not match (GitHub and SHA2-256SUMS differ); stopped.",
    "{} 中找不到 {} 的雜湊值。": "No hash for {1} in {0}.",
    "下載到不支援的音訊格式（{}）。請到「模型管理」更新 YouTube 下載元件後再試。": "Downloaded an unsupported audio format ({0}). Update the YouTube downloader in Models and try again.",
    "下載的 yt-dlp 檔案雜湊不符，已刪除，請重新下載。": "The downloaded yt-dlp file has the wrong hash and was deleted. Please download again.",
    "下載的檔案不完整，請再試一次。": "The download is incomplete. Please try again.",
    "不支援正在進行的直播，請等直播結束後再試。": "Live streams in progress are not supported. Try again after the stream ends.",
    "不支援直播（或尚未結束的直播），請等直播結束並處理完成後再試。": "Live streams (or streams that have not finished) are not supported. Try again after the stream has ended and been processed.",
    "只支援單一影片，不支援播放清單。": "Only single videos are supported, not playlists.",
    "字幕語言不正確。": "Invalid subtitle language.",
    "安裝": "Installed",
    "更新": "Updated",
    "尚未下載 YouTube 下載元件。請到「模型管理」下載「YouTube 下載元件」。": "The YouTube downloader is not downloaded. Download “YouTube downloader” in Models.",
    "已{} yt-dlp {}。": "{0} yt-dlp {1}.",
    "已是最新版（{}）。": "Already the latest version ({0}).",
    "最新版本：{}。": "Latest version: {0}.",
    "有新版本：{}。": "New version available: {0}.",
    "最新版的 yt-dlp 沒有 {} 或 {}，請稍後再試。": "The latest yt-dlp release has no {0} or {1}. Try again later.",
    "影片因著作權問題無法觀看。": "The video is unavailable because of a copyright claim.",
    "影片無法觀看（可能已刪除、設為私人，或在這個地區無法觀看）。": "The video is unavailable (it may have been deleted, made private, or blocked in this region).",
    "找不到可下載的音訊格式。請到「模型管理」更新 YouTube 下載元件後再試。": "No downloadable audio format was found. Update the YouTube downloader in Models and try again.",
    "正在下載 YouTube 影片，請等它完成後再刪除。": "A YouTube video is downloading. Wait until it finishes, then delete.",
    "沒有取得影片字幕，請改用語音辨識。": "The video subtitles could not be downloaded; please use speech recognition.",
    "無法讀取影片資訊": "Cannot read the video information",
    "無法連線到 GitHub 取得 yt-dlp 的最新版本，請檢查網路後再試。": "Cannot reach GitHub to get the latest yt-dlp. Check your network and try again.",
    "無法連線到 YouTube，請檢查網路後再試。": "Cannot reach YouTube. Check your network and try again.",
    "直播尚未開始，無法下載。": "The live stream has not started, so it cannot be downloaded.",
    "首播尚未開始，無法下載。": "The premiere has not started, so it cannot be downloaded.",
    "讀取影片資訊逾時，請檢查網路後再試。": "Reading the video information timed out. Check your network and try again.",
    "連線到 YouTube 逾時，請檢查網路後再試。": "Connecting to YouTube timed out. Check your network and try again.",
    "這不是有效的 YouTube 影片網址。": "This is not a valid YouTube video URL.",
    "這份逐字稿來自影片作者提供的字幕（{}），沒有經過語音辨識。": "This transcript comes from the subtitles provided by the video's author ({0}); no speech recognition was used.",
    "這個作業系統沒有官方的 yt-dlp 執行檔。": "There is no official yt-dlp program for this operating system.",
    "這是會員限定影片，無法下載。": "This is a members-only video and cannot be downloaded.",
    "這是私人影片，無法下載。": "This is a private video and cannot be downloaded.",
    "這部影片在你所在的地區無法觀看。": "This video is not available in your region.",
    "這部影片有年齡限制，需要登入 YouTube，本程式不支援。": "This video is age-restricted and requires signing in to YouTube, which this app does not support.",
    "（沒有錯誤訊息）": "(no error message)",
    "使用環境變數指定的 llama-server：{}（不下載）": "Using the llama-server set by the environment variable: {0} (not downloading)",
    "llama.cpp {}（{}）：已安裝，略過（{}）": "llama.cpp {0} ({1}): already installed, skipped ({2})",
    "llama.cpp {}：已安裝到 {}": "llama.cpp {0}: installed to {1}",
    "{}：已安裝到 {}（{} 秒）": "{0}: installed to {1} ({2} s)",
    "{}：已安裝，略過（{}）": "{0}: already installed, skipped ({1})",
    "MVR2T：正在處理（AI 工作或模型下載）": "MVR2T: processing (AI task or model download)",
}


@lru_cache(maxsize=1)
def _patterns() -> tuple[tuple[re.Pattern[str], str, int], ...]:
    out: list[tuple[re.Pattern[str], str, int, int]] = []
    for zh, en in EN.items():
        parts = zh.split("{}")
        rx = "^" + "(.+?)".join(re.escape(p) for p in parts) + "$"
        out.append((re.compile(rx, re.S), en, len(parts) - 1, sum(len(p) for p in parts)))
    # 先比對固定文字較多的樣板（較具體）：「第 {} / {} 段」要比「{} 段」先比對
    out.sort(key=lambda t: -t[3])
    return tuple((rx, en, n) for rx, en, n, _ in out)


def _whole(text: str) -> str | None:
    if text in EN:
        return EN[text]
    for rx, en, n in _patterns():
        if n == 0:
            continue
        m = rx.match(text)
        if m:
            return en.format(*(translate(g) for g in m.groups()))
    return None


def translate(text: str, lang: str = "en") -> str:
    """把一則訊息翻成英文；不是中文、或對不到時原樣回傳。"""
    if lang != "en" or not text or not CJK.search(text):
        return text
    hit = _whole(text)
    if hit is not None:
        return hit
    # 依句子切開：「A。B」「A；B」
    pieces = [p for p in re.split(r"(?<=[。；])", text) if p]
    if len(pieces) > 1:
        out = []
        for p in pieces:
            core = p[:-1] if p.endswith("；") else p
            t = _whole(core) or _whole(core.rstrip("。")) or core
            out.append(t)
        return " ".join(out)
    return text


#: 會被翻譯的 JSON 欄位（其他欄位例如逐字稿內容、檔名不動）
FIELDS = frozenset({
    "detail", "stage", "message", "warnings", "reason", "name", "role", "hardware", "current", "problems", "note",
    "cuda_reason", "metal_reason", "os_name", "license", "cpu_name",
})


def translate_json(value: Any, lang: str, key: str | None = None) -> Any:
    if lang != "en":
        return value
    if isinstance(value, dict):
        return {k: translate_json(v, lang, k) for k, v in value.items()}
    if isinstance(value, list):
        return [translate_json(v, lang, key) for v in value]
    if isinstance(value, str) and key in FIELDS:
        return translate(value, lang)
    return value


# ---------------------------------------------------------------------------
# 回應翻譯（前端以 X-MVR2T-Lang: en 要求英文）
# ---------------------------------------------------------------------------

LANG_HEADER = "x-mvr2t-lang"
#: 這些路徑的 JSON 全部經過 translate_json（只翻 FIELDS 欄位）；其他路徑只翻錯誤回應的 detail
TRANSLATED_PREFIXES = ("/api/tasks", "/api/models", "/api/system", "/api/youtube/component", "/api/settings", "/api/transcript")


def wants_english(headers: Any) -> bool:
    return str(headers.get(LANG_HEADER, "")).lower().startswith("en")
