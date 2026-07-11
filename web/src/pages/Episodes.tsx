import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { listEpisodes, createEpisode, concepts, type Episode, type Concepts } from '../api'

export default function Episodes() {
  const [eps, setEps] = useState<Episode[]>([])
  const [cs, setCs] = useState<Concepts>({})
  const [name, setName] = useState('')
  const [kind, setKind] = useState('illness')
  const [err, setErr] = useState('')

  const load = async () => {
    try { setEps(await listEpisodes()) } catch (e) { setErr((e as Error).message) }
  }
  useEffect(() => { concepts().then(setCs).catch(() => {}); load() }, [])

  const create = async (e: FormEvent) => {
    e.preventDefault()
    setErr('')
    const cat = cs[kind]
    if (!cat) { setErr('концепты ещё не загружены'); return }
    try {
      await createEpisode(cat, `ep-${Date.now()}`, name || 'Без названия')
      setName('')
      await load()
    } catch (e) { setErr((e as Error).message) }
  }

  return (
    <div>
      <h2>Эпизоды</h2>
      {err && <p className="error">{err}</p>}
      <form className="inline" onSubmit={create}>
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="illness">болезнь</option>
          <option value="injury">травма</option>
        </select>
        <input placeholder="название (напр. ОРВИ)" value={name}
               onChange={(e) => setName(e.target.value)} />
        <button type="submit">Открыть эпизод</button>
      </form>

      {eps.length === 0 && <p className="muted">Эпизодов пока нет.</p>}
      <ul className="cards">
        {eps.map((ep) => (
          <li key={ep.id} className="card">
            <Link to={`/episode/${ep.id}`}>{ep.name || ep.code}</Link>
            <span className="muted"> · {new Date(ep.begins).toLocaleDateString()}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
