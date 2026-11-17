import { Link, Navigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { HOME_BY_ROLE } from '../auth/roles'
import { ArrowIcon } from '../components/icons'
import { DemoBanner, Logo, SkipLink } from '../components/Layout'
import { Mark, type MarkKind } from '../components/Mark'
import { Spinner } from '../components/ui'

/** Synthetic rendering of the product's own surfaces. Not interactive, labelled as an example. */
const SAMPLE_DAYS: { sleep: number; attacks: number[] }[] = [
  [7, []], [6.5, []], [5, [6]], [7, []], [7.5, []], [6, []], [5.5, [8]], [6, []], [7, []], [7.5, []],
  [6.5, []], [7, []], [5, [5]], [6.5, []], [7, []], [8, []], [7, []], [6.5, []], [7, []], [7.5, []], [7, []],
].map(([sleep, attacks]) => ({ sleep: sleep as number, attacks: attacks as number[] }))

function ProductSample() {
  return (
    <div role="group" aria-label="Uygulama ekranı örneği, sentetik veri" className="rounded-soft-lg bg-surface p-5 text-ink sm:p-6">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-[1.0625rem] font-extrabold">Son 21 gün</p>
        <p className="text-[0.8125rem] font-semibold text-muted">örnek ekran · sentetik veri</p>
      </div>
      <div aria-hidden className="mt-4 grid h-32 items-end gap-1 border-b border-ink" style={{ gridTemplateColumns: 'repeat(21, minmax(0, 1fr))' }}>
        {SAMPLE_DAYS.map((d, i) => (
          <div key={i} className="flex h-full flex-col items-center justify-end gap-1">
            {d.attacks.map((a, j) => (
              <span key={j} className="block aspect-square rounded-full bg-attack" style={{ width: `${35 + a * 6.5}%` }} />
            ))}
            <span className="block w-full rounded-t-[2px] bg-sleep" style={{ height: `${d.sleep * 6.2}%` }} />
          </div>
        ))}
      </div>
      <p aria-hidden className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[0.8125rem] font-semibold text-muted">
        <span className="inline-flex items-center gap-1.5">
          <Mark kind="sleep" size={11} /> Uyku
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Mark kind="panic" size={11} /> Atak; büyük daire = daha şiddetli
        </span>
      </p>
      <div className="mt-5 border-t border-line pt-4">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-[1.0625rem] font-extrabold">Seans öncesi özet</p>
          <span className="rounded-full bg-ok-100 px-2.5 py-0.5 text-[0.8125rem] font-semibold text-ok-800">Paylaşıldı</span>
        </div>
        <ul className="mt-3 space-y-2.5">
          {(
            [
              ['panic', 'Bu dönemde 3 atak kaydın var; ikisi kalabalık toplu taşımada.', 3],
              ['sleep', 'Ataklardan önceki gecelerde uykun 5 saatin altında.', 3],
              ['avoidance', 'Bir doğum günü yemeğine gitmediğini yazdın.', 1],
            ] as [MarkKind, string, number][]
          ).map(([kind, text, n]) => (
            <li key={text} className="flex gap-3">
              <span className="mt-1.5">
                <Mark kind={kind} size={12} />
              </span>
              <p className="text-[0.9375rem] leading-relaxed">
                {text} <span className="num font-semibold text-muted">· {n} kayıt</span>
              </p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

const STEPS: { image: string; title: string; body: string }[] = [
  { image: '/step-record.webp', title: 'Arada kaydet', body: 'Günlük not, uyku, panik atağı, ilaç ve kaçınma. Otuz saniye sürer; kayıtları yalnızca danışan görür.' },
  {
    image: '/step-summary.webp',
    title: 'Seanstan önce özetle',
    body: 'AI yalnızca seçilen dönemin kayıtlarını toparlar. Her cümle dayandığı kayıtları gösterir; yorum, teşhis ya da öneri eklemez.',
  },
  { image: '/step-share.webp', title: 'Danışan onaylasın, uzman okusun', body: 'Danışan düzenler ve onaylar. Paylaştığında atanmış uzman okur; paylaşım her an geri alınabilir.' },
  { image: '/step-after.webp', title: 'Seansta konuşulanı unutma', body: 'Seans sonrası iki dakikalık not; zor anlar için uzmanla hazırlanan “O an” kartı.' },
]

const ROLES = [
  ['Klinik yöneticisi', 'Uzmanları davet eder, danışanları atar. Klinik içeriği hiçbir koşulda göremez.'],
  ['Uzman', 'Yalnızca kendisine atanmış danışanın onaylayıp paylaştığı özetleri görür; yeni paylaşımlar listede işaretlenir.'],
  ['Danışan', 'Kayıtlarının tek sahibidir; neyin, ne zaman paylaşılacağına o karar verir.'],
]

const RULES = [
  ['AI teşhis veya ilaç önermez', 'Çıktı doğrulanır; teşhis, ilaç, doz ya da tedavi önerisi gibi okunan ifadeler reddedilir.'],
  ['Kriz anında AI susar', 'Kriz ifadesi saptanırsa içerik üretilmez; önceden yazılmış sabit bir ekran gösterilir.'],
  ['Onaysız paylaşım yok', 'Hiçbir özet danışan onaylamadan uzmana ulaşmaz.'],
  ['Klinikler birbirinden ayrı', 'Bir klinik başka bir kliniğin verisine erişemez; bu sunucuda, her sorguda uygulanır.'],
  ['Veri danışanın', 'Danışan verisini indirebilir, hesabını silebilir.'],
]

export function Landing() {
  const { state } = useAuth()
  if (state.status === 'loading') return <Spinner />
  if (state.status === 'authed') return <Navigate to={HOME_BY_ROLE[state.user.role]} replace />

  const wrap = 'mx-auto w-full max-w-6xl px-4 sm:px-6 lg:px-8'
  return (
    <div className="min-h-screen">
      <SkipLink />
      <DemoBanner />
      <div className="bg-brand-600 text-white">
        <header className={`${wrap} flex items-center justify-between gap-3 py-4`}>
          <Logo inverted />
          <nav aria-label="Sayfa içi" className="hidden items-center gap-1 md:flex">
            {[
              ['#nasil', 'Nasıl çalışır'],
              ['#roller', 'Klinik ve uzman'],
              ['#kurallar', 'Kurallar'],
            ].map(([href, label]) => (
              <a key={href} href={href} className="flex min-h-11 items-center rounded-soft px-3 text-[0.9375rem] font-semibold text-brand-50 hover:bg-white/10 hover:text-white">
                {label}
              </a>
            ))}
          </nav>
          <Link to="/login" className="btn inline-flex min-h-11 items-center rounded-soft border border-white/40 px-4 text-[0.9375rem] font-bold hover:bg-white/10">
            Giriş yap
          </Link>
        </header>

        <main id="main" tabIndex={-1} className="focus:outline-none">
          <section className={`${wrap} grid items-center gap-12 pb-20 pt-10 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:gap-16 lg:pb-28 lg:pt-16`}>
            <div>
              <h1 className="display text-[3.25rem] leading-[0.95] sm:text-[4.5rem] lg:text-[5.25rem]">Seanslar arası defter.</h1>
              <p className="mt-6 max-w-[34rem] text-lg leading-relaxed text-brand-50 sm:text-xl">
                Terapi ve psikiyatri sürecindeki danışan yaşadıklarını kaydeder; seanstan önce kendi kayıtlarından, kaynak gösteren kısa bir özet hazırlar. Danışan onaylamadan uzmana hiçbir şey gitmez.
              </p>
              <div className="mt-9 flex flex-col gap-3 sm:flex-row">
                <Link to="/login" className="btn inline-flex min-h-12 items-center justify-center gap-2 rounded-soft bg-white px-6 text-base font-extrabold text-brand-700 hover:bg-brand-50">
                  Giriş yap <ArrowIcon />
                </Link>
                <a href="#nasil" className="btn inline-flex min-h-12 items-center justify-center rounded-soft border border-white/40 px-6 text-base font-bold hover:bg-white/10">
                  Nasıl çalışır
                </a>
              </div>
            </div>
            <ProductSample />
          </section>
        </main>
      </div>

      <section id="nasil" aria-labelledby="nasil-h" className="py-20 lg:py-28">
        <div className={wrap}>
          <h2 id="nasil-h" className="max-w-[18ch] text-[2.25rem] font-extrabold leading-[1.02] sm:text-[3rem]">
            Haftada 50 dakika seans, arada bir hafta hayat.
          </h2>
          <p className="mt-5 max-w-[60ch] text-lg text-ink-2">
            Seansın ilk dakikaları çoğu zaman “bu hafta ne oldu”yu toparlamaya gider. Seans Arası o haftayı seansa hazır getirir.
          </p>
          <ol className="mt-14 grid gap-x-8 gap-y-10 border-t border-ink pt-8 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s) => (
              <li key={s.title}>
                <img src={s.image} alt="" width={320} height={320} loading="lazy" className="aspect-square w-full max-w-[13rem] object-cover mix-blend-multiply [mask-image:radial-gradient(closest-side,black_72%,transparent)]" />
                <h3 className="mt-4 text-xl font-extrabold">{s.title}</h3>
                <p className="mt-2 text-base leading-relaxed text-ink-2">{s.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section aria-label="Kapak" className="relative overflow-hidden bg-sunk">
        <img
          src="/landing-cover.webp"
          alt=""
          width={1536}
          height={1024}
          loading="lazy"
          className="h-[24rem] w-full object-cover object-right sm:h-[32rem] lg:h-[38rem]"
        />
        <p className="absolute left-0 right-0 top-0 mx-auto max-w-6xl px-4 pt-10 text-[2rem] font-extrabold leading-[1.05] text-ink sm:px-6 sm:pt-14 sm:text-[3rem] lg:px-8">
          <span className="block max-w-[11ch] sm:max-w-[14ch]">Seansta konuşulan unutulmasın; seanslar arası yaşanan da.</span>
        </p>
      </section>

      <section id="roller" aria-labelledby="roller-h" className="py-20 lg:py-28">
        <div className={`${wrap} grid gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]`}>
          <div>
            <h2 id="roller-h" className="text-[2.25rem] font-extrabold leading-[1.02] sm:text-[3rem]">
              Klinik, uzman, danışan.
            </h2>
            <p className="mt-5 max-w-[46ch] text-lg text-ink-2">
              Klinik bir organizasyon olarak çalışır: yönetici uzmanları davet eder ve danışanlara atar, uzman danışanını davet eder, danışan seanstan önce özetini paylaşır. Her rol yalnızca işini yapmak için gereken kadarını görür.
            </p>
          </div>
          <dl className="divide-y divide-line border-y border-ink">
            {ROLES.map(([t, b]) => (
              <div key={t} className="grid gap-1 py-5 sm:grid-cols-[11rem_1fr] sm:gap-6">
                <dt className="text-lg font-extrabold">{t}</dt>
                <dd className="text-base leading-relaxed text-ink-2">{b}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <section id="kurallar" aria-labelledby="kurallar-h" className="bg-ink py-20 text-white lg:py-28">
        <div className={wrap}>
          <h2 id="kurallar-h" className="max-w-[20ch] text-[2.25rem] font-extrabold leading-[1.02] sm:text-[3rem]">
            Kurallar sunucuda; yapay zekânın kararına bırakılmaz.
          </h2>
          <ul className="mt-12 grid gap-x-10 gap-y-8 sm:grid-cols-2 lg:grid-cols-3">
            {RULES.map(([t, b]) => (
              <li key={t} className="border-t border-white/25 pt-5">
                <h3 className="text-lg font-extrabold">{t}</h3>
                <p className="mt-2 text-base leading-relaxed text-white/75">{b}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <footer className="border-t border-line py-8">
        <div className={`${wrap} flex flex-col gap-2 text-[0.9375rem] text-ink-2 sm:flex-row sm:justify-between`}>
          <p>Seans Arası · Gerçek kişisel veya sağlık bilgisi girme.</p>
          <p>Tıbbi tavsiye vermez; teşhis veya tedavi aracı değildir.</p>
        </div>
      </footer>
    </div>
  )
}
