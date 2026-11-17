import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { HOME_BY_ROLE } from '../auth/roles'
import { DemoBanner, SkipLink } from '../components/Layout'
import { Badge, buttonCls, LinkButton, Spinner } from '../components/ui'

const REPO_URL = 'https://github.com/farukberke/innerspace'

/** Static, synthetic-data rendering of the product's own summary screen. Not interactive. */
function AppFrame() {
  const statements = [
    { section: 'Uyku', text: 'Son iki haftada 5 gece uykuya dalmakta zorlandığını yazdın.', sources: 5 },
    { section: 'Kaygı', text: 'Toplantı öncesinde 2 kez göğüste sıkışma hissi kaydettin.', sources: 2 },
    { section: 'Seansa taşımak istediğin', text: 'İşteki sunum kaygısı hakkında konuşmak istediğini not ettin.', sources: 1 },
  ]
  return (
    <div
      role="group"
      aria-label="Uygulama arayüzü örneği, sentetik veri"
      className="rounded-soft-lg border border-line-strong bg-surface p-4 sm:p-6"
    >
      <p className="mb-4 text-sm font-semibold text-muted">Özetlerim · örnek ekran</p>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="font-display text-xl font-semibold">Seans öncesi özet</p>
        <Badge tone="green">Paylaşıldı</Badge>
      </div>
      <p className="mt-1 text-sm text-muted">3 Kasım 2026 – 17 Kasım 2026</p>
      <ul className="mt-4 space-y-3">
        {statements.map((s) => (
          <li key={s.section} className="rounded-soft border border-line bg-paper p-3">
            <p className="text-sm font-semibold text-brand-700">{s.section}</p>
            <p className="mt-1 text-base">{s.text}</p>
            <p className="mt-1 text-sm text-muted">{s.sources} kayda dayanıyor</p>
          </li>
        ))}
      </ul>
      <p className="mt-3 rounded-soft border border-line bg-paper px-3 py-2 text-sm text-ink-2">
        Bu özet, kendi kayıtlarından AI ile düzenlenmiştir. Teşhis veya tedavi önerisi içermez.
      </p>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center">
        <span className={buttonCls('secondary', 'select-none')} aria-hidden="true">
          Paylaşımı geri al
        </span>
        <span className="text-sm text-muted">Uzmanın yalnızca onayladığın özeti görür.</span>
      </div>
    </div>
  )
}

const STEPS = [
  { title: 'Arada kaydet', body: 'Günlük, panik atağı, ilaç ve kaçınma kayıtlarını yalnızca sen görürsün.' },
  {
    title: 'Seanstan önce özet hazırla',
    body: 'AI, yalnızca kendi kayıtlarından kaynaklı bir taslak çıkarır. Her ifade hangi kayda dayandığını gösterir; sen düzenler ve onaylarsın.',
  },
  { title: 'Seansta konuşulanı not et', body: 'Seans sonrası notunu yazarsın; AI onu düzenler, ne yapılacağına sen karar verirsin.' },
  {
    title: 'Zor an için plan yap',
    body: 'Planım sayfasında adımlarını, kendine notunu ve arayacağın kişileri yazarsın. “O an” kartı bunları büyük yazıyla gösterir.',
  },
]

const ROLES = [
  ['Klinik yöneticisi', 'Uzmanları davet eder, danışanları atar. Klinik içeriği göremez.'],
  ['Uzman', 'Yalnızca kendisine atanmış danışanın onaylayıp paylaştığı özetleri görür.'],
  ['Danışan', 'Kayıtlarının tek sahibidir; neyin paylaşılacağına o karar verir.'],
]

const PRIVACY = [
  { title: 'AI teşhis veya ilaç önermez', body: 'Çıktı doğrulanır; teşhis, ilaç, doz ya da tedavi önerisi gibi okunan ifadeler reddedilir.' },
  {
    title: 'Kriz anında AI susar',
    body: 'Kriz ifadesi saptanırsa içerik üretilmez; önceden yazılmış sabit bir ekran gösterilir.',
  },
  { title: 'Onaylamadan paylaşılmaz', body: 'Hiçbir özet sen onaylamadan uzmanına ulaşmaz. Paylaşımı istediğin zaman geri alırsın.' },
  { title: 'Verin senin', body: 'Verini indirebilir, hesabını silebilirsin.' },
  { title: 'Organizasyonlar ayrıdır', body: 'Bir klinik başka bir kliniğin verisine erişemez.' },
]

const NAV_LINKS = [
  ['#nasil', 'Nasıl çalışır'],
  ['#uzman', 'Uzman için'],
  ['#guvenlik', 'Güvenlik'],
]

