import { useCallback, useEffect, useId, useState } from 'react';
import type { BackendSettings, StorageInfo } from '@shared/types/api';
import type { UiPrefs } from '@shared/types/ipc';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { useSystemStatus } from '@/hooks/useSystemStatus';
import { formatBytes } from '@/lib/format';
import { cn } from '@/lib/utils';
import { cleanupStorage, getBackendConnection, getBackendSettings, getStorageInfo, putBackendSettings } from '@/services/api';
import { setUiPrefs, useUiPrefs } from './uiPrefs';

const bridge = () => (typeof window !== 'undefined' ? window.mvr2t : undefined);

async function conn() {
  const c = await getBackendConnection();
  if (!c) throw new Error('本機後端尚未連線。');
  return c;
}

const ASR_LANGUAGES: { value: UiPrefs['asrLanguage']; label: string }[] = [
  { value: 'auto', label: '自動偵測' },
  { value: 'Chinese', label: '中文' },
  { value: 'English', label: '英文' },
  { value: 'Cantonese', label: '粵語' },
  { value: 'Japanese', label: '日文' },
  { value: 'Korean', label: '韓文' },
];

/** 一組單選項目（radio），黑白設計規範的樣式 */
function Choice<T extends string>({
  legend,
  value,
  options,
  onChange,
  disabled,
}: {
  legend: string;
  value: T;
  options: { value: T; label: string; hint: string }[];
  onChange: (v: T) => void;
  disabled?: boolean;
}) {
  const name = useId();
  return (
    <fieldset className="flex flex-col gap-2" disabled={disabled}>
      <legend className="mb-1 text-sm font-medium">{legend}</legend>
      {options.map((o) => (
        <label
          key={o.value}
          className={cn(
            'flex cursor-pointer items-start gap-3 rounded-lg border px-4 py-3 text-sm',
            value === o.value ? 'border-foreground' : 'border-chip',
          )}
        >
          <input
            type="radio"
            name={name}
            className="mt-1 accent-foreground"
            checked={value === o.value}
            onChange={() => onChange(o.value)}
          />
          <span className="flex flex-col gap-0.5">
            <span className="font-medium">{o.label}</span>
            <span className="text-xs text-body-gray">{o.hint}</span>
          </span>
        </label>
      ))}
    </fieldset>
  );
}

