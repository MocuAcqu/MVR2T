import type { MindMapKind, MindMapNode, TimeSpan } from '@shared/types/api';

/**
 * 可編輯的心智圖（PROJECT_SPEC §4-F、Phase 07）。只存在本次 Session 的記憶體中（§8.3）。
 * 所有操作都是純函式、回傳新的樹（方便復原與測試）。
 */
export interface MindNode {
  id: string;
  text: string;
  kind: MindMapKind;
  refs: number[];
  time: TimeSpan | null;
  children: MindNode[];
  /** 收合：子節點不顯示 */
  collapsed: boolean;
  /** 使用者拖曳造成的位移（相對於自動排版位置）；子孫節點一起移動 */
  offset: { x: number; y: number };
  /** 主要分支放在中心的哪一邊（只用於 kind = main；undefined = 自動分配） */
  side?: 'left' | 'right';
}

export const LEVEL_OF: Record<MindMapKind, number> = { central: 0, main: 1, sub: 2, detail: 3, conclusion: 3 };
const KIND_AT_LEVEL: MindMapKind[] = ['central', 'main', 'sub', 'detail'];
export const MAX_LEVEL = 3;

function convert(node: MindMapNode): MindNode {
  return {
    id: node.id,
    text: node.text,
    kind: node.kind,
    refs: node.refs,
    time: node.time,
    children: node.children.map(convert),
    collapsed: false,
    offset: { x: 0, y: 0 },
  };
}

/** 由 AI 產生的心智圖建立可編輯的樹；主要分支先固定好左右（之後收合、新增不會讓分支跳邊）。 */
export function fromSummary(node: MindMapNode): MindNode {
  return balanceSides(convert(node));
}

/** 可編輯的樹 → 後端的心智圖格式（匯出摘要時使用；去掉收合、位移等畫面狀態）。 */
export function toSummary(node: MindNode): MindMapNode {
  return { id: node.id, text: node.text, kind: node.kind, refs: node.refs, time: node.time, children: node.children.map(toSummary) };
}

// ---------------------------------------------------------------------------
// 查詢
// ---------------------------------------------------------------------------

export function findNode(root: MindNode, id: string): MindNode | null {
  if (root.id === id) return root;
  for (const c of root.children) {
    const hit = findNode(c, id);
    if (hit) return hit;
  }
  return null;
}

export function findParent(root: MindNode, id: string): MindNode | null {
  for (const c of root.children) {
    if (c.id === id) return root;
    const hit = findParent(c, id);
    if (hit) return hit;
  }
  return null;
}

export function countDescendants(node: MindNode): number {
  return node.children.reduce((n, c) => n + 1 + countDescendants(c), 0);
}

export function allIds(root: MindNode): string[] {
  return [root.id, ...root.children.flatMap(allIds)];
}

// ---------------------------------------------------------------------------
// 編輯
// ---------------------------------------------------------------------------

function mapNode(root: MindNode, id: string, fn: (n: MindNode) => MindNode): MindNode {
  if (root.id === id) return fn(root);
  let changed = false;
  const children = root.children.map((c) => {
    const next = mapNode(c, id, fn);
    if (next !== c) changed = true;
    return next;
  });
  return changed ? { ...root, children } : root;
}

export function setText(root: MindNode, id: string, text: string): MindNode {
  const t = text.trim();
  if (!t) return root; // 不允許空白節點
  return mapNode(root, id, (n) => ({ ...n, text: t }));
}

export function toggleCollapsed(root: MindNode, id: string): MindNode {
  return mapNode(root, id, (n) => (n.children.length ? { ...n, collapsed: !n.collapsed } : n));
}

export function setAllCollapsed(root: MindNode, collapsed: boolean): MindNode {
  const walk = (n: MindNode, level: number): MindNode => ({
    ...n,
    // 全部收合：只留中心與主要分支
    collapsed: collapsed && level >= 1 && n.children.length > 0,
    children: n.children.map((c) => walk(c, level + 1)),
  });
  return walk(root, 0);
}

export function moveBy(root: MindNode, id: string, dx: number, dy: number): MindNode {
  return mapNode(root, id, (n) => ({ ...n, offset: { x: n.offset.x + dx, y: n.offset.y + dy } }));
}

/** 清除拖曳位移，並依目前內容重新平均分配左右。 */
export function resetLayout(root: MindNode): MindNode {
  const walk = (n: MindNode): MindNode => ({ ...n, offset: { x: 0, y: 0 }, side: undefined, children: n.children.map(walk) });
  return balanceSides(walk(root));
}

/** 主要分支依「完整展開」的子樹高度平均分到左右，並寫入 side。 */
export function balanceSides(root: MindNode): MindNode {
  const expanded = setAllCollapsed(root, false);
  const sides = assignSides(expanded);
  return { ...root, children: root.children.map((c) => ({ ...c, side: sides.get(c.id) })) };
}

