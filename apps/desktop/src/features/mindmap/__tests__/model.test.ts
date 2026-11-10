import { describe, expect, it } from 'vitest';
import type { MindMapNode } from '@shared/types/api';
import {
  addChild,
  addSibling,
  countDescendants,
  findNode,
  fromSummary,
  layout,
  moveBy,
  removeNode,
  resetLayout,
  setSide,
  setAllCollapsed,
  setText,
  toggleCollapsed,
  toggleConclusion,
} from '../model';

const n = (id: string, text: string, kind: MindMapNode['kind'], children: MindMapNode[] = []): MindMapNode => ({
  id,
  text,
  kind,
  refs: [],
  time: null,
  children,
});

const SAMPLE = n('n', '中山店會議', 'central', [
  n('n-1', '開幕', 'main', [n('n-1-1', '咖啡機', 'sub', [n('n-1-1-1', '九月十號確認', 'conclusion')]), n('n-1-2', '招牌', 'sub')]),
  n('n-2', '會員點數', 'main', [n('n-2-1', 'LINE 集點', 'sub')]),
  n('n-3', '人力', 'main', [n('n-3-1', '兼職招募', 'sub'), n('n-3-2', '教育訓練', 'sub')]),
  n('n-4', '行銷', 'main'),
]);

describe('mind map editing', () => {
  it('edits text but never allows an empty node', () => {
    const t = fromSummary(SAMPLE);
    expect(findNode(setText(t, 'n-2', ' 會員 '), 'n-2')?.text).toBe('會員');
    expect(setText(t, 'n-2', '   ')).toBe(t);
  });

  it('adds children with the next level kind, up to four levels', () => {
    const t = fromSummary(SAMPLE);
    const [t1, id1] = addChild(t, 'n', '新分支');
    expect(findNode(t1, id1!)?.kind).toBe('main');
    const [t2, id2] = addChild(t1, 'n-1-1');
    expect(findNode(t2, id2!)?.kind).toBe('detail');
    const [t3, id3] = addChild(t2, 'n-1-1-1');
    expect(id3).toBeNull();
    expect(t3).toBe(t2);
  });

  it('adds siblings right after the node and keeps the original unchanged (immutable)', () => {
    const t = fromSummary(SAMPLE);
    const [t1, id] = addSibling(t, 'n-1-1');
    expect(findNode(t1, 'n-1')!.children.map((c) => c.id)).toEqual(['n-1-1', id, 'n-1-2']);
    expect(findNode(t, 'n-1')!.children).toHaveLength(2);
    expect(addSibling(t, 'n')[1]).toBeNull(); // the central topic has no siblings
  });

  it('deletes a subtree but never the central topic', () => {
    const t = fromSummary(SAMPLE);
    const t1 = removeNode(t, 'n-1');
    expect(findNode(t1, 'n-1-1')).toBeNull();
    expect(countDescendants(t1)).toBe(countDescendants(t) - 4);
    expect(removeNode(t, 'n')).toBe(t);
  });

  it('collapses and toggles conclusions', () => {
    const t = fromSummary(SAMPLE);
    expect(findNode(toggleCollapsed(t, 'n-1'), 'n-1')?.collapsed).toBe(true);
    expect(findNode(toggleCollapsed(t, 'n-4'), 'n-4')?.collapsed).toBe(false); // nothing to collapse
    const all = setAllCollapsed(t, true);
    expect(all.collapsed).toBe(false);
    expect(findNode(all, 'n-1')?.collapsed).toBe(true);
    expect(findNode(toggleConclusion(t, 'n-1-1-1'), 'n-1-1-1')?.kind).toBe('detail');
    expect(findNode(toggleConclusion(t, 'n-1'), 'n-1')?.kind).toBe('main');
  });
});

