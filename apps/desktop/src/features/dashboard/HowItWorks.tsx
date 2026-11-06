const STEPS = [
  { title: '匯入影音', body: '拖曳影片或錄音，或貼上 YouTube 網址。' },
  { title: '語音辨識', body: '本機 AI 產生帶時間戳記的逐字稿，可直接編輯。' },
  { title: '摘要與心智圖', body: '整理重點與行動事項，畫成可編輯的心智圖。' },
  { title: '匯出成果', body: '存成 TXT、SRT、VTT、JSON、Markdown、PNG 或 SVG。' },
];

/** The core workflow is a real sequence, so numbered markers are appropriate here. */
export function HowItWorks({ className }: { className?: string }) {
  return (
    <section aria-labelledby="how-heading" className={className}>
      <h2 id="how-heading" className="text-h2">使用方式</h2>
      <ol className="mt-6 grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
        {STEPS.map((s, i) => (
          <li key={s.title} className="flex flex-col gap-3">
            <span className="flex size-8 items-center justify-center rounded-full bg-foreground text-sm font-bold text-background">
              {i + 1}
            </span>
            <h3 className="text-h3">{s.title}</h3>
            <p className="text-sm text-body-gray">{s.body}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
