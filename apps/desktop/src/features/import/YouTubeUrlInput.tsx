import { AlertCircle, Link } from 'lucide-react';
import { useEffect, useId, useState, type FormEvent } from 'react';
import type { SubtitleChoice } from '@shared/types/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import {
  acceptYouTubeNotice,
  cancelDownload,
  cancelProbe,
  downloadVideo,
  loadYouTubeStatus,
  probeVideo,
  setYouTubeUrl,
  useYouTubeStore,
} from '@/features/youtube/youtubeController';
import { formatBytes, formatDuration, formatPercent } from '@/lib/format';
import { useUiStore } from '@/stores/uiStore';
import { t } from '@/i18n';

/** 第一次使用時的說明（使用者決定 2026-11-15）：只用於自己擁有或已獲授權的影片。 */
function Notice() {
  const checkId = useId();
  const [checked, setChecked] = useState(false);
  return (
    <div className="flex flex-col gap-3 rounded-lg bg-chip p-4 text-sm">
      <p className="font-medium">{t('使用 YouTube 連結之前')}</p>
      <ul className="list-inside list-disc space-y-1 text-body-gray">
        <li>{t('YouTube 的服務條款原則上不允許下載影片內容，除非 YouTube 提供下載功能或取得權利人許可。')}</li>
        <li>{t('請只用於你自己上傳、創用 CC 授權，或已取得權利人同意的影片。是否符合條款與著作權規定由使用者自行負責。')}</li>
        <li>{t('只下載音訊，存放在本次工作階段的暫存，關閉程式或更換檔案時刪除。不支援登入、會員限定、私人影片、直播與播放清單。')}</li>
        <li>{t('下載需要網路；之後的語音辨識與摘要仍在這台電腦上進行。')}</li>
      </ul>
      <label htmlFor={checkId} className="flex items-start gap-2">
        <input id={checkId} type="checkbox" className="mt-1 size-4 accent-foreground" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
        <span>{t('我了解，只會用於自己擁有或已獲授權的影片。')}</span>
      </label>
      <div>
        <Button size="sm" disabled={!checked} onClick={() => void acceptYouTubeNotice()}>{t('同意並繼續')}</Button>
      </div>
    </div>
  );
}

