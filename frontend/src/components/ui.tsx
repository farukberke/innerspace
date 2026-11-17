import { useId, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { Link, type LinkProps } from 'react-router-dom'

const inputCls =
  'mt-1.5 block min-h-12 w-full rounded-soft border border-line-strong bg-surface px-3 py-2 text-base text-ink placeholder:text-muted focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-200 disabled:bg-sunk aria-[invalid=true]:border-danger-600'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'

/** The single button look. Primary + secondary are the pair; danger/ghost are for destructive and tertiary actions. */
export function buttonCls(variant: Variant = 'primary', className = ''): string {
  const styles: Record<Variant, string> = {
    primary: 'bg-brand-600 text-white hover:bg-brand-700',
    secondary: 'border border-ink/25 bg-surface text-ink hover:border-ink/50 hover:bg-sunk',
    danger: 'bg-danger-600 text-white hover:bg-danger-700',
    ghost: 'text-brand-700 hover:bg-brand-50',
  }
  return `btn inline-flex min-h-11 items-center justify-center gap-2 rounded-soft px-4 py-2 text-[0.9375rem] font-bold disabled:cursor-not-allowed disabled:opacity-50 ${styles[variant]} ${className}`
}

export function Button({
  variant = 'primary',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return <button type="button" {...props} className={buttonCls(variant, className)} />
}

/** A router link that looks like a Button. */
export function LinkButton({ variant = 'primary', className = '', ...props }: LinkProps & { variant?: Variant }) {
  return <Link {...props} className={buttonCls(variant, className)} />
}

interface FieldProps {
  label: string
  hint?: string
}

export function TextField({ label, hint, ...props }: FieldProps & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId()
  return (
    <div>
      <label htmlFor={id} className="block text-[0.9375rem] font-semibold text-ink">
        {label}
      </label>
      <input id={id} {...props} className={inputCls} aria-describedby={hint ? `${id}-hint` : undefined} />
      {hint && (
        <p id={`${id}-hint`} className="mt-1 text-sm text-muted">
          {hint}
        </p>
      )}
    </div>
  )
}

export function TextArea({ label, hint, ...props }: FieldProps & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId()
  return (
    <div>
      <label htmlFor={id} className="block text-[0.9375rem] font-semibold text-ink">
        {label}
      </label>
      <textarea id={id} rows={4} {...props} className={inputCls} aria-describedby={hint ? `${id}-hint` : undefined} />
      {hint && (
        <p id={`${id}-hint`} className="mt-1 text-sm text-muted">
          {hint}
        </p>
      )}
    </div>
  )
}

export function SelectField({ label, children, ...props }: FieldProps & SelectHTMLAttributes<HTMLSelectElement>) {
  const id = useId()
  return (
    <div>
      <label htmlFor={id} className="block text-[0.9375rem] font-semibold text-ink">
        {label}
      </label>
      <select id={id} {...props} className={inputCls}>
        {children}
      </select>
    </div>
  )
}

export function CheckField({ label, ...props }: { label: string } & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId()
  return (
    <div className="flex min-h-11 items-center gap-3">
      <input id={id} type="checkbox" {...props} className="h-5 w-5 rounded border-line-strong accent-brand-600" />
      <label htmlFor={id} className="text-sm text-ink">
        {label}
      </label>
    </div>
  )
}

export function Alert({ kind = 'error', children }: { kind?: 'error' | 'info' | 'success'; children: ReactNode }) {
  const styles = {
    error: 'border-danger-200 bg-danger-50 text-danger-800',
    info: 'border-info-200 bg-info-50 text-info-800',
    success: 'border-ok-200 bg-ok-50 text-ok-800',
  }[kind]
  return (
    <div role={kind === 'error' ? 'alert' : 'status'} className={`rounded-soft border px-4 py-3 text-sm ${styles}`}>
      {children}
    </div>
  )
}

export function Card({ children, className = '', interactive = false }: { children: ReactNode; className?: string; interactive?: boolean }) {
  return (
    <div
      className={`rounded-soft-lg border border-line bg-surface p-4 sm:p-5 ${interactive ? 'transition-colors hover:border-ink/40' : ''} ${className}`}
    >
      {children}
    </div>
  )
}

export function PageHeader({ title, lede, actions }: { title: string; lede?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3 sm:mb-8">
      <div className="min-w-0">
        <h1 className="text-[2rem] leading-[1.05] text-ink sm:text-[2.75rem]">{title}</h1>
        {lede && <p className="mt-2 max-w-[60ch] text-base text-ink-2">{lede}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

export function Spinner() {
  return (
    <p role="status" className="flex items-center justify-center gap-2 py-12 text-base text-muted">
      <span aria-hidden className="inline-flex gap-1">
        <span className="h-2 w-2 animate-pulse rounded-full bg-brand-600" />
        <span className="h-2 w-2 animate-pulse rounded-full bg-brand-400 [animation-delay:150ms]" />
        <span className="h-2 w-2 animate-pulse rounded-full bg-brand-200 [animation-delay:300ms]" />
      </span>
      Yükleniyor…
    </p>
  )
}

/** An empty state: what is missing, why it matters, and the next step. */
export function Empty({ title, children, action }: { title?: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-4 rounded-soft-lg border border-dashed border-line-strong bg-surface/60 px-5 py-8 sm:flex-row sm:items-center sm:gap-6 sm:px-8">
      <span aria-hidden className="grid h-14 w-14 shrink-0 place-items-center rounded-full bg-brand-50 text-brand-600">
        <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
          <rect x="5" y="3" width="14" height="18" rx="1.5" />
          <path d="M9 8h6M9 12h6M9 16h3" />
        </svg>
      </span>
      <div className="min-w-0">
        {title && <p className="text-lg font-bold text-ink">{title}</p>}
        <div className="mt-1 max-w-[56ch] text-base text-ink-2">{children}</div>
        {action && <div className="mt-4">{action}</div>}
      </div>
    </div>
  )
}

export function Badge({ children, tone = 'slate' }: { children: ReactNode; tone?: 'slate' | 'brand' | 'green' | 'amber' | 'rose' }) {
  const styles = {
    slate: 'bg-sunk text-ink-2',
    brand: 'bg-brand-100 text-brand-800',
    green: 'bg-ok-100 text-ok-800',
    amber: 'bg-warn-100 text-warn-900',
    rose: 'bg-danger-100 text-danger-800',
  }[tone]
  return <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[0.8125rem] font-semibold ${styles}`}>{children}</span>
}

/** "Back to …" link above a detail page. */
export function BackLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="mb-3 inline-flex min-h-11 items-center gap-2 text-[0.9375rem] font-semibold text-brand-700 hover:text-brand-900">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" aria-hidden>
        <path d="M19 12H5M11 6l-6 6 6 6" />
      </svg>
      {children}
    </Link>
  )
}

export function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' })
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('tr-TR', { dateStyle: 'medium', timeStyle: 'short' })
}

export function formatShortDate(iso: string): string {
  return new Date(iso).toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' })
}

/** Whole calendar days from `now` to `iso` (0 = today, 1 = tomorrow), in local time. */
export function calendarDaysUntil(iso: string, now: Date = new Date()): number {
  const a = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const t = new Date(iso)
  const b = new Date(t.getFullYear(), t.getMonth(), t.getDate())
  return Math.round((b.getTime() - a.getTime()) / 86400000)
}

export function relativeDay(iso: string, now: Date = new Date()): string {
  const n = calendarDaysUntil(iso, now)
  if (n === 0) return 'bugün'
  if (n === 1) return 'yarın'
  if (n === -1) return 'dün'
  return n > 0 ? `${n} gün sonra` : `${-n} gün önce`
}
