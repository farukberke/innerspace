import { useId, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { Link, type LinkProps } from 'react-router-dom'

const inputCls =
  'mt-1 block min-h-11 w-full rounded-soft border border-line-strong bg-surface px-3 py-2 text-base text-ink placeholder:text-muted focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-200 disabled:bg-sunk aria-[invalid=true]:border-danger-600'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'

/** The single button look. Primary + secondary are the pair; danger/ghost are for destructive and tertiary actions. */
export function buttonCls(variant: Variant = 'primary', className = ''): string {
  const styles: Record<Variant, string> = {
    primary: 'bg-brand-600 text-white hover:bg-brand-700',
    secondary: 'border border-line-strong bg-surface text-ink hover:bg-sunk',
    danger: 'bg-danger-600 text-white hover:bg-danger-700',
    ghost: 'text-brand-700 hover:bg-brand-50',
  }
  return `btn inline-flex min-h-11 items-center justify-center rounded-soft px-4 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50 ${styles[variant]} ${className}`
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
      <label htmlFor={id} className="block text-sm font-semibold text-ink">
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
      <label htmlFor={id} className="block text-sm font-semibold text-ink">
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
      <label htmlFor={id} className="block text-sm font-semibold text-ink">
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
    <div className={`rounded-soft-lg border border-line bg-surface p-4 sm:p-5 ${interactive ? 'lift hover:border-line-strong' : ''} ${className}`}>
      {children}
    </div>
  )
}

export function PageHeader({ title, actions }: { title: string; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-2xl font-semibold text-ink sm:text-3xl">{title}</h1>
      <div className="flex flex-wrap gap-2">{actions}</div>
    </div>
  )
}

export function Spinner() {
  return (
    <p role="status" className="py-10 text-center text-base text-muted">
      Yükleniyor…
    </p>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-soft border border-dashed border-line-strong px-4 py-10 text-center text-base text-muted">{children}</p>
}

export function Badge({ children, tone = 'slate' }: { children: ReactNode; tone?: 'slate' | 'brand' | 'green' | 'amber' | 'rose' }) {
  const styles = {
    slate: 'bg-sunk text-ink-2',
    brand: 'bg-brand-100 text-brand-800',
    green: 'bg-ok-100 text-ok-800',
    amber: 'bg-warn-100 text-warn-800',
    rose: 'bg-danger-100 text-danger-800',
  }[tone]
  return <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${styles}`}>{children}</span>
}

export function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' })
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('tr-TR', { dateStyle: 'medium', timeStyle: 'short' })
}