describe('mind map layout', () => {
  it('puts the centre in the middle and splits main branches to both sides', () => {
    const placed = layout(fromSummary(SAMPLE));
    const root = placed.find((p) => p.node.id === 'n')!;
    expect(root.x + root.width / 2).toBeCloseTo(0);
    const mains = placed.filter((p) => p.depth === 1);
    expect(new Set(mains.map((m) => m.side))).toEqual(new Set(['left', 'right']));
    for (const p of placed) {
      if (p.side === 'right') expect(p.x).toBeGreaterThan(root.x + root.width);
      if (p.side === 'left') expect(p.x + p.width).toBeLessThan(root.x);
    }
  });

  it('children sit one column further out than their parent, and siblings do not overlap', () => {
    const placed = layout(fromSummary(SAMPLE));
    const byId = new Map(placed.map((p) => [p.node.id, p]));
    for (const p of placed) {
      if (!p.parentId || p.depth < 2) continue;
      const parent = byId.get(p.parentId)!;
      if (p.side === 'right') expect(p.x).toBeGreaterThan(parent.x + parent.width);
      else expect(p.x + p.width).toBeLessThan(parent.x);
    }
    for (const side of ['left', 'right'] as const) {
      for (let depth = 1; depth <= 3; depth++) {
        const col = placed.filter((p) => p.side === side && p.depth === depth).sort((a, b) => a.y - b.y);
        for (let i = 1; i < col.length; i++) expect(col[i].y).toBeGreaterThanOrEqual(col[i - 1].y + col[i - 1].height);
      }
    }
  });

  it('hides collapsed descendants and reports how many', () => {
    const placed = layout(toggleCollapsed(fromSummary(SAMPLE), 'n-1'));
    expect(placed.find((p) => p.node.id === 'n-1-1')).toBeUndefined();
    expect(placed.find((p) => p.node.id === 'n-1')!.hidden).toBe(3);
  });

  it('a dragged branch moves with its descendants; reset puts everything back', () => {
    const t = fromSummary(SAMPLE);
    const before = new Map(layout(t).map((p) => [p.node.id, p]));
    const moved = moveBy(t, 'n-1', 30, -20);
    const after = new Map(layout(moved).map((p) => [p.node.id, p]));
    for (const id of ['n-1', 'n-1-1', 'n-1-1-1']) {
      expect(after.get(id)!.x - before.get(id)!.x).toBe(30);
      expect(after.get(id)!.y - before.get(id)!.y).toBe(-20);
    }
    expect(after.get('n-2')!.x).toBe(before.get('n-2')!.x);
    expect(layout(resetLayout(moved)).map((p) => [p.x, p.y])).toEqual(layout(t).map((p) => [p.x, p.y]));
  });

  it('branches keep their side when collapsing or adding; a new branch goes to the shorter side', () => {
    const t = fromSummary(SAMPLE);
    const sideOf = (tree: typeof t) => new Map(layout(tree).filter((p) => p.depth === 1).map((p) => [p.node.id, p.side]));
    const before = sideOf(t);
    expect(sideOf(toggleCollapsed(t, 'n-1'))).toEqual(before);
    expect(sideOf(setAllCollapsed(t, true))).toEqual(before);
    const [t1, id] = addChild(t, 'n', '新分支');
    const after = sideOf(t1);
    for (const [k, v] of before) expect(after.get(k)).toBe(v);
    const height = (side: string) =>
      layout(t).filter((p) => p.depth >= 1 && p.side === side).reduce((s, p) => s + p.height, 0);
    expect(after.get(id!)).toBe(height('right') <= height('left') ? 'right' : 'left');
  });

  it('a main branch can be moved to the other side', () => {
    const t = fromSummary(SAMPLE);
    const side = layout(t).find((p) => p.node.id === 'n-2')!.side;
    const other = side === 'left' ? 'right' : 'left';
    const moved = setSide(moveBy(t, 'n-2', 10, 10), 'n-2', other);
    const p = layout(moved).find((q) => q.node.id === 'n-2')!;
    expect(p.side).toBe(other);
    expect(findNode(moved, 'n-2')!.offset).toEqual({ x: 0, y: 0 });
    expect(setSide(t, 'n-1-1', 'left')).toBe(t); // only main branches
  });
});
