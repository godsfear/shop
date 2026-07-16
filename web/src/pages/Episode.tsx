import { useEffect, useState, type FormEvent } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  getEpisode, renameEpisode, episodeHistory, episodeState, transition, assess,
  episodeProperties, listDocuments, uploadDocument, concepts, dictionary,
  evaluateEpisode,
  type Episode as Ep, type FsmState, type Assess, type MedProperty, type Doc,
  type Concepts, type StateLog,
} from '../api'

interface Ddx {
  assessments: { condition: string; likelihood: number; rationale: string }[]
  urgent: boolean; note?: string; docs?: number
}
interface Workup { tests: { test: string; reason: string }[] }
import { EVENTS, RED_FLAGS, SECTIONS, STATES, t } from '../ui'

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
  const [ddx, setDdx] = useState<MedProperty | null>(null)  // ИИ-оценка (code=ddx)
  const [workup, setWorkup] = useState<MedProperty | null>(null)  // рекоменд. анализы (code=workup)
  const [hasSummary, setHasSummary] = useState(false)     // интервью подтверждено
  const [workupPending, setWorkupPending] = useState(false)
  const [evaluating, setEvaluating] = useState(false)

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
      setFinds(props.filter((p) => isAi(p) && p.code !== 'ddx' && p.code !== 'workup'))
      setDdx(props.find((p) => p.code === 'ddx') ?? null)
      setWorkup(props.find((p) => p.code === 'workup') ?? null)
      setHasSummary(props.some((p) => p.code === 'summary'))  // интервью подтверждено
      setDocs(await listDocuments(id))
      setLog(await episodeHistory(id))
      setA(await assess(id))
    } catch (e) { setErr((e as Error).message) }
  }
  // код жалобы -> русское имя из справочника (существующие записи хранят код)
  const [symNames, setSymNames] = useState<Record<string, string>>({})
  useEffect(() => {
    concepts().then(setCs).catch(() => {})
    dictionary('symptom').then((d) =>
      setSymNames(Object.fromEntries(d.map((x) => [x.code, x.name])))).catch(() => {})
  }, [])
  // перезагрузка данных, когда стали известны концепты (нужен id категории симптома)
  useEffect(() => { if (id) reload() }, [id, cs['symptom']])

  // рекомендация анализов генерится в фоне (шина) после подтверждения интервью —
  // если резюме уже есть, а workup ещё нет, коротко опрашиваем, пока не придёт
  useEffect(() => {
    if (!hasSummary || workup) return
    let stop = false
    setWorkupPending(true)
    ;(async () => {
      for (let i = 0; i < 8 && !stop; i++) {
        await new Promise((r) => setTimeout(r, 2500))
        const w = (await episodeProperties(id)).find((p) => p.code === 'workup')
        if (w) { setWorkup(w); break }
      }
      if (!stop) setWorkupPending(false)
    })()
    return () => { stop = true }
  }, [hasSummary, workup, id])

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

  const upload = async (e: FormEvent) => {
    e.preventDefault()
    setErr('')
    if (!file) return
    try {
      // документ читается ИИ при нажатии «Диагноз» (оригинал мультимодально),
      // не разбирается при загрузке — просто сохраняем и показываем в списке
      await uploadDocument(file, docName || file.name, 'doc', cs['analysis'], id)
      setFile(null); setDocName('')
      await reload()
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

      {/* показывается, только когда есть что дополнить или тревога */}
      {a && (a.alerts.length > 0 || a.gaps.length > 0) && (
        <section>
          <h3>Стоит дополнить</h3>
          {a.alerts.map((x) => <p key={x} className="alert">
            ⚠ Признак возможного угрожающего состояния ({t(RED_FLAGS, x)}) — не откладывайте
            обращение за помощью.</p>)}
          {a.gaps.length > 0 &&
            <p className="muted">Рассказ пока неполон: {a.gaps.map((g) => t(SECTIONS, g).toLocaleLowerCase()).join(', ')}.
            Быстрее всего — пройти опрос.</p>}
        </section>
      )}

      {/* рекомендованные анализы — ИИ подбирает автоматически после анамнеза */}
      {workup && (() => {
        const w = workup.value as unknown as Workup
        if (!w.tests?.length) return null
        return (
          <section>
            <h3>Рекомендованные анализы</h3>
            <p className="muted">ИИ предлагает сдать для уточнения. Загрузите
            результаты ниже — они войдут в диагноз.</p>
            <ul className="cards">
              {w.tests.map((x, i) => (
                <li key={i} className="card">
                  <b>{x.test}</b>
                  <div className="muted">{x.reason}</div>
                </li>
              ))}
            </ul>
          </section>
        )
      })()}

      {/* анализы ещё подбираются (шина обрабатывает событие после подтверждения) */}
      {!workup && workupPending && (
        <section>
          <h3>Рекомендованные анализы</h3>
          <p className="muted parsing">ИИ подбирает анализы по анамнезу…</p>
        </section>
      )}

      <section>
        <h3>Диагноз (оценка ИИ)</h3>
        <div className="inline">
          {/* диагноз по неполному анамнезу вводит в заблуждение — сначала опрос */}
          <button onClick={evaluate} disabled={evaluating || !a || a.gaps.length > 0}>
            {evaluating ? 'ИИ анализирует…' : (ddx ? 'Пересчитать диагноз' : 'Диагноз')}
          </button>
          <span className="muted">
            {a && a.gaps.length > 0
              ? 'станет доступно после сбора анамнеза — пройдите опрос'
              : 'анамнез и оригиналы загруженных документов уйдут ИИ одной задачей'}
          </span>
        </div>
        {/* мягкое предупреждение о неполноте: рекомендованы анализы, но документов нет */}
        {workup && (workup.value as unknown as Workup).tests?.length > 0 && docs.length === 0 &&
          <p className="muted">Рекомендованные анализы ещё не загружены — оценка
          будет менее точной.</p>}
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

      {/* жалобы вносятся опросом (анамнез) — ручного ввода кодов нет */}
      {symptoms.length > 0 && (
        <section>
          <h3>Жалобы</h3>
          <ul className="cards">
            {symptoms.map((s) => (
              <li key={s.id} className="card">
                <b>{s.name || symNames[s.code] || s.code}</b>
                {(s.value as { status?: string }).status === 'absent' &&
                  <span className="muted"> — отсутствует (значимо)</span>}
                <span className="muted"> · {String((s.value as { source?: string }).source ?? '')}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h3>Документы</h3>
        <p className="muted">Результаты анализов и обследований. Читаются ИИ при
        нажатии «Диагноз» (оригиналы), не разбираются при загрузке.</p>
        <form className="inline" onSubmit={upload}>
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <input placeholder="название" value={docName}
                 onChange={(e) => setDocName(e.target.value)} />
          <button type="submit" disabled={!file}>Загрузить</button>
        </form>
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
