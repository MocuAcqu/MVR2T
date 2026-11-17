import { useEffect, useRef, useState } from 'react';
import type { MediaInfo } from '@shared/types/api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { getBackendConnection, mediaFileUrl } from '@/services/api';
import { useSessionStore } from '@/stores/sessionStore';
import { registerPlayer, usePlayerStore } from './playerStore';
import { t } from '@/i18n';

/**
 * 工作區播放器：播放本次 Session 的原始影音（後端支援拖曳進度的 Range 請求）。
 * Chromium 無法播放的格式（例如部分 MKV／MOV 的編碼）→ 抽取音訊後改播 16 kHz 音訊。
 */
export function PlayerCard({ info }: { info: MediaInfo }) {
  const sessionId = useSessionStore((s) => s.sessionId);
  const extracted = useSessionStore((s) => s.extraction.status === 'completed');
  const [kind, setKind] = useState<'original' | 'audio'>('original');
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const ref = useRef<HTMLMediaElement | null>(null);
  const showVideo = info.has_video && kind === 'original';

  useEffect(() => {
    setKind('original');
    setFailed(false);
  }, [info.media_id]);

  useEffect(() => {
    let alive = true;
    setSrc(null);
    if (!sessionId) return;
    void getBackendConnection().then((conn) => {
      if (alive && conn) setSrc(mediaFileUrl(conn, sessionId, info.media_id, kind));
    });
    return () => {
      alive = false;
    };
  }, [sessionId, info.media_id, kind]);

  useEffect(() => () => registerPlayer(null), []);
  // 原始格式無法播放、之後才完成抽取：改播抽取的音訊
  useEffect(() => {
    if (failed && extracted && kind === 'original') {
      setFailed(false);
      setKind('audio');
    }
  }, [failed, extracted, kind]);

  const attach = (el: HTMLMediaElement | null) => {
    ref.current = el;
    registerPlayer(el);
  };
  const set = usePlayerStore.getState().set;
  const events = {
    onLoadedMetadata: () => {
      setFailed(false);
      set({ ready: true });
    },
    onTimeUpdate: (e: React.SyntheticEvent<HTMLMediaElement>) => set({ time: e.currentTarget.currentTime }),
    onPlay: () => set({ playing: true }),
    onPause: () => set({ playing: false }),
    onError: () => {
      set({ ready: false });
      if (kind === 'original' && extracted) setKind('audio');
      else setFailed(true);
    },
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('播放器')}</CardTitle>
        <CardDescription>{t('點逐字稿的時間可以從那一句開始播放。')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {src ? (
          showVideo ? (
            <video
              key={src}
              ref={attach}
              src={src}
              controls
              preload="metadata"
              className="max-h-[360px] w-full rounded-lg bg-foreground"
              {...events}
            />
          ) : (
            <audio key={src} ref={attach} src={src} controls preload="metadata" className="w-full" {...events} />
          )
        ) : null}
        {kind === 'audio' ? <p className="text-xs text-body-gray">{t('原始檔案的格式無法在程式內播放，改為播放抽取的音訊。')}</p> : null}
        {failed ? (
          <p role="status" className="text-sm text-body-gray">
            {extracted ? t('無法播放這個檔案。') : t('這個檔案的格式無法在程式內直接播放。完成「抽取音訊」後可以播放音訊。')}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
