import { useState } from 'react'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import {
  Activity,
  FileText,
  MousePointerClick,
  DollarSign,
  Eye,
  CheckCircle,
  XCircle,
  Clock,
  X,
  AlertTriangle,
} from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────────────

interface Article {
  id: string
  title: string
  slug: string
  site: 'site_a' | 'site_b'
  language: 'en' | 'th'
  content_type: string
  status: string
  target_keyword: string | null
  meta_description: string | null
  word_count: number | null
  body: string
  created_at: string
  published_at: string | null
  affiliate_programs_used: string[]
}

interface ArticleList {
  total: number
  items: Article[]
}

interface Stats {
  published_articles: number
  pending_review: number
  traffic_30d: number
  clicks_30d: number
  revenue_30d: number
}

// ─── API helpers ─────────────────────────────────────────────────────────────

const API = '/api/v1/content'

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

// ─── Preview Modal ────────────────────────────────────────────────────────────

function ArticlePreviewModal({
  article,
  onClose,
  onApprove,
  onReject,
}: {
  article: Article
  onClose: () => void
  onApprove: () => void
  onReject: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 pt-16 backdrop-blur-sm">
      <div className="relative w-full max-w-3xl rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-gray-900">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b p-5 dark:border-gray-700">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
                {article.site}
              </span>
              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                {article.content_type}
              </span>
              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                {article.language.toUpperCase()}
              </span>
            </div>
            <h2 className="mt-2 text-lg font-semibold text-gray-900 dark:text-white">
              {article.title}
            </h2>
            {article.meta_description && (
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                {article.meta_description}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded-xl p-2 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800"
          >
            <X size={18} />
          </button>
        </div>

        {/* Metadata strip */}
        <div className="flex flex-wrap gap-4 border-b bg-gray-50 px-5 py-3 text-xs text-gray-500 dark:border-gray-700 dark:bg-gray-800/50 dark:text-gray-400">
          <span>
            🔑 <strong>Keyword:</strong> {article.target_keyword || '—'}
          </span>
          <span>
            📝 <strong>Words:</strong> {article.word_count?.toLocaleString() ?? '—'}
          </span>
          {article.affiliate_programs_used.length > 0 && (
            <span>
              💰 <strong>Affiliates:</strong> {article.affiliate_programs_used.join(', ')}
            </span>
          )}
        </div>

        {/* Article body preview */}
        <div className="max-h-[50vh] overflow-y-auto p-5">
          <pre className="whitespace-pre-wrap text-sm leading-relaxed text-gray-700 font-sans dark:text-gray-300">
            {article.body}
          </pre>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 border-t p-5 dark:border-gray-700">
          <button
            onClick={onClose}
            className="rounded-xl border px-4 py-2 text-sm text-gray-600 transition hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
          >
            Close
          </button>
          <button
            onClick={onReject}
            className="flex items-center gap-1.5 rounded-xl bg-red-50 px-4 py-2 text-sm font-medium text-red-600 transition hover:bg-red-100 dark:bg-red-900/20 dark:text-red-400 dark:hover:bg-red-900/30"
          >
            <XCircle size={15} />
            Reject
          </button>
          <button
            onClick={onApprove}
            className="flex items-center gap-1.5 rounded-xl bg-green-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-green-700"
          >
            <CheckCircle size={15} />
            Approve & Queue
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function ContentEngine() {
  const qc = useQueryClient()
  const [previewArticle, setPreviewArticle] = useState<Article | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [showRejectInput, setShowRejectInput] = useState<string | null>(null)

  // Stats
  const { data: stats, isLoading: statsLoading } = useQuery<Stats>({
    queryKey: ['content_stats'],
    queryFn: () => apiFetch<Stats>(`${API}/stats`),
    refetchInterval: 60_000,
  })

  // Draft queue — polls every 30s
  const { data: drafts, isLoading: draftsLoading } = useQuery<ArticleList>({
    queryKey: ['content_drafts'],
    queryFn: () => apiFetch<ArticleList>(`${API}/articles?status=draft&limit=50`),
    refetchInterval: 30_000,
  })

  // Published articles (recent)
  const { data: published } = useQuery<ArticleList>({
    queryKey: ['content_published'],
    queryFn: () => apiFetch<ArticleList>(`${API}/articles?status=published&limit=20`),
  })

  // Mutations
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['content_drafts'] })
    qc.invalidateQueries({ queryKey: ['content_stats'] })
    qc.invalidateQueries({ queryKey: ['content_published'] })
  }

  const approveMutation = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`${API}/articles/${id}/approve`, { method: 'PATCH' }),
    onSuccess: () => {
      invalidate()
      setPreviewArticle(null)
    },
  })

  const rejectMutation = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      apiFetch(`${API}/articles/${id}/reject`, {
        method: 'PATCH',
        body: JSON.stringify({ review_notes: reason }),
      }),
    onSuccess: () => {
      invalidate()
      setShowRejectInput(null)
      setRejectReason('')
      setPreviewArticle(null)
    },
  })

  const handleApprove = (id: string) => approveMutation.mutate(id)
  const handleReject = (id: string, reason: string) =>
    rejectMutation.mutate({ id, reason: reason || 'Rejected by reviewer' })

  const statCards = [
    {
      label: 'Articles Published',
      value: stats?.published_articles ?? 0,
      icon: FileText,
      color: 'blue',
    },
    {
      label: 'Traffic (30d)',
      value: stats?.traffic_30d ?? 0,
      icon: Activity,
      color: 'green',
    },
    {
      label: 'Affiliate Clicks (30d)',
      value: stats?.clicks_30d ?? 0,
      icon: MousePointerClick,
      color: 'purple',
    },
    {
      label: 'Revenue (30d)',
      value: `$${(stats?.revenue_30d ?? 0).toFixed(2)}`,
      icon: DollarSign,
      color: 'yellow',
      isRevenue: true,
    },
  ]

  const colorMap = {
    blue: 'bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400',
    green: 'bg-green-50 text-green-600 dark:bg-green-900/20 dark:text-green-400',
    purple: 'bg-purple-50 text-purple-600 dark:bg-purple-900/20 dark:text-purple-400',
    yellow: 'bg-yellow-50 text-yellow-600 dark:bg-yellow-900/20 dark:text-yellow-400',
  }

  return (
    <div className="space-y-6">
      {/* Preview Modal */}
      {previewArticle && (
        <ArticlePreviewModal
          article={previewArticle}
          onClose={() => setPreviewArticle(null)}
          onApprove={() => handleApprove(previewArticle.id)}
          onReject={() => handleReject(previewArticle.id, 'Rejected from preview')}
        />
      )}

      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Content Engine</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Apex Funnel Pipeline — AI-generated content approval &amp; publishing
          </p>
        </div>
        {(stats?.pending_review ?? 0) > 0 && (
          <div className="flex items-center gap-2 rounded-full bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-700 dark:bg-amber-900/20 dark:text-amber-400">
            <AlertTriangle size={14} />
            {stats!.pending_review} pending review
          </div>
        )}
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {statCards.map((card) => {
          const Icon = card.icon
          return (
            <div
              key={card.label}
              className="rounded-xl border bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800"
            >
              <div className="flex items-center gap-3">
                <div className={`rounded-lg p-2.5 ${colorMap[card.color as keyof typeof colorMap]}`}>
                  <Icon size={20} />
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
                    {card.label}
                  </p>
                  <p className="mt-0.5 text-2xl font-bold text-gray-900 dark:text-white">
                    {statsLoading ? '—' : card.value}
                  </p>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* ─── Pending Approval Queue ────────────────────────────────────────── */}
      <div className="rounded-xl border bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <div className="flex items-center justify-between border-b p-4 dark:border-gray-700">
          <h2 className="font-semibold text-gray-900 dark:text-white">
            Pending Review
            <span className="ml-2 text-gray-400">({drafts?.total ?? 0})</span>
          </h2>
          <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/20 dark:text-amber-400">
            Requires approval before publish
          </span>
        </div>

        {draftsLoading ? (
          <div className="p-8 text-center text-sm text-gray-400">Loading drafts…</div>
        ) : !drafts?.items?.length ? (
          <div className="p-8 text-center text-sm text-gray-400">
            No drafts pending review. Pipeline is clear ✓
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-700/50">
                <tr>
                  <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-300">
                    Title
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-300">
                    Site
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-300">
                    Words
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-300">
                    Keyword
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-300">
                    Created
                  </th>
                  <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-300">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y dark:divide-gray-700">
                {drafts.items.map((article) => (
                  <tr key={article.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                    <td className="max-w-xs px-4 py-3 font-medium text-gray-900 dark:text-white">
                      <p className="truncate">{article.title}</p>
                    </td>
                    <td className="px-4 py-3">
                      <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
                        {article.site}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                      {article.word_count?.toLocaleString() ?? '—'}
                    </td>
                    <td className="max-w-[180px] px-4 py-3 text-xs text-gray-500 dark:text-gray-400">
                      <p className="truncate">{article.target_keyword ?? '—'}</p>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-400 dark:text-gray-500">
                      {new Date(article.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {showRejectInput === article.id ? (
                        <div className="flex items-center justify-end gap-2">
                          <input
                            autoFocus
                            value={rejectReason}
                            onChange={(e) => setRejectReason(e.target.value)}
                            placeholder="Reason (optional)"
                            className="rounded-lg border px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                          />
                          <button
                            onClick={() => handleReject(article.id, rejectReason)}
                            disabled={rejectMutation.isPending}
                            className="rounded-lg bg-red-600 px-2 py-1 text-xs text-white hover:bg-red-700 disabled:opacity-50"
                          >
                            Confirm
                          </button>
                          <button
                            onClick={() => setShowRejectInput(null)}
                            className="rounded-lg border px-2 py-1 text-xs text-gray-500 hover:bg-gray-100 dark:border-gray-600 dark:hover:bg-gray-700"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            id={`preview-${article.id}`}
                            onClick={() => setPreviewArticle(article)}
                            className="flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs text-gray-600 transition hover:bg-gray-100 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
                          >
                            <Eye size={12} />
                            Preview
                          </button>
                          <button
                            id={`approve-${article.id}`}
                            onClick={() => handleApprove(article.id)}
                            disabled={approveMutation.isPending}
                            className="flex items-center gap-1 rounded-lg bg-green-600 px-2.5 py-1 text-xs font-medium text-white transition hover:bg-green-700 disabled:opacity-50"
                          >
                            <CheckCircle size={12} />
                            Approve
                          </button>
                          <button
                            id={`reject-${article.id}`}
                            onClick={() => setShowRejectInput(article.id)}
                            className="flex items-center gap-1 rounded-lg bg-red-50 px-2.5 py-1 text-xs font-medium text-red-600 transition hover:bg-red-100 dark:bg-red-900/20 dark:text-red-400 dark:hover:bg-red-900/30"
                          >
                            <XCircle size={12} />
                            Reject
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ─── Recently Published ──────────────────────────────────────────────── */}
      <div className="rounded-xl border bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <div className="border-b p-4 dark:border-gray-700">
          <h2 className="font-semibold text-gray-900 dark:text-white">
            Recently Published
            <span className="ml-2 text-gray-400">({published?.total ?? 0})</span>
          </h2>
        </div>
        {!published?.items?.length ? (
          <div className="p-8 text-center text-sm text-gray-400">No published articles yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-700/50">
                <tr>
                  <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-300">
                    Title
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-300">
                    Site
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-300">
                    Words
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-300">
                    Clicks
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-300">
                    Published
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y dark:divide-gray-700">
                {published.items.map((article) => (
                  <tr key={article.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                    <td className="max-w-xs px-4 py-3 font-medium text-gray-900 dark:text-white">
                      <p className="truncate">{article.title}</p>
                    </td>
                    <td className="px-4 py-3">
                      <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-300">
                        {article.site}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                      {article.word_count?.toLocaleString() ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">—</td>
                    <td className="px-4 py-3 text-xs text-gray-400 dark:text-gray-500">
                      <div className="flex items-center gap-1">
                        <Clock size={11} />
                        {article.published_at
                          ? new Date(article.published_at).toLocaleDateString()
                          : '—'}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
