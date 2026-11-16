export const AI_DISCLAIMER_CLIENT =
  'Bu özet, kendi kayıtlarından AI ile düzenlenmiştir. Teşhis veya tedavi önerisi içermez.'
export const AI_DISCLAIMER_CLINICIAN =
  'Bu özet, danışanın kendi kayıtlarından AI ile düzenlenmiştir. Teşhis veya tedavi önerisi içermez.'

export const AI_DISCLAIMER_NOTE = 'Bu not, kendi yazdığından AI ile düzenlenmiştir. Teşhis veya tedavi önerisi içermez.'

export function AiDisclaimer({ audience, kind = 'summary' }: { audience: 'client' | 'clinician'; kind?: 'summary' | 'note' }) {
  const text = kind === 'note' ? AI_DISCLAIMER_NOTE : audience === 'client' ? AI_DISCLAIMER_CLIENT : AI_DISCLAIMER_CLINICIAN
  return (
    <p data-testid="ai-disclaimer" className="mt-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
      {text}
    </p>
  )
}