/** YouTube 連結：讀取影片資訊 → 只下載音訊（＋可選的作者字幕）→ 與本機檔案相同的流程。 */
export function YouTubeUrlInput() {
  const inputId = useId();
  const messageId = useId();
  const selectId = useId();
  const s = useYouTubeStore();
  const setPage = useUiStore((st) => st.setPage);
  const [mode, setMode] = useState<'asr' | 'subtitles'>('asr');
  const [lang, setLang] = useState<string>('');

  useEffect(() => {
    void loadYouTubeStatus();
  }, []);
  // 換影片時：有作者字幕就預設選第一個（仍預設語音辨識）
  useEffect(() => {
    setMode('asr');
    setLang(s.video?.subtitles[0]?.lang ?? '');
  }, [s.video]);

  const busy = s.phase === 'starting' || s.phase === 'downloading';
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void probeVideo();
  };

  const header = (
    <div className="flex items-center gap-2">
      <Link className="size-5" aria-hidden="true" />
      <span className="text-sm font-medium">{t('YouTube 連結')}</span>
    </div>
  );

  if (s.component && !s.component.installed) {
    return (
      <div className="flex flex-col gap-2">
        {header}
        <p className="text-sm text-body-gray">
          {s.component.supported
            ? t('需要先下載「YouTube 下載元件」（約 20 MB，需要網路）。下載後貼上影片網址，就能只下載音訊並轉成逐字稿。')
            : t('這個作業系統目前不支援 YouTube 下載。')}
        </p>
        {s.component.supported ? (
          <div>
            <Button variant="secondary" size="sm" onClick={() => setPage('models')}>{t('前往模型管理')}</Button>
          </div>
        ) : null}
      </div>
    );
  }

  if (s.noticeAccepted === false) {
    return (
      <div className="flex flex-col gap-2">
        {header}
        <Notice />
      </div>
    );
  }

  const video = s.video;
  const subtitle: SubtitleChoice | null =
    mode === 'subtitles' && video ? (video.subtitles.find((x) => x.lang === lang) ?? null) : null;

  return (
    <div className="flex flex-col gap-3">
      <form onSubmit={onSubmit} className="flex flex-col gap-2" noValidate>
        <label htmlFor={inputId} className="flex items-center gap-2 text-sm font-medium">
          <Link className="size-5" aria-hidden="true" />
          {t('YouTube 網址')}
        </label>
        <div className="flex gap-2">
          <Input
            id={inputId}
            type="url"
            inputMode="url"
            placeholder="https://www.youtube.com/watch?v=..."
            value={s.url}
            disabled={busy}
            onChange={(e) => setYouTubeUrl(e.target.value)}
            aria-invalid={s.phase === 'error'}
            aria-describedby={s.message ? messageId : undefined}
          />
          {s.phase === 'probing' ? (
            <Button type="button" variant="secondary" className="shrink-0" onClick={cancelProbe}>{t('取消')}</Button>
          ) : (
            <Button type="submit" variant="secondary" className="shrink-0" disabled={busy}>{t('讀取影片')}</Button>
          )}
        </div>
      </form>

      {s.phase === 'probing' ? (
        <div className="flex flex-col gap-2" aria-live="polite">
          <p className="text-sm text-body-gray">{t('正在讀取影片資訊…（需要網路，約數秒到半分鐘）')}</p>
          <Progress label={t('讀取影片資訊')} indeterminate />
        </div>
      ) : null}

      {video && (s.phase === 'ready' || busy) ? (
        <div className="flex flex-col gap-3 rounded-lg bg-chip p-4">
          <div className="min-w-0">
            <p className="font-medium" title={video.title}>{video.title}</p>
            <p className="text-sm text-body-gray">
              {[video.channel, video.duration ? t('長度 {0}', formatDuration(video.duration)) : null, video.audio_size ? t('音訊約 {0}', formatBytes(video.audio_size)) : null]
                .filter(Boolean)
                .join(t('，'))}
            </p>
          </div>

          {busy ? (
            <div className="flex flex-col gap-2" aria-live="polite">
              <div className="flex justify-between gap-3 text-sm">
                <span className="font-medium">
                  {s.stage || t('準備中')}
                  {s.detail ? <span className="ml-2 font-normal text-body-gray">{s.detail}</span> : null}
                </span>
                <span className="tabular-nums text-body-gray">{formatPercent(s.progress)}</span>
              </div>
              <Progress label={t('YouTube 下載進度')} value={s.progress} indeterminate={s.phase === 'starting' || s.progress === 0} />
              <div>
                <Button variant="secondary" size="sm" onClick={() => void cancelDownload()} disabled={s.phase === 'starting'}>{t('取消')}</Button>
              </div>
            </div>
          ) : (
            <>
              <fieldset className="flex flex-col gap-2 text-sm">
                <legend className="sr-only">{t('逐字稿的來源')}</legend>
                <label className="flex items-start gap-2">
                  <input type="radio" name="yt-mode" className="mt-1 accent-foreground" checked={mode === 'asr'} onChange={() => setMode('asr')} />
                  <span>{t('在這台電腦上做語音辨識（有精確時間戳記，需要一些時間）')}</span>
                </label>
                {video.subtitles.length > 0 ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <label className="flex items-start gap-2">
                      <input type="radio" name="yt-mode" className="mt-1 accent-foreground" checked={mode === 'subtitles'} onChange={() => setMode('subtitles')} />
                      <span>{t('使用影片作者提供的字幕（不必辨識，較快）：')}</span>
                    </label>
                    <label htmlFor={selectId} className="sr-only">{t('字幕語言')}</label>
                    <select
                      id={selectId}
                      value={lang}
                      onChange={(e) => {
                        setLang(e.target.value);
                        setMode('subtitles');
                      }}
                      className="h-9 rounded-pill border border-foreground bg-background px-3 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2"
                    >
                      {video.subtitles.map((x) => (
                        <option key={x.lang} value={x.lang}>{x.name}</option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <p className="text-xs text-body-gray">{t('這部影片沒有作者提供的字幕，下載後請用語音辨識。')}</p>
                )}
              </fieldset>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => void downloadVideo(subtitle)}>{t('下載音訊')}</Button>
              </div>
            </>
          )}
        </div>
      ) : null}

      {s.message && !busy ? (
        <p id={messageId} role={s.phase === 'error' ? 'alert' : 'status'} className="flex items-start gap-2 text-sm">
          {s.phase === 'error' ? <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" /> : null}
          <span>{s.message}</span>
        </p>
      ) : null}
      {s.component?.update_available ? (
        <p className="text-xs text-body-gray">{t('YouTube 下載元件有新版本（{0}），可以到「模型管理」更新。', s.component.latest_version)}</p>
      ) : null}
    </div>
  );
}
