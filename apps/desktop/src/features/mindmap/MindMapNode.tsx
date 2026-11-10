import { createContext, memo, useContext, useEffect, useRef, useState } from 'react';
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import { formatDuration } from '@/lib/format';
import { cn } from '@/lib/utils';
import { revealTranscriptLine } from '@/features/workspace/TranscriptCard';
import type { MindNode } from './model';

export interface MindNodeData extends Record<string, unknown> {
  node: MindNode;
  side: 'left' | 'right' | 'center';
  width: number;
  minHeight: number;
  hidden: number;
}
export type MindFlowNode = Node<MindNodeData, 'mind'>;

/** 節點用的動作（放在 context，節點資料改變時不必重建這些函式）。 */
export interface MindActions {
  editingId: string | null;
  startEdit: (id: string) => void;
  commitEdit: (id: string, text: string) => void;
  cancelEdit: () => void;
  toggle: (id: string) => void;
}
export const MindActionsContext = createContext<MindActions | null>(null);

/** 不出現在匯出圖片中的元素 */
export const NO_EXPORT = 'mm-noexport';

const KIND_STYLE: Record<MindNode['kind'], string> = {
  central: 'bg-foreground text-background text-lg font-bold rounded-xl px-4 py-4 text-center',
  main: 'bg-background border-2 border-foreground text-[15px] font-bold rounded-lg px-3.5 py-3',
  sub: 'bg-chip text-sm font-medium rounded-lg px-3.5 py-2.5',
  detail: 'bg-background border border-hover-gray text-[13px] rounded-md px-3.5 py-2',
  conclusion: 'bg-background border-2 border-foreground text-[13px] font-medium rounded-md px-3.5 py-2',
};

const handleClass = '!h-2 !w-2 !min-h-0 !min-w-0 !border-0 !bg-transparent';

function InlineEditor({ id, text }: { id: string; text: string }) {
  const actions = useContext(MindActionsContext)!;
  const [value, setValue] = useState(text);
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    // 新節點在 React Flow 量測完尺寸前是隱藏的，無法取得焦點：重試幾個畫面
    let tries = 0;
    let raf = 0;
    const focus = () => {
      const el = ref.current;
      if (!el) return;
      el.focus();
      if (document.activeElement === el) el.select();
      else if (tries++ < 20) raf = requestAnimationFrame(focus);
    };
    focus();
    return () => cancelAnimationFrame(raf);
  }, []);
  return (
    <textarea
      ref={ref}
      aria-label="節點文字"
      value={value}
      rows={Math.min(4, Math.max(1, Math.ceil(value.length / 12)))}
      maxLength={80}
      onChange={(e) => setValue(e.target.value.replace(/\n/g, ''))}
      onKeyDown={(e) => {
        e.stopPropagation(); // 不觸發心智圖的快捷鍵
        if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
          e.preventDefault();
          actions.commitEdit(id, value);
        } else if (e.key === 'Escape') {
          e.preventDefault();
          actions.cancelEdit();
        }
      }}
      onBlur={() => actions.commitEdit(id, value)}
      className="nodrag nopan nowheel w-full resize-none bg-transparent leading-snug outline-none"
    />
  );
}

/** 心智圖節點：依種類顯示不同樣式；時間標籤點一下跳到逐字稿；外側的按鈕收合／展開子節點。 */
export const MindNodeView = memo(function MindNodeView({ data, selected }: NodeProps<MindFlowNode>) {
  const actions = useContext(MindActionsContext)!;
  const { node, side, width, minHeight, hidden } = data;
  const editing = actions.editingId === node.id;
  const hasChildren = node.children.length > 0;
  const outer = side === 'left' ? 'left' : 'right';
  const dark = node.kind === 'central';

  return (
    <div
      style={{ width, minHeight }}
      onDoubleClick={() => actions.startEdit(node.id)}
      className={cn(
        'relative flex flex-col justify-center gap-1 break-words leading-snug shadow-sm',
        KIND_STYLE[node.kind],
        selected && 'outline outline-2 outline-offset-2 outline-foreground',
      )}
    >
      {/* 兩側都有連接點：中心的左右分支、以及各分支往外連 */}
      <Handle type="target" position={Position.Left} id="t-l" className={handleClass} isConnectable={false} />
      <Handle type="target" position={Position.Right} id="t-r" className={handleClass} isConnectable={false} />
      <Handle type="source" position={Position.Left} id="s-l" className={handleClass} isConnectable={false} />
      <Handle type="source" position={Position.Right} id="s-r" className={handleClass} isConnectable={false} />

      {node.kind === 'conclusion' ? (
        <span className="w-fit rounded-pill bg-foreground px-2 py-px text-[11px] font-bold text-background">結論</span>
      ) : null}
      {editing ? <InlineEditor id={node.id} text={node.text} /> : <span>{node.text}</span>}
      {node.time && node.refs.length > 0 && node.kind !== 'central' ? (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            revealTranscriptLine(node.refs[0]);
          }}
          onDoubleClick={(e) => e.stopPropagation()}
          title="跳到逐字稿中的這一句"
          className={cn(
            'nodrag w-fit rounded-pill px-2 py-px text-[11px] font-normal tabular-nums',
            dark ? 'bg-body-gray text-background' : 'bg-chip text-body-gray hover:bg-hover-gray',
            node.kind === 'sub' && 'bg-background',
          )}
        >
          {formatDuration(Math.floor(node.time.start))}
        </button>
      ) : null}

      {hasChildren && node.kind !== 'central' ? (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            actions.toggle(node.id);
          }}
          onDoubleClick={(e) => e.stopPropagation()}
          aria-label={hidden ? `展開 ${hidden} 個子節點` : '收合子節點'}
          title={hidden ? `展開（${hidden}）` : '收合'}
          className={cn(
            NO_EXPORT,
            'nodrag absolute top-1/2 flex h-5 min-w-5 -translate-y-1/2 items-center justify-center rounded-pill border border-foreground bg-background px-1 text-[11px] font-bold leading-none text-foreground hover:bg-chip',
            outer === 'right' ? 'right-0 translate-x-[calc(100%+6px)]' : 'left-0 -translate-x-[calc(100%+6px)]',
          )}
        >
          {hidden ? hidden : '−'}
        </button>
      ) : null}
    </div>
  );
});
