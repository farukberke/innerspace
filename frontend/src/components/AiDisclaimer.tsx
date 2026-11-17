export const AI_DISCLAIMER_CLIENT =
  'Bu özet, kendi kayıtlarından AI ile düzenlenmiştir. Teşhis veya tedavi önerisi içermez.'
export const AI_DISCLAIMER_CLINICIAN =
  'Bu özet, danışanın kendi kayıtlarından AI ile düzenlenmiştir. Teşhis veya tedavi önerisi içermez.'

export const AI_DISCLAIMER_NOTE = 'Bu not, kendi yazdığından AI ile düzenlenmiştir. Teşhis veya tedavi önerisi içermez.'

export function AiDisclaimer({ audience, kind = 'summary' }: { audience: 'client' | 'clinician'; kind?: 'summary' | 'note' }) {
  const text = kind === 'note' ? AI_DISCLAIMER_NOTE : audience === 'client' ? AI_DISCLAIMER_CLIENT : AI_DISCLAIMER_CLINICIAN
  return (
    <p data-testid="ai-disclaimer" className="mt-4 border-t border-line pt-3 text-[0.8125rem] leading-relaxed text-muted">
      {text}
    </p>
  )
}
