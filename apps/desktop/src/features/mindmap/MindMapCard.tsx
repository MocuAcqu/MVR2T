import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import {
  Background,
  BackgroundVariant,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  applyNodeChanges,
  getNodesBounds,
  useReactFlow,
  type Edge,
  type NodeChange,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { SaveFileKind } from '@shared/types/ipc';
import { Mono } from '@/components/mono/Mono';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { startMindmap } from '@/features/media/mediaController';
import { cn } from '@/lib/utils';
import { useSessionStore } from '@/stores/sessionStore';
import { exportFileName, renderMindMap, saveImage } from './exportImage';
import { MindActionsContext, MindNodeView, type MindActions, type MindFlowNode } from './MindMapNode';
import {
  LEVEL_OF,
  MAX_LEVEL,
  addChild,
  addSibling,
  allIds,
  estimateHeight,
  findNode,
  findParent,
  layout,
  moveBy,
  removeNode,
  resetLayout,
  setAllCollapsed,
  setSide,
  setText,
  toggleCollapsed,
  toggleConclusion,
  type MindNode,
} from './model';

const NODE_TYPES = { mind: MindNodeView };
const HISTORY_LIMIT = 100;
const isMac = typeof navigator !== 'undefined' && /Mac/.test(navigator.platform);

function ToolButton({ onClick, disabled, title, children }: { onClick: () => void; disabled?: boolean; title: string; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="rounded-pill bg-chip px-3 py-1.5 text-sm font-medium transition-colors hover:bg-hover-gray focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}

const Sep = () => <span aria-hidden className="mx-1 h-5 w-px bg-hover-gray" />;

/** 心智圖編輯器（React Flow）。樹狀資料在 sessionStore，這裡負責顯示、拖曳、編輯與復原。 */
function MindMapEditor({ root, mediaName }: { root: MindNode; mediaName: string }) {
  const setStore = useSessionStore((s) => s.set);
  const rf = useReactFlow<MindFlowNode, Edge>();
  const wrapRef = useRef<HTMLDivElement>(null);
  const past = useRef<MindNode[]>([]);
  const future = useRef<MindNode[]>([]);
  const lastCommitted = useRef<MindNode>(root);
  const [, forceRender] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  // 心智圖被重新產生（不是這裡的編輯）：清除復原紀錄與選取，並置中
  useEffect(() => {
    if (root === lastCommitted.current) return;
    lastCommitted.current = root;
    past.current = [];
    future.current = [];
    setSelectedId(null);
    setEditingId(null);
    requestAnimationFrame(() => void rf.fitView({ padding: 0.15, duration: 200 }));
  }, [root, rf]);

  const commit = useCallback(
    (next: MindNode) => {
      const cur = lastCommitted.current;
      if (next === cur) return;
      past.current = [...past.current.slice(-(HISTORY_LIMIT - 1)), cur];
      future.current = [];
      lastCommitted.current = next;
      setStore({ mindmap: next });
    },
    [setStore],
  );

  const undo = () => {
    const prev = past.current.pop();
    if (!prev) return;
    future.current.push(lastCommitted.current);
    lastCommitted.current = prev;
    setStore({ mindmap: prev });
    if (selectedId && !findNode(prev, selectedId)) setSelectedId(null);
    forceRender((n) => n + 1);
  };
  const redo = () => {
    const next = future.current.pop();
    if (!next) return;
    past.current.push(lastCommitted.current);
    lastCommitted.current = next;
    setStore({ mindmap: next });
    if (selectedId && !findNode(next, selectedId)) setSelectedId(null);
    forceRender((n) => n + 1);
  };

  // 節點實際高度（React Flow 量測）；文字換行比估計多時，排版用實際高度避免重疊
  const [heights, setHeights] = useState<ReadonlyMap<string, number>>(() => new Map());
  const placed = useMemo(() => layout(root, heights), [root, heights]);
  const placedById = useMemo(() => new Map(placed.map((p) => [p.node.id, p])), [placed]);
  const baseNodes = useMemo<MindFlowNode[]>(
    () =>
      placed.map((p) => ({
        id: p.node.id,
        type: 'mind',
        position: { x: p.x, y: p.y },
        data: { node: p.node, side: p.side, width: p.width, minHeight: estimateHeight(p.node), hidden: p.hidden },
        selected: p.node.id === selectedId,
        draggable: editingId !== p.node.id,
        selectable: false,
      })),
    [placed, selectedId, editingId],
  );
  const edges = useMemo<Edge[]>(
    () =>
      placed
        .filter((p) => p.parentId)
        .map((p) => ({
          id: `e-${p.node.id}`,
          source: p.parentId!,
          target: p.node.id,
          sourceHandle: p.side === 'left' ? 's-l' : 's-r',
          targetHandle: p.side === 'left' ? 't-r' : 't-l',
          type: 'default',
          focusable: false,
          style: { stroke: '#000', strokeWidth: p.depth === 1 ? 2.5 : p.depth === 2 ? 1.75 : 1.25 },
        })),
    [placed],
  );

  // React Flow 需要自己的 nodes 狀態（拖曳中、量測尺寸）；樹改變時重新同步
  // 同步時保留已量測的尺寸，否則 React Flow 會先把節點隱藏、重新量測（畫面閃爍，匯出也會是空白）
  const [nodes, setNodes] = useState<MindFlowNode[]>(baseNodes);
  useEffect(
    () =>
      setNodes((prev) => {
        const measured = new Map(prev.map((n) => [n.id, n.measured]));
        return baseNodes.map((n) => ({ ...n, measured: measured.get(n.id) }));
      }),
    [baseNodes],
  );
  const onNodesChange = useCallback((changes: NodeChange<MindFlowNode>[]) => {
    setNodes((ns) => applyNodeChanges(changes.filter((c) => c.type === 'position' || c.type === 'dimensions'), ns));
    const sized = changes.flatMap((c) => (c.type === 'dimensions' && c.dimensions ? [[c.id, Math.round(c.dimensions.height)] as const] : []));
    if (sized.length)
      setHeights((cur) => (sized.some(([id, h]) => Math.abs((cur.get(id) ?? -1) - h) > 1) ? new Map([...cur, ...sized]) : cur));
  }, []);

  // 拖曳時子孫節點一起移動；放開後寫回樹（主要分支拖過中心 → 換到另一側）
  const descendantsOf = (id: string) => {
    const n = findNode(root, id);
    return new Set(n ? allIds(n).slice(1) : []);
  };
  const onNodeDrag = (_: unknown, dragged: MindFlowNode) => {
    const base = placedById.get(dragged.id);
    if (!base) return;
    const dx = dragged.position.x - base.x;
    const dy = dragged.position.y - base.y;
    const desc = descendantsOf(dragged.id);
    setNodes((ns) =>
      ns.map((n) => {
        if (!desc.has(n.id)) return n;
        const p = placedById.get(n.id)!;
        return { ...n, position: { x: p.x + dx, y: p.y + dy } };
      }),
    );
  };
  const onNodeDragStop = (_: unknown, dragged: MindFlowNode) => {
    const base = placedById.get(dragged.id);
    if (!base) return;
    const dx = Math.round(dragged.position.x - base.x);
    const dy = Math.round(dragged.position.y - base.y);
    if (Math.abs(dx) < 2 && Math.abs(dy) < 2) {
      setNodes(baseNodes);
      return;
    }
    if (base.depth === 1) {
      const center = placedById.get(root.id)!;
      const cx = center.x + center.width / 2;
      const nodeCx = dragged.position.x + base.width / 2;
      const newSide = nodeCx < cx ? 'left' : 'right';
      if (newSide !== base.side) {
        commit(setSide(root, dragged.id, newSide));
        return;
      }
    }
    commit(moveBy(root, dragged.id, dx, dy));
  };

  const focusCanvas = () => wrapRef.current?.focus({ preventScroll: true });

  const actions = useMemo<MindActions>(
    () => ({
      editingId,
      startEdit: (id) => {
        setSelectedId(id);
        setEditingId(id);
      },
      commitEdit: (id, text) => {
        setEditingId((cur) => (cur === id ? null : cur));
        commit(setText(lastCommitted.current, id, text));
        focusCanvas();
      },
      cancelEdit: () => {
        setEditingId(null);
        focusCanvas();
      },
      toggle: (id) => commit(toggleCollapsed(lastCommitted.current, id)),
    }),
    [editingId, commit],
  );

  const selected = selectedId ? findNode(root, selectedId) : null;
  const canAddChild = !!selected && LEVEL_OF[selected.kind] < MAX_LEVEL;
  const canAddSibling = !!selected && selected.id !== root.id;
  const canConclude = !!selected && (selected.kind === 'detail' || selected.kind === 'conclusion');

  const add = (mode: 'child' | 'sibling') => {
    if (!selected) return;
    const [next, id] = mode === 'child' || selected.id === root.id ? addChild(root, selected.id) : addSibling(root, selected.id);
    if (!id) return;
    commit(next);
    setSelectedId(id);
    setEditingId(id);
  };
  const remove = () => {
    if (!selected || selected.id === root.id) return;
    const parent = findParent(root, selected.id);
    commit(removeNode(root, selected.id));
    setSelectedId(parent?.id ?? null);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (editingId) return;
    const mod = isMac ? e.metaKey : e.ctrlKey;
    if (mod && e.key.toLowerCase() === 'z') {
      e.preventDefault();
      if (e.shiftKey) redo();
      else undo();
      return;
    }
    if (mod && e.key.toLowerCase() === 'y') {
      e.preventDefault();
      redo();
      return;
    }
    if (e.key === 'Escape') {
      if (expanded) setExpanded(false);
      else setSelectedId(null);
      return;
    }
    if (!selected) return;
    if (e.key === 'Tab') {
      e.preventDefault();
      add('child');
    } else if (e.key === 'Enter') {
      e.preventDefault();
      add('sibling');
    } else if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault();
      remove();
    } else if (e.key === 'F2') {
      e.preventDefault();
      actions.startEdit(selected.id);
    }
  };

  const doExport = async (kind: SaveFileKind) => {
    const viewport = wrapRef.current?.querySelector<HTMLElement>('.react-flow__viewport');
    if (!viewport) return;
    setExporting(true);
    setNotice(null);
    const keepSelected = selectedId;
    setSelectedId(null); // 選取框不要出現在圖片中
    setEditingId(null);
    try {
      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      const bounds = getNodesBounds(rf.getNodes());
      const dataUrl = await renderMindMap(viewport, bounds, kind);
      const path = await saveImage(dataUrl, kind, exportFileName(mediaName));
      if (path) setNotice(`已儲存：${path}`);
    } catch (err) {
      setNotice(`匯出失敗：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setSelectedId(keepSelected);
      setExporting(false);
    }
  };

  const modKey = isMac ? '⌘' : 'Ctrl';

  return (
    <div
      className={cn(
        'flex flex-col gap-3',
        expanded && 'fixed inset-0 z-40 bg-background p-4',
      )}
    >
      <div role="toolbar" aria-label="心智圖工具" className="flex flex-wrap items-center gap-2">
        <ToolButton onClick={() => add('child')} disabled={!canAddChild} title="新增子節點（Tab）">＋ 子節點</ToolButton>
        <ToolButton onClick={() => add('sibling')} disabled={!canAddSibling} title="新增同層節點（Enter）">＋ 同層</ToolButton>
        <ToolButton onClick={() => selected && actions.startEdit(selected.id)} disabled={!selected} title="修改節點文字（也可以雙擊節點或按 F2）">改文字</ToolButton>
        <ToolButton onClick={remove} disabled={!canAddSibling} title="刪除節點與它的子節點（Delete）">刪除</ToolButton>
        <ToolButton onClick={() => selected && commit(toggleConclusion(root, selected.id))} disabled={!canConclude} title="把細節標為結論，或取消">
          {selected?.kind === 'conclusion' ? '取消結論' : '標為結論'}
        </ToolButton>
        {selected ? null : <span className="text-xs text-body-gray">先點選一個節點</span>}
        <Sep />
        <ToolButton onClick={undo} disabled={past.current.length === 0} title={`復原（${modKey}+Z）`}>復原</ToolButton>
        <ToolButton onClick={redo} disabled={future.current.length === 0} title={`重做（${modKey}+Shift+Z）`}>重做</ToolButton>
        <Sep />
        <ToolButton onClick={() => commit(setAllCollapsed(root, false))} title="展開所有節點">全部展開</ToolButton>
        <ToolButton onClick={() => commit(setAllCollapsed(root, true))} title="只顯示中心與主要分支">全部收合</ToolButton>
        <ToolButton
          onClick={() => {
            commit(resetLayout(root));
            requestAnimationFrame(() => void rf.fitView({ padding: 0.15, duration: 200 }));
          }}
          title="清除拖曳，恢復自動排列"
        >
          重新排列
        </ToolButton>
        <ToolButton onClick={() => setExpanded((v) => !v)} title={expanded ? '縮小（Esc）' : '放大到整個視窗'}>
          {expanded ? '縮小' : '放大'}
        </ToolButton>
        <Sep />
        <ToolButton onClick={() => void doExport('png')} disabled={exporting} title="匯出成 PNG 圖片">匯出 PNG</ToolButton>
        <ToolButton onClick={() => void doExport('svg')} disabled={exporting} title="匯出成 SVG 向量圖">匯出 SVG</ToolButton>
      </div>

      <MindActionsContext.Provider value={actions}>
        <div
          ref={wrapRef}
          tabIndex={0}
          onKeyDown={onKeyDown}
          aria-label="心智圖。點選節點後可用 Tab 新增子節點、Enter 新增同層、F2 編輯、Delete 刪除。"
          className={cn(
            'mm-canvas overflow-hidden rounded-lg border border-chip focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground',
            expanded ? 'min-h-0 flex-1' : 'h-[600px]',
          )}
        >
          <ReactFlow<MindFlowNode, Edge>
            nodes={nodes}
            edges={edges}
            nodeTypes={NODE_TYPES}
            onNodesChange={onNodesChange}
            onNodeClick={(_, n) => {
              setSelectedId(n.id);
              focusCanvas();
            }}
            onNodeDragStart={(_, n) => {
              setSelectedId(n.id);
              focusCanvas();
            }}
            onNodeDrag={onNodeDrag}
            onNodeDragStop={onNodeDragStop}
            onPaneClick={() => {
              setSelectedId(null);
              focusCanvas();
            }}
            nodesConnectable={false}
            elementsSelectable={false}
            deleteKeyCode={null}
            selectionKeyCode={null}
            multiSelectionKeyCode={null}
            zoomOnDoubleClick={false}
            disableKeyboardA11y
            minZoom={0.2}
            maxZoom={2}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1.5} color="#e2e2e2" />
            <Controls showInteractive={false} position="bottom-right" />
          </ReactFlow>
        </div>
      </MindActionsContext.Provider>

      <p className="text-xs text-body-gray" aria-live="polite">
        {notice ?? '拖曳節點可移動（子節點會跟著）；把主要分支拖到另一側可換邊。雙擊編輯文字，點時間跳到逐字稿。編輯只保留在這次開啟的程式中。'}
      </p>
    </div>
  );
}

/** 心智圖（PROJECT_SPEC §4-F、Phase 07）：由摘要時勾選「心智圖」產生，或用「重新產生心智圖」單獨產生。 */
export function MindMapCard() {
  const mindmap = useSessionStore((s) => s.mindmap);
  const transcript = useSessionStore((s) => s.transcript);
  const s = useSessionStore((st) => st.summarizing);
  const imp = useSessionStore((st) => st.import);
  const [confirming, setConfirming] = useState(false);

  const ready = !!transcript && transcript.segments.length > 0;
  const busy = s.status === 'starting' || s.status === 'queued' || s.status === 'running';
  const mediaName = imp.status === 'ready' ? imp.info.filename : '心智圖';

  const regenerate = () => {
    setConfirming(false);
    void startMindmap();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>心智圖</CardTitle>
        <CardDescription>從中心主題向左右展開；節點可以拖曳、編輯、新增或刪除，也能匯出成 PNG 或 SVG。</CardDescription>
      </CardHeader>
      <CardContent>
        {mindmap ? (
          <ReactFlowProvider>
            <MindMapEditor root={mindmap} mediaName={mediaName} />
          </ReactFlowProvider>
        ) : busy ? (
          <div className="flex items-end gap-4">
            <Mono animation="video" scale={2} />
            <p className="text-sm text-body-gray">正在整理中，進度請看上方「摘要」。有勾選「心智圖」時，完成後會顯示在這裡。</p>
          </div>
        ) : (
          <p className="text-sm text-body-gray">
            {ready ? '產生摘要時勾選「心智圖」，或直接按下方的「產生心智圖」。' : '請先完成「語音辨識」，再產生心智圖。'}
          </p>
        )}
      </CardContent>
      <CardFooter className="flex flex-wrap items-center gap-3">
        {confirming ? (
          <>
            <span className="text-sm font-medium">重新產生會取代目前的心智圖（包含你的編輯），確定嗎？</span>
            <Button onClick={regenerate}>確定重新產生</Button>
            <Button variant="secondary" onClick={() => setConfirming(false)}>取消</Button>
          </>
        ) : (
          <Button
            variant={mindmap ? 'secondary' : 'default'}
            disabled={!ready || busy}
            onClick={() => (mindmap ? setConfirming(true) : regenerate())}
          >
            {mindmap ? '重新產生心智圖' : '產生心智圖'}
          </Button>
        )}
        {busy && mindmap ? <span className="text-sm text-body-gray">處理中，進度請看上方「摘要」。</span> : null}
      </CardFooter>
    </Card>
  );
}
