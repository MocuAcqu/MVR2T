import { toPng, toSvg } from 'html-to-image';
import { getViewportForBounds, type Rect } from '@xyflow/react';
import type { SaveFileKind } from '@shared/types/ipc';
import { NO_EXPORT } from './MindMapNode';
import { t } from '@/i18n';

const PADDING = 40;
/** PNG 最長邊上限（避免超大畫布在部分電腦上失敗） */
const MAX_PNG_SIDE = 8000;

export function exportFileName(mediaName: string): string {
  const base = mediaName.replace(/\.[^.]+$/, '').trim() || t('心智圖');
  return t('{0}-心智圖', base);
}

/**
 * 把 React Flow 的畫面（.react-flow__viewport）輸出成 PNG 或 SVG。
 * 不嵌入網頁字型（skipFonts）：PNG 在這台電腦上用目前的字型繪製；SVG 在其他電腦開啟時使用系統的中文字型。
 */
export async function renderMindMap(viewportEl: HTMLElement, bounds: Rect, kind: SaveFileKind): Promise<string> {
  const width = Math.ceil(bounds.width + PADDING * 2);
  const height = Math.ceil(bounds.height + PADDING * 2);
  const vp = getViewportForBounds(bounds, width, height, 1, 1, 0);
  const options = {
    backgroundColor: '#ffffff',
    width,
    height,
    skipFonts: true,
    pixelRatio: kind === 'png' ? Math.max(1, Math.min(2, MAX_PNG_SIDE / Math.max(width, height))) : 1,
    style: {
      width: `${width}px`,
      height: `${height}px`,
      // getViewportForBounds 已把內容置中在含留白的畫布中
      transform: `translate(${vp.x}px, ${vp.y}px) scale(1)`,
      fontFamily: "'Inter Variable', 'Noto Sans TC Variable', 'Microsoft JhengHei', 'PingFang TC', 'Noto Sans CJK TC', sans-serif",
    },
    filter: (el: Node) => !(el instanceof Element && el.classList.contains(NO_EXPORT)),
  };
  return kind === 'png' ? toPng(viewportEl, options) : toSvg(viewportEl, options);
}

/** data URL → 存檔用的資料（PNG：base64；SVG：UTF-8 文字）。 */
export function dataUrlPayload(dataUrl: string, kind: SaveFileKind): string {
  const comma = dataUrl.indexOf(',');
  const head = dataUrl.slice(0, comma);
  const body = dataUrl.slice(comma + 1);
  if (kind === 'png') return body;
  const svg = head.endsWith(';base64') ? new TextDecoder().decode(Uint8Array.from(atob(body), (c) => c.charCodeAt(0))) : decodeURIComponent(body);
  return svg.startsWith('<?xml') ? svg : `<?xml version="1.0" encoding="UTF-8"?>\n${svg}`;
}

/** 儲存：桌面版跳出「另存新檔」對話框；瀏覽器預覽改用下載。回傳儲存的路徑（取消則 null）。 */
export async function saveImage(dataUrl: string, kind: SaveFileKind, defaultName: string): Promise<string | null> {
  const data = dataUrlPayload(dataUrl, kind);
  if (window.mvr2t?.saveFile) {
    const res = await window.mvr2t.saveFile({ defaultName, kind, data });
    return res.saved ? res.path : null;
  }
  const a = document.createElement('a');
  a.href = kind === 'svg' ? URL.createObjectURL(new Blob([data], { type: 'image/svg+xml' })) : dataUrl;
  a.download = `${defaultName}.${kind}`;
  a.click();
  if (kind === 'svg') setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  return a.download;
}
