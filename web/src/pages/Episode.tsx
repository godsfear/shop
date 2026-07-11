import { useEffect, useState, type FormEvent } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  getEpisode, renameEpisode, episodeHistory, episodeState, transition, assess,
  episodeProperties, addEpisodeProperty, listDocuments, uploadDocument, concepts,
  type Episode as Ep, type FsmState, type Assess, type MedProperty, type Doc,
  type Concepts, type StateLog,
} from '../api'
import { EVENTS, SECTIONS, STATES, t } from '../ui'

// Таймлайн жизненного цикла: полный маршрут из fsm.states, текущее — акцентом
function Timeline({ fsm }: { fsm: FsmState }) {
  const cur = fsm.states.indexOf(fsm.state)
  return (
    <div className="timeline">
      {fsm.states.map((st, i) => (
        <span key={st}
              className={'st' + (i < cur ? ' done' : '') + (i === cur ? ' cur' : '')}>
          {t(STATES, st)}
        </span>
      ))}
    </div>
  )
}

export default function Episode() {
  const { id = '' } = useParams()
  const [ep, setEp] = useState<Ep | null>(null)
  const [cs, setCs] = useState<Concepts>({})
  const [fsm, setFsm] = useState<FsmState | null>(null)
  const [symptoms, setSymptoms] = useState<MedProperty[]>([])
  const [docs, setDocs] = useState<Doc[]>([])
  const [log, setLog] = useState<StateLog[]>([])
  const [a, setA] = useState<Assess | null>(null)
  const [err, setErr] = useState('')
  const [renaming, setRenaming] = useState(false)
  const [newName, setNewName] = useState('')

  // форма симптома
  const [symCode, setSymCode] = useState('')
  const [symStatus, setSymStatus] = useState('present')
  // форма документа
  const [file, setFile] = useState<File | null>(null)
  const [docName, setDocName] = useState('')

  const reload = async () => {
    try {
      setEp(await getEpisode(id))
      setFsm(await episodeState(id))
      setSymptoms(await episodeProperties(id, cs['symptom']))
      setDocs(await listDocuments(id))
      setLog(await episodeHistory(id))
      setA(await assess(id))
    } catch (e) { setErr((e as Error).message) }
  }
  useEffect(() => { concepts().then(setCs).catch(() => {}) }, [])
  // перезагрузка данных, когда стали известны концепты (нужен id категории симптома)
  useEffect(() => { if (id) reload() }, [id, cs['symptom']])

  const fire = async (event: string) => {
    setErr('')
    try {
      setFsm(await transition(id, event))
      setA(await assess(id))
      setLog(await episodeHistory(id))
    } catch (e) { setErr((e as Error).message) }
  }

  const rename = async () => {
    setErr('')
    try {
      setEp(await renameEpisode(id, newName.trim()))
      setRenaming(false)
    } catch (e) { setErr((e as Error).message) }
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
      <p><Link to="/">← сегодня</Link></p>
      {renaming ? (
        <div className="inline">
          <input value={newName} autoFocus placeholder="диагноз / название"
                 onChange={(e) => setNewName(e.target.value)} />
          <button onClick={rename} disabled={!newName.trim()}>Сохранить</button>
          <button className="ghost" onClick={() => setRenaming(false)}>Отмена</button>
        </div>
      ) : (
        <h2>{ep?.name || ep?.code || 'Эпизод'}{' '}
          <button className="ghost small"
                  onClick={() => { setNewName(ep?.name ?? ''); setRenaming(true) }}>
            переименовать
          </button>
        </h2>
      )}
      {err && <p className="error">{err}</p>}

      <section>
        {fsm && <Timeline fsm={fsm} />}
        <div className="inline">
          {fsm?.available.map((ev) => (
            <button key={ev} onClick={() => fire(ev)}>{t(EVENTS, ev)}</button>
          ))}
          {fsm && fsm.available.length === 0 && <span className="muted">маршрут завершён</span>}
        </div>
        {log.length > 0 && (
          <details className="log">
            <summary>Журнал ({log.length})</summary>
            <ul className="rows">
              {log.map((r, i) => (
                <li key={i} className="row-link">
                  <span>{t(STATES, r.state)}</span>
                  {r.event && <span className="muted">← {t(EVENTS, r.event).toLowerCase()}</span>}
                  <span className="muted">{new Date(r.begins).toLocaleString()}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>

      <section>
        <h3>Полнота и красные флаги</h3>
        {a?.alerts.map((x) => <p key={x} className="alert">⚠ красный флаг: {x}</p>)}
        {a && a.gaps.length > 0 &&
          <p className="muted">не заполнено: {a.gaps.map((g) => t(SECTIONS, g)).join(', ')}</p>}
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
