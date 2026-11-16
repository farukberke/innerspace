// Hand-written from backend/app/schemas/*.py. Keep in sync with the backend.

export type UserRole = 'org_admin' | 'clinician' | 'client'
export type EntryKind = 'quick' | 'panic' | 'medication' | 'avoidance'
export type SummaryStatus = 'draft' | 'approved' | 'shared' | 'revoked'
export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'crisis'

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface User {
  id: string
  organization_id: string
  email: string
  display_name: string
  role: UserRole
  is_active: boolean
}

export interface ClientRead {
  id: string
  display_name: string
}

export interface InvitationCreated {
  id: string
  email: string
  role: UserRole
  expires_at: string
  token: string
}

export interface Assignment {
  id: string
  clinician_id: string
  client_id: string
  created_at: string
}

export interface Entry {
  id: string
  kind: EntryKind
  occurred_at: string
  note: string | null
  details: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface EntryPage {
  items: Entry[]
  total: number
  limit: number
  offset: number
}

export interface EntryInput {
  kind: EntryKind
  occurred_at: string
  note: string | null
  details: Record<string, unknown>
}

export interface Statement {
  id: string
  section: string
  text: string
  source_entry_ids: string[]
}

export interface Summary {
  id: string
  client_id: string
  title: string
  body: string
  status: SummaryStatus
  period_start: string | null
  period_end: string | null
  statements: Statement[]
  approved_at: string | null
  shared_at: string | null
  created_at: string
}

export interface SummaryListItem {
  id: string
  client_id: string
  title: string
  period_start: string | null
  period_end: string | null
  shared_at: string | null
  created_at: string
}

export interface SharedSummary extends SummaryListItem {
  body: string
}

export interface CrisisInfo {
  crisis: boolean
  message: string
  resources: Record<string, string>[]
}

export interface SummaryJob {
  id: string
  status: JobStatus
  period_start: string
  period_end: string
  summary_id: string | null
  error_code: string | null
  attempts: number
  created_at: string
  updated_at: string
  crisis: CrisisInfo | null
}

export interface AfterSessionNote {
  id: string
  discussed: string[]
  to_try: string[]
  questions: string[]
  created_at: string
}
