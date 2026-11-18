## MVR2T 0.1.0 — 第一個正式版（Windows）

在你的電腦上把影片與錄音轉成**逐字稿、摘要與心智圖**。AI 模型下載一次後完全離線執行，檔案不會上傳。

### 下載
- **`MVR2T-Setup-0.1.0-x64.exe`**（約 348 MB）— Windows 10／11（64 位元）
- SHA-256：`{{SHA256}}`
  （驗證：PowerShell 執行 `Get-FileHash .\MVR2T-Setup-0.1.0-x64.exe -Algorithm SHA256`）

### 系統需求
- Windows 10 或 11（64 位元）
- 記憶體 8 GB 以上（建議 16 GB）
- 磁碟可用空間約 10 GB（程式約 1.2 GB、AI 模型約 6 GB）
- 第一次使用需要網路下載 AI 模型

### 安裝
1. 下載並執行安裝檔。這個版本**沒有數位簽章**，Windows 會顯示「Windows 已保護您的電腦」：按「其他資訊」→「仍要執行」。
   防毒軟體（例如 Avast）可能會先掃描一次。
2. 安裝只需要目前使用者的權限，完成後從桌面或開始功能表開啟 **MVR2T**。
3. 到「模型管理」下載「語音辨識」與「摘要與心智圖」（約 6 GB）。之後除了 YouTube 功能都可以離線使用。

### 功能
- 匯入影片（MP4、MOV、MKV、WEBM）或錄音（MP3、WAV、M4A、FLAC、AAC、OGG），或貼上 YouTube 網址（只下載音訊）
- 本機語音辨識（Qwen3-ASR）與每句時間戳記；中文自動轉繁體
- 逐字稿編輯（修改、合併、刪除、復原）與播放器（點時間從那一句播放）
- 本機摘要（全文摘要、重點、筆記、主題、關鍵字、行動事項、問題與結論）與可編輯的心智圖
- 匯出 TXT、SRT、VTT、JSON、Markdown、CSV、Word、PDF、PNG、SVG、切段音檔 ZIP
- 介面：繁體中文／English

### 注意
- YouTube 功能請只用於你自己擁有或已獲授權的影片；是否符合 YouTube 服務條款與著作權規定由使用者自行負責。
- 解除安裝時會保留 `%APPDATA%\MVR2T`（已下載的模型與設定），要完全移除請手動刪除該資料夾。
- 已知限制：沒有數位簽章；NVIDIA 顯示卡加速尚未在實機測試；沒有 macOS 版。

---

**English:** MVR2T turns videos and recordings into transcripts, summaries and mind maps on your own Windows PC. Models are downloaded once
and then run fully offline. The installer is unsigned: on the SmartScreen prompt choose “More info” → “Run anyway”. Requires Windows 10/11 x64,
8 GB+ RAM and about 10 GB of disk space. Switch the interface to English in Settings → Interface language.
