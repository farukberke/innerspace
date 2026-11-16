import { request, tokens } from './client'
import type {
  AfterSessionNote,
  Assignment,
  ClientRead,
  CrisisInfo,
  Entry,
  EntryInput,
  EntryKind,
  EntryPage,
  InvitationCreated,
  SharedSummary,
  Summary,
  SummaryJob,
  SummaryListItem,
  TokenPair,
  User,
  UserRole,
} from './types'

export const authApi = {
  async login(email: string, password: string): Promise<void> {
    const pair = await request<TokenPair>('/auth/login', { method: 'POST', body: { email, password }, auth: false })
    tokens.set(pair)
  },
  /** Revokes the refresh token server-side. Never throws: the local session is cleared regardless. */
  async logout(refreshToken: string | null): Promise<void> {
    if (!refreshToken) return
    try {
      await request<void>('/auth/logout', { method: 'POST', body: { refresh_token: refreshToken }, auth: false })
    } catch {
      // network/server error: the caller still ends the local session
    }
  },
  me: () => request<User>('/auth/me'),
  acceptInvitation: (token: string, password: string, display_name: string) =>
    request<User>('/auth/accept-invitation', { method: 'POST', body: { token, password, display_name }, auth: false }),
}

export const entriesApi = {
  list: (q: { kind?: EntryKind; limit: number; offset: number }) => request<EntryPage>('/entries', { query: q }),
  create: (body: EntryInput) => request<Entry>('/entries', { method: 'POST', body }),
  update: (id: string, body: Partial<Omit<EntryInput, 'kind'>>) =>
    request<Entry>(`/entries/${id}`, { method: 'PATCH', body }),
  remove: (id: string) => request<void>(`/entries/${id}`, { method: 'DELETE' }),
}

export const summariesApi = {
  list: () => request<Summary[]>('/summaries'),
  get: (id: string) => request<Summary>(`/summaries/${id}`),
  update: (id: string, body: { title?: string; statements: { id: string; text: string }[] }) =>
    request<Summary>(`/summaries/${id}`, { method: 'PATCH', body }),
  approve: (id: string) => request<Summary>(`/summaries/${id}/approve`, { method: 'POST' }),
  share: (id: string) => request<Summary>(`/summaries/${id}/share`, { method: 'POST' }),
  unshare: (id: string) => request<Summary>(`/summaries/${id}/unshare`, { method: 'POST' }),
  generate: (period_start: string, period_end: string, idempotencyKey: string) =>
    request<SummaryJob>('/summaries/generate', {
      method: 'POST',
      body: { period_start, period_end },
      headers: { 'Idempotency-Key': idempotencyKey },
    }),
  job: (id: string) => request<SummaryJob>(`/summaries/jobs/${id}`),
}

export const afterSessionApi = {
  /** 201 = saved note; 200 = crisis response (nothing saved). */
  create: (text: string) =>
    request<AfterSessionNote | CrisisInfo>('/after-session-notes', { method: 'POST', body: { text } }),
  list: () => request<AfterSessionNote[]>('/after-session-notes'),
}

export const clinicianApi = {
  clients: () => request<ClientRead[]>('/clinician/clients'),
  summaries: () => request<SummaryListItem[]>('/clinician/summaries'),
  summary: (id: string) => request<SharedSummary>(`/clinician/summaries/${id}`),
}

export const invitationsApi = {
  create: (email: string, role: UserRole, clinician_id?: string) =>
    request<InvitationCreated>('/invitations', {
      method: 'POST',
      body: { email, role, clinician_id: clinician_id || null },
    }),
}

export const adminApi = {
  users: (role?: UserRole) => request<User[]>('/admin/users', { query: { role } }),
  setActive: (id: string, is_active: boolean) =>
    request<User>(`/admin/users/${id}`, { method: 'PATCH', body: { is_active } }),
  assignments: () => request<Assignment[]>('/admin/assignments'),
  createAssignment: (clinician_id: string, client_id: string) =>
    request<Assignment>('/admin/assignments', { method: 'POST', body: { clinician_id, client_id } }),
  deleteAssignment: (id: string) => request<void>(`/admin/assignments/${id}`, { method: 'DELETE' }),
}
