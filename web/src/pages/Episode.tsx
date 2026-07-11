import { useEffect, useState, type FormEvent } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  episodeState, transition, assess, episodeProperties, addEpisodeProperty,
  listDocuments, uploadDocument, concepts,
  type FsmState, type Assess, type MedProperty, type Doc, type Concepts,
} from '../api'

export default function Episode() {
  const { id = '' } = useParams()
  const [cs, setCs] = useState<Concepts>({})
  const [fsm, setFsm] = useState<FsmState | null>(null)
  const [symptoms, setSymptoms] = useState<MedProperty[]>([])
  const [docs, setDocs] = useState<Doc[]>([])
  const [a, setA] = useState<Assess | null>(null)
  const [err, setErr] = useState('')

  // форма симптома
  const [symCode, setSymCode] = useState('')
  const [symStatus, setSymStatus] = useState('present')
  // форма документа
  const [file, setFile] = useState<File | null>(null)
  const [docName, setDocName] = useState('')

  const reload = async () => {
    try {
      setFsm(await episodeState(id))
      setSymptoms(await episodeProperties(id, cs['symptom']))
      setDocs(await listDocuments(id))
      setA(await assess(id))
    } catch (e) { setErr((e as Error).message) }
  }
  useEffect(() => { concepts().then(setCs).catch(() => {}) }, [])
  // перезагрузка данных, когда стали известны концепты (нужен id категории симптома)
  useEffect(() => { if (id) reload() }, [id, cs['symptom']])

  const fire = async (event: string) => {
    setErr('')
    try { setFsm(await transition(id, event)); setA(await assess(id)) }
    catch (e) { setErr((e as Error).message) }
  }

  const addSymptom = async (e: FormEvent) => {
    e.preventDefault()
    setErr('')
    if (!symCode) return
    try {
      await addEpisodeProperty(id, {
        category: cs['symptom'], code: symCode,
        value: { status: symStatus, source: 'self' },
      })
      setSymCode('')
      await reload()
    } catch (e) { setErr((e as Error).message) }
  }

  const upload = async (e: FormEvent) => {
    e.preventDefault()
    setErr('')
    if (!file) return
    try {
      await uploadDocument(file, docName || file.name, 'doc', cs['analysis'], id)
      setFile(null); setDocName('')
      await reload()  // ИИ-разбор идёт асинхронно (outbox) — находки появятся позже
    } catch (e) { setErr((e as Error).message) }
  }

  return (
    <div>
      <p><Link to="/">← эпизоды</Link></p>
      <h2>Эпизод</h2>
      {err && <p className="error">{err}</p>}

      <section>
        <h3>Состояние: <b>{fsm?.state ?? '…'}</b></h3>
        <div className="inline">
          {fsm?.available.map((ev) => (
            <button key={ev} onClick={() => fire(ev)}>{ev}</button>
          ))}
          {fsm && fsm.available.length === 0 && <span className="muted">переходов нет</span>}
        </div>
      </section>

      <section>
        <h3>Полнота и красные флаги</h3>
        {a?.alerts.map((x) => <p key={x} className="alert">⚠ красный флаг: {x}</p>)}
        {a && a.gaps.length > 0 && <p className="muted">не заполнено: {a.gaps.join(', ')}</p>}
        {a && a.alerts.length === 0 && a.gaps.length === 0 && <p className="muted">всё заполнено, флагов нет</p>}
      </section>

      <section>
        <h3>Симптомы</h3>
        <form className="inline" onSubmit={addSymptom}>
          <input placeholder="код (напр. chest_pain)" value={symCode}
                 onChange={(e) => setSymCode(e.target.value)} />
          <select value={symStatus} onChange={(e) => setSymStatus(e.target.value)}>
            <option value="present">есть</option>
            <option value="absent">нет</option>
            <option value="unknown">неизвестно</option>
          </select>
          <button type="submit">Добавить</button>
        </form>
        <ul className="cards">
          {symptoms.map((s) => (
            <li key={s.id} className="card">
              <b>{s.code}</b> — {String((s.value as { status?: string }).status ?? '')}
              <span className="muted"> ({String((s.value as { source?: string }).source ?? '')})</span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3>Документы</h3>
        <form className="inline" onSubmit={upload}>
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <input placeholder="название" value={docName}
                 onChange={(e) => setDocName(e.target.value)} />
          <button type="submit">Загрузить</button>
        </form>
        <p className="muted">После загрузки ИИ разбирает документ в фоне — находки появятся среди симптомов/находок.</p>
        <ul className="cards">
          {docs.map((d) => (
            <li key={d.id} className="card">{d.name || d.code}
              <span className="muted"> · {d.hash.slice(0, 12)}…</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
