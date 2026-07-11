import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import {
  listEpisodes, createEpisode, episodeState, listDocuments, concepts,
  type Episode, type Doc, type Concepts,
} from '../api'
import { KINDS, STATES, t } from '../ui'

interface EpisodeRow extends Episode { fsm?: string }

// Дашборд «Сегодня»: сетка плиток-трекеров. Эпизоды — первая плитка;
// сон/нагрузки/питание зарезервированы пунктиром (перспектива, сетка не меняется).
export default function Dashboard() {
  const [eps, setEps] = useState<EpisodeRow[]>([])
  const [docs, setDocs] = useState<Doc[]>([])
  const [cs, setCs] = useState<Concepts>({})
  const [err, setErr] = useState('')
  const [creating, setCreating] = useState(false)
  const [kind, setKind] = useState('illness')
  const [name, setName] = useState('')

  const load = async () => {
    try {
      const list = await listEpisodes()
      // состояние каждого эпизода — параллельно; упавшие не роняют дашборд
      const states = await Promise.allSettled(list.map((e) => episodeState(e.id)))
      setEps(list.map((e, i) => ({
        ...e,
        fsm: states[i].status === 'fulfilled'
          ? (states[i] as PromiseFulfilledResult<{ state: string }>).value.state
          : undefined,
      })))
      setDocs((await listDocuments()).slice(-3).reverse())
    } catch (e) { setErr((e as Error).message) }
  }
  useEffect(() => { concepts().then(setCs).catch(() => {}); load() }, [])

  const create = async (e: FormEvent) => {
    e.preventDefault()
    setErr('')
    const cat = cs[kind]
    if (!cat) { setErr('справочник ещё загружается — секунду'); return }
    try {
      await createEpisode(cat, `ep-${Date.now()}`, name || 'Без названия')
      setName(''); setCreating(false)
      await load()
    } catch (e) { setErr((e as Error).message) }
  }

  return (
    <div className="tiles">
      {err && <p className="error">{err}</p>}

      <section className="tile">
        <header><h3>Эпизоды</h3>
          <button className="ghost" onClick={() => setCreating(!creating)}>
            {creating ? 'Отмена' : '+ Новый'}
          </button>
        </header>
        {creating && (
          <form className="inline" onSubmit={create}>
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              {Object.entries(KINDS).map(([k, label]) =>
                <option key={k} value={k}>{label}</option>)}
            </select>
            <input placeholder="название (напр. ОРВИ)" value={name} autoFocus
                   onChange={(e) => setName(e.target.value)} />
            <button type="submit">Открыть</button>
          </form>
        )}
        {eps.length === 0 && !creating &&
          <p className="muted">Пока пусто. Заболели или травма — откройте эпизод.</p>}
        <ul className="rows">
          {eps.map((ep) => (
            <li key={ep.id}>
              <Link to={`/episode/${ep.id}`} className="row-link">
                <span>{ep.name || ep.code}</span>
                {ep.fsm && <span className="chip state">{t(STATES, ep.fsm)}</span>}
                <span className="muted">{new Date(ep.begins).toLocaleDateString()}</span>
              </Link>
            </li>
          ))}
        </ul>
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
