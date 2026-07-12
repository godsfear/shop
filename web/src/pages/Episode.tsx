import { useEffect, useState, type FormEvent } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  getEpisode, renameEpisode, episodeHistory, episodeState, transition, assess,
  episodeProperties, addEpisodeProperty, listDocuments, uploadDocument, concepts,
  evaluateEpisode,
  type Episode as Ep, type FsmState, type Assess, type MedProperty, type Doc,
  type Concepts, type StateLog,
} from '../api'

interface Ddx {
  assessments: { condition: string; likelihood: number; rationale: string }[]
  urgent: boolean; note?: string
}
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
  const [finds, setFinds] = useState<MedProperty[]>([])   // находки ИИ (source=ai)
  const [docs, setDocs] = useState<Doc[]>([])
  const [log, setLog] = useState<StateLog[]>([])
  const [a, setA] = useState<Assess | null>(null)
  const [err, setErr] = useState('')
  const [renaming, setRenaming] = useState(false)
  const [newName, setNewName] = useState('')
  const [parsing, setParsing] = useState(false)           // документ в ИИ-разборе
  const [ddx, setDdx] = useState<MedProperty | null>(null)  // ИИ-оценка (code=ddx)
  const [evaluating, setEvaluating] = useState(false)

  // форма симптома
  const [symCode, setSymCode] = useState('')
  const [symStatus, setSymStatus] = useState('present')
  // форма документа
  const [file, setFile] = useState<File | null>(null)
  const [docName, setDocName] = useState('')

  const isAi = (p: MedProperty) => (p.value as { source?: string }).source === 'ai'

  const reload = async () => {
    try {
      setEp(await getEpisode(id))
      setFsm(await episodeState(id))
      const props = await episodeProperties(id)
      setSymptoms(props.filter((p) => p.category === cs['symptom'] && !isAi(p)))
      setFinds(props.filter((p) => isAi(p) && p.code !== 'ddx'))
      setDdx(props.find((p) => p.code === 'ddx') ?? null)
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

  const evaluate = async () => {
    setErr(''); setEvaluating(true)
    const before = ddx?.begins
    try {
      await evaluateEpisode(id)
      // оценка идёт в фоне (outbox -> ИИ): ждём новую/обновлённую запись ddx
      for (let i = 0; i < 10; i++) {
        await new Promise((r) => setTimeout(r, 2000))
        const props = await episodeProperties(id)
        const fresh = props.find((p) => p.code === 'ddx')
        if (fresh && fresh.begins !== before) { setDdx(fresh); break }
      }
    } catch (e) { setErr((e as Error).message) }
    finally { setEvaluating(false) }
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
      await reload()
      // ИИ-разбор идёт в фоне (outbox): опрашиваем находки, пока не появятся
      setParsing(true)
      const before = finds.length
      for (let i = 0; i < 5; i++) {
        await new Promise((r) => setTimeout(r, 2000))
        const props = await episodeProperties(id)
        const ai = props.filter(isAi)
        if (ai.length > before) { setFinds(ai); break }
      }
      setParsing(false)
      await reload()
    } catch (e) { setErr((e as Error).message); setParsing(false) }
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
          {/* сбор анамнеза — основной путь на этапе «анамнез» */}
          {fsm?.state === 'anamnesis' &&
            <Link to={`/episode/${id}/interview`}><button>Пройти опрос (анамнез)</button></Link>}
          {fsm && fsm.state !== 'anamnesis' &&
            <Link to={`/episode/${id}/interview`} className="muted">интервью</Link>}
          {fsm?.available.map((ev) => (
            <button key={ev} className={fsm.state === 'anamnesis' ? 'ghost' : ''}
                    onClick={() => fire(ev)}>{t(EVENTS, ev)}</button>
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
        <h3>Оценка ИИ</h3>
        <div className="inline">
          {/* оценка по неполному анамнезу вводит в заблуждение — сначала опрос */}
          <button onClick={evaluate} disabled={evaluating || !a || a.gaps.length > 0}>
            {evaluating ? 'ИИ анализирует…' : (ddx ? 'Оценить заново' : 'Собрать и оценить (ИИ)')}
          </button>
          <span className="muted">
            {a && a.gaps.length > 0
              ? 'станет доступно после сбора анамнеза — пройдите опрос'
              : 'все данные эпизода и карты уйдут ИИ одной задачей'}
          </span>
        </div>
        {ddx && (() => {
          const v = ddx.value as unknown as Ddx
          return (
            <div className="card resume">
              {v.urgent && <p className="alert">⚠ Данные указывают на возможное угрожающее
                состояние — не откладывайте обращение за помощью.</p>}
              <ol className="ddx">
                {v.assessments.map((x, i) => (
                  <li key={i}>
                    <b>{x.condition}</b>
                    <span className="chip state">{Math.round(x.likelihood * 100)}%</span>
                    <div className="muted">{x.rationale}</div>
                  </li>
                ))}
              </ol>
              {v.note && <p className="muted">{v.note}</p>}
              <p className="muted disclaimer">Предварительная оценка ИИ — не диагноз
              и не заменяет осмотр врача. Обсудите результат со специалистом.</p>
            </div>
          )
        })()}
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
        <h3>Документы и находки ИИ</h3>
        <form className="inline" onSubmit={upload}>
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <input placeholder="название" value={docName}
                 onChange={(e) => setDocName(e.target.value)} />
          <button type="submit" disabled={!file || parsing}>Загрузить</button>
        </form>
        {parsing && <p className="muted parsing">ИИ разбирает документ…</p>}
        <ul className="cards">
          {docs.map((d) => (
            <li key={d.id} className="card">{d.name || d.code}
              <span className="muted"> · {new Date(d.begins).toLocaleDateString()}</span>
            </li>
          ))}
        </ul>
        {finds.length > 0 && (
          <ul className="cards">
            {finds.map((f) => {
              const v = f.value as { kind?: string; text?: string; value?: string; unit?: string }
              return (
                <li key={f.id} className="card find">
                  <span className="chip state">ИИ</span> <b>{f.code}</b>
                  {v.kind && <span className="muted"> · {v.kind}</span>}
                  {v.text && <div className="muted">{v.text}</div>}
                  {v.value && <div>{v.value} {v.unit ?? ''}</div>}
                </li>
              )
            })}
          </ul>
        )}
      </section>
    </div>
  )
}