/** 語言與預設模型（規格 §12.4） */
export function RecognitionSettings() {
  const selectId = useId();
  const asrLanguage = useUiPrefs((p) => p.asrLanguage);
  const { models } = useSystemStatus();
  const packages = models.status === 'done' ? models.data.packages.filter((p) => p.id !== 'llm_gpu') : [];
  return (
    <Card>
      <CardHeader>
        <CardTitle>語音辨識與模型</CardTitle>
        <CardDescription>工作區「逐字稿」會預先選好這個語言；每次辨識前仍可以改。</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={selectId} className="text-sm font-medium">預設辨識語言</label>
          <select
            id={selectId}
            value={asrLanguage}
            onChange={(e) => void setUiPrefs({ asrLanguage: e.target.value as UiPrefs['asrLanguage'] })}
            className="h-11 rounded-pill border border-foreground bg-background px-4 text-base font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2"
          >
            {ASR_LANGUAGES.map((l) => (
              <option key={l.value} value={l.value}>{l.label}</option>
            ))}
          </select>
          <p className="text-xs text-body-gray">確定影片的語言時直接指定，比自動偵測更準確；混合多種語言時用自動偵測。</p>
        </div>
        <div className="flex flex-col gap-1.5">
          <p className="text-sm font-medium">預設模型</p>
          <ul className="flex flex-col text-sm">
            {packages.map((p) => (
              <li key={p.id} className="flex justify-between gap-4 border-t border-chip py-2.5">
                <span className="text-body-gray">{p.name}</span>
                <span className="text-right font-medium">{p.models.map((m) => m.display_name).join(' ＋ ')}</span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-body-gray">目前每項功能各有一個經過驗證的模型；下載、刪除與更新請到「模型管理」。</p>
        </div>
      </CardContent>
    </Card>
  );
}

/** 推論裝置與記憶體使用偏好（規格 §12.4），存在後端的 settings.json，下次辨識或摘要時生效。 */
export function ComputeSettings() {
  const [value, setValue] = useState<BackendSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    void conn()
      .then(getBackendSettings)
      .then(setValue)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const update = async (patch: Partial<BackendSettings>) => {
    if (!value) return;
    setError(null);
    setSaved(false);
    try {
      setValue(await putBackendSettings(await conn(), { ...value, ...patch }));
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>推論裝置與記憶體</CardTitle>
        <CardDescription>下次開始語音辨識或產生摘要時生效。「模型管理 → 這台電腦」會顯示實際使用的裝置。</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {!value && !error ? <p className="text-sm text-body-gray">讀取中…</p> : null}
        {value ? (
          <>
            <Choice
              legend="推論裝置"
              value={value.device}
              onChange={(device) => void update({ device })}
              options={[
                { value: 'auto', label: '自動（建議）', hint: '有可用的 NVIDIA 顯示卡（或 Apple Silicon）時，摘要使用 GPU；其他情況用 CPU。' },
                { value: 'cpu', label: '一律使用 CPU', hint: 'GPU 驅動程式不穩定、或想讓顯示卡留給其他程式時使用。語音辨識本來就使用 CPU。' },
              ]}
            />
            <Choice
              legend="記憶體使用"
              value={value.memory}
              onChange={(memory) => void update({ memory })}
              options={[
                { value: 'standard', label: '標準', hint: '可用記憶體不足時仍會自動降級並提醒。' },
                {
                  value: 'low',
                  label: '省記憶體',
                  hint: '摘要使用較短的 context（長逐字稿會分成較多段，時間稍長），語音辨識一次只處理一段。適合可用記憶體少於 4 GB 的電腦。',
                },
              ]}
            />
          </>
        ) : null}
        {saved ? <p role="status" className="text-sm text-body-gray">已儲存。</p> : null}
        {error ? <p role="alert" className="text-sm font-medium">{error}</p> : null}
      </CardContent>
    </Card>
  );
}

/** 暫存清理（規格 §12.4） */
export function StorageSettings() {
  const [info, setInfo] = useState<StorageInfo | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    try {
      setInfo(await getStorageInfo(await conn()));
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    }
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);

  const cleanable = info ? info.stale_bytes + info.cache_bytes : 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle>暫存檔案</CardTitle>
        <CardDescription>匯入的影音與抽取的音訊只存在本次工作階段，換檔案或關閉程式時自動刪除。</CardDescription>
      </CardHeader>
      <CardContent>
        {info ? (
          <dl className="text-sm">
            {[
              ['本次工作階段', formatBytes(info.current_session_bytes)],
              ['其他工作階段留下的暫存', formatBytes(info.stale_bytes)],
              ['YouTube 下載元件的快取', formatBytes(info.cache_bytes)],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 border-t border-chip py-2.5">
                <dt className="text-body-gray">{k}</dt>
                <dd className="font-medium tabular-nums">{v}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="text-sm text-body-gray">讀取中…</p>
        )}
        {message ? <p role="status" className="mt-3 text-sm">{message}</p> : null}
      </CardContent>
      <CardFooter className="gap-2">
        <Button
          variant="secondary"
          disabled={busy || !info || cleanable === 0}
          onClick={() => {
            setBusy(true);
            setMessage(null);
            void conn()
              .then(cleanupStorage)
              .then((r) => setMessage(`已清除 ${formatBytes(r.freed_bytes)}。`))
              .catch((e: unknown) => setMessage(e instanceof Error ? e.message : String(e)))
              .finally(() => {
                setBusy(false);
                void refresh();
              });
          }}
        >
          清除暫存{cleanable ? `（${formatBytes(cleanable)}）` : ''}
        </Button>
        <Button variant="ghost" onClick={() => void refresh()} disabled={busy}>重新計算</Button>
      </CardFooter>
    </Card>
  );
}

/** 關於（規格 §12.4） */
export function AboutCard() {
  const { app } = useSystemStatus();
  const [dataDir, setDataDir] = useState<string | null>(null);
  useEffect(() => {
    void conn()
      .then(getStorageInfo)
      .then((s) => setDataDir(s.data_dir))
      .catch(() => undefined);
  }, []);
  const b = bridge();
  return (
    <Card>
      <CardHeader>
        <CardTitle>關於 MVR2T</CardTitle>
        <CardDescription>Local Media Studio：在你的電腦上把影片與錄音轉成逐字稿、摘要與心智圖。所有處理都在本機完成，不保存處理歷史。</CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="text-sm">
          <div className="flex justify-between gap-4 border-t border-chip py-2.5">
            <dt className="text-body-gray">版本</dt>
            <dd className="font-medium tabular-nums">{app.status === 'electron' ? app.info.version : '開發預覽'}</dd>
          </div>
          {dataDir ? (
            <div className="flex justify-between gap-4 border-t border-chip py-2.5">
              <dt className="shrink-0 text-body-gray">資料夾（模型、設定）</dt>
              <dd className="min-w-0 break-all text-right font-medium">{dataDir}</dd>
            </div>
          ) : null}
        </dl>
      </CardContent>
      {b ? (
        <CardFooter className="flex-wrap gap-2">
          <Button variant="secondary" onClick={() => void b.openAppLocation('data')}>開啟資料夾</Button>
          <Button variant="secondary" onClick={() => void b.openAppLocation('notices')}>第三方授權</Button>
        </CardFooter>
      ) : null}
    </Card>
  );
}