export function Landing() {
  const { state } = useAuth()
  if (state.status === 'loading') return <Spinner />
  if (state.status === 'authed') return <Navigate to={HOME_BY_ROLE[state.user.role]} replace />

  const wrap = 'mx-auto w-full max-w-6xl px-4 sm:px-6'
  const h2 = 'font-display text-3xl font-semibold sm:text-4xl'
  return (
    <div className="min-h-screen">
      <SkipLink />
      <DemoBanner />
      <header className="border-b border-line">
        <div className={`${wrap} flex items-center justify-between gap-3 py-3`}>
          <span className="font-display text-xl font-semibold text-brand-700">InnerSpace</span>
          <nav aria-label="Sayfa içi" className="hidden items-center gap-1 md:flex">
            {NAV_LINKS.map(([href, label]) => (
              <a key={href} href={href} className="flex min-h-11 items-center rounded-soft px-3 text-sm font-medium text-ink-2 hover:bg-sunk">
                {label}
              </a>
            ))}
          </nav>
          <LinkButton to="/login" variant="secondary">
            Giriş yap
          </LinkButton>
        </div>
      </header>

      <main id="main" tabIndex={-1} className="focus:outline-none">
        <section className="flex min-h-[calc(100svh-7rem)] items-center py-12 lg:py-16">
          <div className={`${wrap} grid items-center gap-10 lg:grid-cols-2 lg:gap-14`}>
            <div>
              <p className="rise mb-4 text-sm font-semibold text-brand-700">Portföy projesi · yalnızca sentetik veri</p>
              <h1 className="rise rise-2 text-4xl font-semibold leading-tight sm:text-5xl">
                Terapi ve psikiyatri sürecindeki danışan ve uzmanı için seanslar arası defter
              </h1>
              <p className="rise rise-3 mt-5 max-w-xl text-lg text-ink-2">
                Yaşadıklarını kaydet. Seanstan önce AI, yalnızca senin kayıtlarından kaynaklı bir özet taslağı hazırlasın; sen onaylamadan hiçbir şey uzmanına gitmez.
              </p>
              <div className="rise rise-3 mt-8 flex flex-col gap-3 sm:flex-row">
                <LinkButton to="/login" className="w-full sm:w-auto">
                  Demoyu aç
                </LinkButton>
                <a href="#nasil" className={buttonCls('secondary', 'w-full sm:w-auto')}>
                  Nasıl çalışır
                </a>
              </div>
            </div>
            <div className="rise rise-2">
              <AppFrame />
            </div>
          </div>
        </section>

        <section id="nasil" aria-labelledby="nasil-h" className="border-t border-line py-16 lg:py-24">
          <div className={wrap}>
            <h2 id="nasil-h" className={h2}>
              Seanslar arasında dört adım
            </h2>
            <ol className="mt-10 grid gap-4 md:grid-cols-2">
              {STEPS.map((s, i) => (
                <li key={s.title} className="rounded-soft-lg border border-line bg-surface p-6">
                  <p className="text-sm font-semibold text-brand-700">Adım {i + 1}</p>
                  <h3 className="mt-1 text-xl font-semibold">{s.title}</h3>
                  <p className="mt-2 text-base text-ink-2">{s.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section aria-label="Bir cümle" className="bg-brand-800 py-20 text-white lg:py-32">
          <div className={wrap}>
            <p className="max-w-4xl font-display text-3xl font-medium leading-snug sm:text-5xl">
              Seansta konuşulan unutulmasın; seanslar arası yaşanan da.
            </p>
          </div>
        </section>

        <section id="uzman" aria-labelledby="uzman-h" className="py-16 lg:py-24">
          <div className={`${wrap} grid gap-10 lg:grid-cols-2`}>
            <div>
              <h2 id="uzman-h" className={h2}>
                Klinik, uzman ve danışan için ayrı roller
              </h2>
              <p className="mt-4 text-lg text-ink-2">
                Kurum bir klinik olarak çalışır: klinik yöneticisi uzmanları ve danışan atamalarını yönetir, uzman paylaşılan özetleri okur.
              </p>
            </div>
            <ul className="space-y-3">
              {ROLES.map(([t, b]) => (
                <li key={t} className="rounded-soft-lg border border-line bg-surface p-5">
                  <h3 className="text-lg font-semibold">{t}</h3>
                  <p className="mt-1 text-base text-ink-2">{b}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section id="guvenlik" aria-labelledby="guvenlik-h" className="border-t border-line bg-sunk py-16 lg:py-24">
          <div className={wrap}>
            <h2 id="guvenlik-h" className={h2}>
              Güvenlik ve mahremiyet kuralları
            </h2>
            <p className="mt-4 max-w-2xl text-lg text-ink-2">Bu kurallar sunucuda uygulanır; yapay zekânın kararına bırakılmaz.</p>
            <ul className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {PRIVACY.map((p) => (
                <li key={p.title} className="rounded-soft-lg border border-line bg-surface p-6">
                  <h3 className="text-lg font-semibold">{p.title}</h3>
                  <p className="mt-2 text-base text-ink-2">{p.body}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section aria-labelledby="kapanis-h" className="border-t border-line py-16 lg:py-24">
          <div className={`${wrap} flex flex-col items-start gap-6`}>
            <h2 id="kapanis-h" className={h2}>
              Demoyu sentetik verilerle dene
            </h2>
            <LinkButton to="/login" className="w-full sm:w-auto">
              Demoyu aç
            </LinkButton>
          </div>
        </section>
      </main>

      <footer className="border-t border-line py-8">
        <div className={`${wrap} flex flex-col gap-2 text-sm text-ink-2 sm:flex-row sm:justify-between`}>
          <p>InnerSpace · portföy projesi. Gerçek kişisel veya sağlık bilgisi girme.</p>
          <p>Tıbbi tavsiye vermez; teşhis veya tedavi aracı değildir.</p>
          <a href={REPO_URL} className="link" rel="noreferrer">
            Kaynak kod (GitHub)
          </a>
        </div>
      </footer>
    </div>
  )
}
