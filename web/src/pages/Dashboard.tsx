import { useEffect, useState } from 'react'
import { Link, useNavigate, useOutletContext } from 'react-router-dom'
import {
  enroll, listEpisodes, createEpisode, episodeState, listDocuments, concepts,
  openSession, type Episode, type Doc, type Concepts,
} from '../api'
import { KINDS, STATES, t } from '../ui'

interface ShellCtx { needEnroll: boolean; onEnrolled: () => void }

// Явный шаг выпуска ключей — плиткой на «Сегодня» (не отдельным экраном-тупиком):
// навигация и чужие карты доступны и без своей.
function EnrollTile({ onEnrolled }: { onEnrolled: () => void }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const start = async () => {
    setBusy(true); setErr('')
    try {
      await enroll()
      await openSession()
      onEnrolled()
    } catch (e) { setErr((e as Error).message); setBusy(false) }
  }
  return (
    <section className="tile" style={{ gridColumn: '1 / -1' }}>
      <header><h3>Ваши данные — под псевдонимом</h3></header>
      <p className="muted">Медицинские записи хранятся отдельно от вашего имени —
      под случайным псевдонимом; связывает их только зашифрованный мост, ключ от
      которого принадлежит вам. Доверенные лица получают доступ только по вашему
      согласию, экстренный доступ — по протоколу «двух подтверждений» с уведомлением.</p>
      {err && <p className="error">{err}</p>}
      <button onClick={start} disabled={busy}>
        {busy ? 'Выпускаю ключи…' : 'Выпустить ключи и завести карту'}
      </button>
    </section>
  )
}

// available пуст -> маршрут завершён: эпизод уходит в «Историю болезни»
interface EpisodeRow extends Episode { fsm?: string; closed?: boolean }

function EpisodeLink({ ep }: { ep: EpisodeRow }) {
  return (
    <Link to={`/episode/${ep.id}`} className="row-link">
      <span>{ep.name || ep.code}</span>
      {ep.fsm && <span className="chip state">{t(STATES, ep.fsm)}</span>}
      <span className="muted">{new Date(ep.begins).toLocaleDateString()}</span>
    </Link>
  )
}

// Дашборд «Сегодня»: сетка плиток-трекеров. Эпизоды — первая плитка;
// сон/нагрузки/питание зарезервированы пунктиром (перспектива, сетка не меняется).
export default function Dashboard() {
  const nav = useNavigate()
  const { needEnroll, onEnrolled } = useOutletContext<ShellCtx>()
  const [eps, setEps] = useState<EpisodeRow[]>([])
  const [docs, setDocs] = useState<Doc[]>([])
  const [cs, setCs] = useState<Concepts>({})
  const [err, setErr] = useState('')
  const [creating, setCreating] = useState(false)

  const load = async () => {
    try {
      const list = await listEpisodes()
      // состояние каждого эпизода — параллельно; упавшие не роняют дашборд
      const states = await Promise.allSettled(list.map((e) => episodeState(e.id)))
      setEps(list.map((e, i) => {
        const st = states[i]
        return st.status === 'fulfilled'
          ? { ...e, fsm: st.value.state, closed: st.value.available.length === 0 }
          : { ...e }
      }))
      setDocs((await listDocuments()).slice(-3).reverse())
    } catch (e) { setErr((e as Error).message) }
  }
  useEffect(() => {
    if (needEnroll) return   // карты ещё нет — грузить нечего
    concepts().then((c) => {
      setCs(c)
      if (Object.keys(c).length === 0)
        setErr('Справочник пуст — на сервере не прогнан медицинский сид ' +
               '(uv run python scripts/bootstrap_dev.py)')
    }).catch((e) => setErr((e as Error).message))
    load()
  }, [needEnroll])

  // эпизод открывается жалобой, а не диагнозом: имени пока нет — авто по дате;
  // назвать можно на странице эпизода, когда диагноз поставлен
  const create = async (kind: string) => {
    setErr('')
    const cat = cs[kind]
    if (!cat) return
    try {
      const auto = `${t(KINDS, kind)} от ${new Date().toLocaleDateString()}`
      const ep = await createEpisode(cat, `ep-${Date.now()}`,
        auto[0].toUpperCase() + auto.slice(1))
      nav(`/episode/${ep.id}`)
    } catch (e) { setErr((e as Error).message) }
  }

  const active = eps.filter((e) => !e.closed)
  const closed = eps.filter((e) => e.closed)

  if (needEnroll) {
    return <div className="tiles"><EnrollTile onEnrolled={onEnrolled} /></div>
  }

  return (
    <div className="tiles">
      {err && <p className="error" style={{ gridColumn: '1 / -1' }}>{err}</p>}

      <section className="tile">
        <header><h3>Эпизоды</h3>
          <button className="ghost" onClick={() => setCreating(!creating)}
                  disabled={!Object.keys(cs).length}>
            {creating ? 'Отмена' : '+ Новый'}
          </button>
        </header>
        {creating && (
          <div className="inline">
            <span className="muted">Что случилось?</span>
            {Object.entries(KINDS).map(([k, label]) => (
              <button key={k} onClick={() => create(k)}>{label}</button>
            ))}
          </div>
        )}
        {active.length === 0 && !creating &&
          <p className="muted">Сейчас ничего не беспокоит. Заболели или травма — откройте эпизод.</p>}
        <ul className="rows">
          {active.map((ep) => <li key={ep.id}><EpisodeLink ep={ep} /></li>)}
        </ul>
        {closed.length > 0 && (
          <details className="log">
            <summary>История болезни ({closed.length})</summary>
            <ul className="rows">
              {closed.map((ep) => <li key={ep.id}><EpisodeLink ep={ep} /></li>)}
            </ul>
          </details>
        )}
      </section>

      <section className="tile">
        <header><h3>Документы</h3></header>
        {docs.length === 0 && <p className="muted">Анализы и выписки — на странице эпизода.</p>}
        <ul className="rows">
          {docs.map((d) => (
            <li key={d.id} className="row-link">
              <span>{d.name || d.code}</span>
              <span className="muted">{new Date(d.begins).toLocaleDateString()}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* перспектива: те же плитки, данные подключатся новыми концептами ядра */}
      <section className="tile future"><header><h3>Сон</h3></header><p>скоро</p></section>
      <section className="tile future"><header><h3>Нагрузки</h3></header><p>скоро</p></section>
      <section className="tile future"><header><h3>Питание</h3></header><p>скоро</p></section>
    </div>
  )
}