/** 新的主要分支放在目前較短的一側。 */
function lighterSide(root: MindNode): 'left' | 'right' {
  const expanded = setAllCollapsed(root, false);
  const memo = new Map<string, number>();
  const sides = assignSides(expanded, memo);
  let left = 0;
  let right = 0;
  for (const m of expanded.children) {
    const h = memo.get(m.id) ?? 0;
    if (sides.get(m.id) === 'left') left += h;
    else right += h;
  }
  return right <= left ? 'right' : 'left';
}

/** 把主要分支移到中心的另一側（拖曳越過中心時），並清除它的拖曳位移。 */
export function setSide(root: MindNode, id: string, side: 'left' | 'right'): MindNode {
  if (!root.children.some((c) => c.id === id)) return root;
  return mapNode(root, id, (n) => ({ ...n, side, offset: { x: 0, y: 0 } }));
}

export function toggleConclusion(root: MindNode, id: string): MindNode {
  return mapNode(root, id, (n) =>
    n.kind === 'detail' ? { ...n, kind: 'conclusion' } : n.kind === 'conclusion' ? { ...n, kind: 'detail' } : n,
  );
}

let seq = 0;
const newId = (parentId: string) => `${parentId}-u${Date.now().toString(36)}${(seq++).toString(36)}`;

/** 新增子節點；回傳 [新樹, 新節點 id]。細節／結論之下不能再新增（最多四層）。 */
export function addChild(root: MindNode, parentId: string, text = '新節點'): [MindNode, string | null] {
  const parent = findNode(root, parentId);
  if (!parent || LEVEL_OF[parent.kind] >= MAX_LEVEL) return [root, null];
  const id = newId(parentId);
  const child: MindNode = {
    id,
    text,
    kind: KIND_AT_LEVEL[LEVEL_OF[parent.kind] + 1],
    refs: [],
    time: null,
    children: [],
    collapsed: false,
    offset: { x: 0, y: 0 },
    side: parent.id === root.id ? lighterSide(root) : undefined,
  };
  return [mapNode(root, parentId, (n) => ({ ...n, collapsed: false, children: [...n.children, child] })), id];
}

/** 在同一層、這個節點之後新增；中心主題沒有同層。 */
export function addSibling(root: MindNode, id: string, text = '新節點'): [MindNode, string | null] {
  const parent = findParent(root, id);
  if (!parent) return [root, null];
  const self = findNode(root, id)!;
  const newNodeId = newId(parent.id);
  const sibling: MindNode = {
    id: newNodeId,
    text,
    kind: self.kind === 'conclusion' ? 'detail' : self.kind,
    refs: [],
    time: null,
    children: [],
    collapsed: false,
    offset: { x: 0, y: 0 },
    side: self.side,
  };
  return [
    mapNode(root, parent.id, (p) => {
      const i = p.children.findIndex((c) => c.id === id);
      return { ...p, children: [...p.children.slice(0, i + 1), sibling, ...p.children.slice(i + 1)] };
    }),
    newNodeId,
  ];
}

/** 刪除節點與其子孫；中心主題不能刪除。 */
export function removeNode(root: MindNode, id: string): MindNode {
  if (root.id === id) return root;
  const parent = findParent(root, id);
  if (!parent) return root;
  return mapNode(root, parent.id, (p) => ({ ...p, children: p.children.filter((c) => c.id !== id) }));
}

// ---------------------------------------------------------------------------
// 排版：中心在 (0, 0)，主要分支平均分到左右兩側；每一側由內往外一欄一欄排
// ---------------------------------------------------------------------------

export const NODE_WIDTH: Record<MindMapKind, number> = { central: 240, main: 190, sub: 180, detail: 210, conclusion: 210 };
const FONT_PX: Record<MindMapKind, number> = { central: 18, main: 15, sub: 14, detail: 13, conclusion: 13 };
const PAD_Y: Record<MindMapKind, number> = { central: 32, main: 24, sub: 20, detail: 18, conclusion: 18 };
const COL_GAP = 64;
const ROW_GAP = 14;

/** 依字數估計節點高度（中文字寬約等於字級；英數約一半）。實際顯示時文字會在節點內換行。 */
export function estimateHeight(node: Pick<MindNode, 'kind' | 'text' | 'time'>): number {
  const font = FONT_PX[node.kind];
  const inner = NODE_WIDTH[node.kind] - 28;
  let width = 0;
  for (const ch of node.text) width += /[\u0000-ÿ]/.test(ch) ? font * 0.55 : font;
  const lines = Math.max(1, Math.ceil(width / inner));
  const chip = node.time && node.kind !== 'central' ? 22 : 0;
  const badge = node.kind === 'conclusion' ? 22 : 0;
  return Math.round(lines * font * 1.45 + PAD_Y[node.kind] + chip + badge);
}

