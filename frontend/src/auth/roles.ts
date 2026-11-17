import type { UserRole } from '../api/types'

export const HOME_BY_ROLE: Record<UserRole, string> = {
  client: '/client/home',
  clinician: '/clinician/clients',
  org_admin: '/admin/users',
}

export const ROLE_LABEL: Record<UserRole, string> = {
  client: 'Danışan',
  clinician: 'Uzman',
  org_admin: 'Klinik yöneticisi',
}
