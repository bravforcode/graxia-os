/* ═══════════════════════════════════════════════════════
   News Feed — Regime-tagged news items
   ═══════════════════════════════════════════════════════ */

import type { NewsItem } from '../types';

interface NewsFeedProps {
  news: NewsItem[];
}

const REGIME_ICON: Record<string, string> = {
  NORMAL: 'normal',
  HIGH_UNCERTAINTY: 'warning',
  CRISIS: 'crisis',
};

export function NewsFeed({ news }: NewsFeedProps) {
  const recent = news.slice(-5).reverse();

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">News</span>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)' }}>
          {news.length} items
        </span>
      </div>

      {recent.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">—</div>
          <span>No news data</span>
        </div>
      ) : (
        <div className="news-list">
          {recent.map((item, i) => (
            <div className="news-item" key={`${item.timestamp}-${i}`}>
              <span className={`news-icon ${REGIME_ICON[item.regime] ?? ''}`} />
              <div className="news-content">
                <div>
                  <span className="news-regime">{item.regime}</span>
                  <span className="news-time">
                    {item.confidence > 0 ? `${(item.confidence * 100).toFixed(0)}%` : ''} · {item.timestamp.slice(11, 16)}
                  </span>
                </div>
                {item.headlines?.slice(0, 2).map((h, j) => (
                  <div className="news-headline" key={j}>
                    {h.title}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
