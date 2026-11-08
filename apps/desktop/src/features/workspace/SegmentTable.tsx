import type { AudioSegment } from '@shared/types/api';
import { formatTimestamp } from '@/lib/format';

const BOUNDARY: Record<AudioSegment['boundary'], string> = {
  silence: '停頓處',
  hard: '硬切（重疊）',
  end: '結尾',
};

/** 切段結果。時間都是「原始檔案」的時間軸，之後 ASR 的時間戳記會以此對回原始影音。 */
export function SegmentTable({ segments }: { segments: AudioSegment[] }) {
  return (
    <div className="max-h-96 overflow-auto rounded-lg border border-chip">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">音訊切段列表</caption>
        <thead className="sticky top-0 bg-background">
          <tr className="text-left text-body-gray">
            <th scope="col" className="px-4 py-2 font-medium">段</th>
            <th scope="col" className="px-4 py-2 font-medium">開始</th>
            <th scope="col" className="px-4 py-2 font-medium">結束</th>
            <th scope="col" className="px-4 py-2 text-right font-medium">長度</th>
            <th scope="col" className="px-4 py-2 font-medium">切點</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {segments.map((s) => (
            <tr key={s.index} className="border-t border-chip">
              <td className="px-4 py-2 font-medium">{s.index + 1}</td>
              <td className="px-4 py-2">{formatTimestamp(s.start)}</td>
              <td className="px-4 py-2">{formatTimestamp(s.end)}</td>
              <td className="px-4 py-2 text-right">{s.duration.toFixed(1)} 秒</td>
              <td className="px-4 py-2 text-body-gray">{BOUNDARY[s.boundary]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
