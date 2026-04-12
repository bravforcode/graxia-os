import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { format, formatDistanceToNow } from 'date-fns'
import { th } from 'date-fns/locale'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(date: string | Date): string {
  return format(new Date(date), 'dd MMM yyyy', { locale: th })
}

export function formatDateTime(date: string | Date): string {
  return format(new Date(date), 'dd MMM yyyy HH:mm', { locale: th })
}

export function formatRelative(date: string | Date): string {
  return formatDistanceToNow(new Date(date), { addSuffix: true, locale: th })
}

export function formatCurrency(amount: number, currency: string = 'THB'): string {
  return new Intl.NumberFormat('th-TH', {
    style: 'currency',
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
}

export function formatNumber(num: number): string {
  return new Intl.NumberFormat('th-TH').format(num)
}

export function getScoreColor(score: number): string {
  if (score >= 7) return 'text-emerald-400'
  if (score >= 5.5) return 'text-blue-400'
  if (score >= 4) return 'text-amber-400'
  return 'text-slate-400'
}

export function getScoreBadgeClass(score: number): string {
  if (score >= 7) return 'badge-success'
  if (score >= 5.5) return 'badge-info'
  if (score >= 4) return 'badge-warning'
  return 'badge'
}

export function getStatusBadgeClass(status: string): string {
  const statusMap: Record<string, string> = {
    found: 'badge',
    scored: 'badge-info',
    decided: 'badge-info',
    approved: 'badge-success',
    in_progress: 'badge-warning',
    applied: 'badge-warning',
    accepted: 'badge-success',
    rejected: 'badge-danger',
    ignored: 'badge',
  }
  return statusMap[status] || 'badge'
}

export function truncate(text: string, length: number): string {
  if (text.length <= length) return text
  return text.slice(0, length) + '...'
}