export interface Placed {
  node: MindNode;
  /** 節點左上角 */
  x: number;
  y: number;
  width: number;
  height: number;
  side: 'left' | 'right' | 'center';
  parentId: string | null;
  depth: number;
  /** 隱藏的子孫數（收合時顯示在按鈕上） */
  hidden: number;
}

const visibleChildren = (n: MindNode) => (n.collapsed ? [] : n.children);

/** 節點高度：畫面上量到的實際高度優先，否則用估計值 */
type HeightOf = (n: MindNode) => number;

function subtreeHeight(n: MindNode, memo: Map<string, number>, heightOf: HeightOf = estimateHeight): number {
  const own = heightOf(n);
  const kids = visibleChildren(n);
  const total = kids.length ? kids.reduce((s, c) => s + subtreeHeight(c, memo, heightOf), 0) + ROW_GAP * (kids.length - 1) : 0;
  const h = Math.max(own, total);
  memo.set(n.id, h);
  return h;
}

/** 主要分支依子樹高度平均分到兩邊（使用者指定 side 的優先）。 */
export function assignSides(
  root: MindNode,
  memo = new Map<string, number>(),
  heightOf: HeightOf = estimateHeight,
): Map<string, 'left' | 'right'> {
  const sides = new Map<string, 'left' | 'right'>();
  let right = 0;
  let left = 0;
  // 依原本順序：先放右邊（閱讀順序從右上開始，順時針），高度較少的一邊優先
  for (const m of root.children) {
    const h = subtreeHeight(m, memo, heightOf) + ROW_GAP;
    const side = m.side ?? (right <= left ? 'right' : 'left');
    sides.set(m.id, side);
    if (side === 'right') right += h;
    else left += h;
  }
  return sides;
}

/**
 * 排版。`measured`：畫面上量到的節點高度（文字換行可能比估計的多），有的話優先使用，避免節點重疊。
 */
export function layout(root: MindNode, measured?: ReadonlyMap<string, number>): Placed[] {
  const heightOf: HeightOf = (n) => measured?.get(n.id) ?? estimateHeight(n);
  const memo = new Map<string, number>();
  const sides = assignSides(root, memo, heightOf);
  const placed: Placed[] = [];
  const rootH = heightOf(root);
  const rootW = NODE_WIDTH.central;
  placed.push({
    node: root,
    x: -rootW / 2 + root.offset.x,
    y: -rootH / 2 + root.offset.y,
    width: rootW,
    height: rootH,
    side: 'center',
    parentId: null,
    depth: 0,
    hidden: root.collapsed ? countDescendants(root) : 0,
  });
  if (root.collapsed) return placed;

  // 每一欄的起點：中心半寬 + 間距，之後每層加上該層節點寬
  const colStart = [0, rootW / 2 + COL_GAP];
  for (let level = 2; level <= MAX_LEVEL; level++) colStart[level] = colStart[level - 1] + NODE_WIDTH[KIND_AT_LEVEL[level - 1]] + COL_GAP;

  for (const side of ['right', 'left'] as const) {
    const mains = root.children.filter((m) => sides.get(m.id) === side);
    const total = mains.reduce((s, m) => s + (memo.get(m.id) ?? 0), 0) + ROW_GAP * Math.max(0, mains.length - 1);
    let top = -total / 2;
    const place = (n: MindNode, depth: number, blockTop: number, parentId: string, inherited: { x: number; y: number }) => {
      const block = memo.get(n.id) ?? heightOf(n);
      const h = heightOf(n);
      const w = NODE_WIDTH[n.kind];
      const off = { x: inherited.x + n.offset.x, y: inherited.y + n.offset.y };
      const x = side === 'right' ? colStart[depth] : -colStart[depth] - w;
      placed.push({
        node: n,
        x: x + off.x,
        y: blockTop + (block - h) / 2 + off.y,
        width: w,
        height: h,
        side,
        parentId,
        depth,
        hidden: n.collapsed ? countDescendants(n) : 0,
      });
      const kids = visibleChildren(n);
      const kidsTotal = kids.reduce((s, c) => s + (memo.get(c.id) ?? 0), 0) + ROW_GAP * Math.max(0, kids.length - 1);
      let childTop = blockTop + (block - kidsTotal) / 2;
      for (const c of kids) {
        place(c, depth + 1, childTop, n.id, off);
        childTop += (memo.get(c.id) ?? 0) + ROW_GAP;
      }
    };
    for (const m of mains) {
      place(m, 1, top, root.id, root.offset);
      top += (memo.get(m.id) ?? 0) + ROW_GAP;
    }
  }
  return placed;
}
