# MVR2T 設計規範（Phase 02）

方向：Uber 風格，黑白、粗體標題、緊湊排版、強對比（見 PROJECT_SPEC 12.1）。
參考：getdesign.md 上社群整理的 Uber DESIGN.md。這是對 uber.com 公開外觀的**非官方分析**，只當作靈感，不是 Uber 官方規範。
所有 token 定義在 `apps/desktop/tailwind.config.ts`，元件在 `apps/desktop/src/components/ui/`。開發模式下可從導覽列「設計規範」頁面檢視。

## 色彩

| Token | 色碼 | 用途 |
|---|---|---|
| `foreground` | `#000000` | 主要按鈕、標題、選取中的導覽、頁尾 |
| `background` | `#ffffff` | 頁面與卡片表面、黑底上的文字 |
| `chip` | `#efefef` | 次要按鈕、導覽膠囊、檔案資訊底色 |
| `hover-gray` | `#e2e2e2` | 次要元件的 hover |
| `hover-light` | `#f3f3f3` | 外框按鈕的 hover |
| `body-gray` | `#4b4b4b` | 次要文字、placeholder（對白底符合 WCAG AA） |
| `muted-gray` | `#afafaf` | **只用在黑底**（對白底對比不足） |

規則：不使用彩色、漸層、近黑或米白。狀態一律用「形狀加文字」表達（實心圓＝正常、空心＝失敗、虛線＝檢查中），不只靠顏色。

## 字型與字級

- 字型：Inter（英文）加 Noto Sans TC（繁體中文），以 `@fontsource-variable` **內建於安裝檔**，離線可用，不使用 CDN。
- 標題一律 700，介面文字 500，內文 400。

| 角色 | 類別 | 大小 / 行高 |
|---|---|---|
| Display | `text-display` | 52px / 1.23（`xl` 以上；以下用 `text-h1`） |
| 頁面標題 | `text-h1` | 36px / 1.22 |
| 區塊標題 | `text-h2` | 24px / 1.33 |
| 卡片標題 | `text-h3` | 20px / 1.4 |
| 導覽、重點 | `text-lg` | 18px / 1.33 |
| 內文 | `text-base` | 16px / 1.5 |
| 說明 | `text-sm` | 14px / 1.43 |
| 細項 | `text-xs` | 12px / 1.67 |

## 形狀、陰影、間距

- 圓角：按鈕、標籤、導覽一律膠囊 `rounded-pill`（999px）；卡片與輸入框 `rounded-lg`（8px）；重點卡片 `rounded-xl`（12px）。
- 陰影：只用極淡的 `shadow-card`（0.12）；卡片靠陰影區隔，不加邊框。
- 邊框：只出現在輸入框（1px 黑）、拖放區（虛線）與分隔線（`chip`）。
- 間距：4/8px 網格。卡片內距 24px。內容最大寬度 1136px。

## 元件

- **Button**：`default`（黑）、`secondary`（chip）、`outline`、`ghost`、`inverse`（黑底使用）；尺寸 `sm` 36px、`default` 44px、`lg` 48px。
- **Input**：1px 黑框、8px 圓角；`aria-invalid` 時邊框加粗。
- **Card**：標準與 `featured`。
- **Badge**：`default`、`solid`、`outline`。
- 所有可互動元件都有明確的鍵盤焦點環（2px 黑色加 2px 間隔）。

## 響應式

斷點：`sm` 600、`md` 768、`lg` 960（Electron 最小視窗寬度）、`xl` 1120。
首頁在 `lg` 以上為左右分欄，以下堆疊；導覽列過窄時可橫向捲動；狀態卡片在 `md` 以上並排。

## 不要做

- 不加入彩色、漸層、重陰影。
- 按鈕不使用小於膠囊的圓角。
- 不用大寫字母標籤、箭頭裝飾或無意義的編號。
