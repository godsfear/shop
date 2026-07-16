import { useEffect, useState, type FormEvent } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  getEpisode, renameEpisode, episodeHistory, episodeState, transition, assess,
  episodeProperties, listDocuments, uploadDocument, concepts, dictionary,
  evaluateEpisode, addEpisodeProperty,
  type Episode as Ep, type FsmState, type Assess, type MedProperty, type Doc,
  type Concepts, type StateLog, type DictItem,
} from '../api'

interface Ddx {
  assessments: { condition: string; likelihood: number; rationale: string }[]
  urgent: boolean; note?: string; docs?: number
}
interface WorkupTest { code?: string; test: string; reason: string; self?: boolean }
interface Workup { tests: WorkupTest[] }
import { EVENTS, RED_FLAGS, SECTIONS, SLOTS, STATES, UNITS, t } from '../ui'
import { ui } from '../i18n'

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
  const [summary, setSummary] = useState<MedProperty | null>(null)  // резюме анамнеза
  const [workupPending, setWorkupPending] = useState(false)
  const [evaluating, setEvaluating] = useState(false)

  // форма документа
  const [file, setFile] = useState<File | null>(null)
  const [docName, setDocName] = useState('')

  const isAi = (p: MedProperty) => (p.value as { source?: string }).source === 'ai'

  // результаты, внесённые пациентом вручную (самостоятельные пробы и т.п.)
  const [results, setResults] = useState<MedProperty[]>([])
  // дневник симптомов: замеры в моменте (температура/давление/пульс)
  const [diary, setDiary] = useState<MedProperty[]>([])
  const [diaryDict, setDiaryDict] = useState<DictItem[]>([])
  const [dCode, setDCode] = useState('')
  const [dVal, setDVal] = useState('')

  const reload = async () => {
    try {
      setEp(await getEpisode(id))
      setFsm(await episodeState(id))
      const props = await episodeProperties(id)
      setSymptoms(props.filter((p) => p.category === cs['symptom'] && !isAi(p)))
      setFinds(props.filter((p) => isAi(p) && p.code !== 'ddx' && p.code !== 'workup'))
      setResults(props.filter((p) =>
        (p.value as { source?: string; result?: string }).source === 'patient'
        && (p.value as { result?: string }).result !== undefined))
      setDiary(props.filter((p) => p.category === cs['vital'] && !isAi(p))
        .sort((a, b) => b.begins.localeCompare(a.begins)))
      setDdx(props.find((p) => p.code === 'ddx') ?? null)
      setWorkup(props.find((p) => p.code === 'workup') ?? null)
      const sum = props.find((p) => p.code === 'summary') ?? null
      setSummary(sum)
      setHasSummary(sum !== null)                             // интервью подтверждено
      setDocs(await listDocuments(id))
      setLog(await episodeHistory(id))
      setA(await assess(id))
    } catch (e) { setErr((e as Error).message) }
  }
  // код жалобы -> русское имя из справочника (существующие записи хранят код)
  const [symNames, setSymNames] = useState<Record<string, string>>({})
  useEffect(() => {
    concepts().then(setCs).catch(() => {})
    // symptom + system: имена жалоб и систем (резюме анамнеза, ROS)
    Promise.all([dictionary('symptom'), dictionary('system')]).then(([a, b]) =>
      setSymNames(Object.fromEntries([...a, ...b].map((x) => [x.code, x.name])))).catch(() => {})
    dictionary('vital').then(setDiaryDict).catch(() => {})
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

  // --- действия по конкретному рекомендованному анализу -----------------
  const [resFor, setResFor] = useState<string | null>(null)  // test, для которого открыт ввод
  const [resText, setResText] = useState('')

  // текстовый результат = свойство эпизода (concept=analysis, source=patient);
  // войдёт в диагноз вместе с анамнезом — документ для домашних проб не нужен.
  // Ключ связи с рекомендацией — стабильный code из ответа ИИ (переживает
  // пересчёт workup); для старых ответов без кода — название.
  const saveResult = async (x: WorkupTest) => {
    setErr('')
    try {
      await addEpisodeProperty(id, {
        category: cs['analysis'], code: x.code ?? `res-${Date.now()}`, name: x.test,
        value: { code: x.code, test: x.test, result: resText.trim(), source: 'patient' },
      })
      setResFor(null); setResText('')
      await reload()
    } catch (e) { setErr((e as Error).message) }
  }

  // документ по конкретному анализу: code/имя документа = код/название анализа
  const uploadFor = async (x: WorkupTest, f: File | null) => {
    if (!f) return
    setErr('')
    try {
      await uploadDocument(f, x.test, x.code ?? 'doc', cs['analysis'], id)
      await reload()
    } catch (e) { setErr((e as Error).message) }
  }

  // выполнен ли рекомендованный анализ: по коду, иначе по названию
  const matches = (code: string | null, name: string | null, x: WorkupTest) =>
    (x.code != null && code === x.code) || name === x.test

  // запись дневника — обычное свойство эпизода (concept=vital, source=diary):
  // ИИ получает её в бандле с отметкой времени, отдельного носителя не нужно
  const addDiary = async () => {
    if (!dCode || !dVal.trim()) return
    setErr('')
    try {
      const names = new Map(diaryDict.map((d) => [d.code, d.name]))
      await addEpisodeProperty(id, {
        category: cs['vital'], code: dCode, name: names.get(dCode),
        value: { value: dVal.trim(), unit: ui(UNITS[dCode] ?? ''), source: 'diary' },
      })
      setDVal('')
      await reload()
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
      <p><Link to="/">{ui('← сегодня')}</Link></p>
      {renaming ? (
        <div className="inline">
          <input value={newName} autoFocus placeholder={ui('диагноз / название')}
                 onChange={(e) => setNewName(e.target.value)} />
          <button onClick={rename} disabled={!newName.trim()}>{ui('Сохранить')}</button>
          <button className="ghost" onClick={() => setRenaming(false)}>{ui('Отмена')}</button>
        </div>
      ) : (
        <h2>{ep?.name || ep?.code || ui('Эпизод')}{' '}
          <button className="ghost small"
                  onClick={() => { setNewName(ep?.name ?? ''); setRenaming(true) }}>
            {ui('переименовать')}
          </button>
        </h2>
      )}
      {err && <p className="error">{err}</p>}

      <section>
        {fsm && <Timeline fsm={fsm} />}
        <div className="inline">
          {/* сбор анамнеза — основной путь на этапе «анамнез» */}
          {fsm?.state === 'anamnesis' &&
            <Link to={`/episode/${id}/interview`}><button>{ui('Пройти опрос (анамнез)')}</button></Link>}
          {fsm && fsm.state !== 'anamnesis' &&
            <Link to={`/episode/${id}/interview`} className="muted">{ui('интервью')}</Link>}
          {fsm?.available.map((ev) => (
            <button key={ev} className={fsm.state === 'anamnesis' ? 'ghost' : ''}
                    onClick={() => fire(ev)}>{t(EVENTS, ev)}</button>
          ))}
          {fsm && fsm.available.length === 0 && <span className="muted">{ui('маршрут завершён')}</span>}
        </div>
        {log.length > 0 && (
          <details className="log">
            <summary>{ui('Журнал')} ({log.length})</summary>
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
          <h3>{ui('Стоит дополнить')}</h3>
          {a.alerts.map((x) => <p key={x} className="alert">
            ⚠ {ui('Признак возможного угрожающего состояния')} ({t(RED_FLAGS, x)}) {ui('— не откладывайте обращение за помощью.')}</p>)}
          {a.gaps.length > 0 &&
            <p className="muted">{ui('Рассказ пока неполон:')} {a.gaps.map((g) => t(SECTIONS, g).toLocaleLowerCase()).join(', ')}.{' '}
            {ui('Быстрее всего — пройти опрос.')}</p>}
        </section>
      )}

      {/* резюме подтверждённого анамнеза — то, что пациент видел на шаге summary */}
      {summary && (() => {
        const v = summary.value as {
          chief_complaint?: string; symptoms?: Record<string, unknown>
          negatives?: string[]; ros?: Record<string, unknown>
        }
        const nm = (c: string) => symNames[c] ?? c
        const positive = Object.entries(v.ros ?? {}).filter(([, s]) => s !== 'clear')
        return (
          <section>
            <h3>{ui('Анамнез (резюме опроса)')}</h3>
            <div className="card resume">
              <p><b>{ui('Главная жалоба:')}</b> {nm(v.chief_complaint ?? '')}</p>
              {/* развёрнутый анамнез: каждый симптом раскрывается в слоты OPQRST */}
              <p><b>{ui('Симптомы:')}</b></p>
              {Object.entries(v.symptoms ?? {}).map(([c, slots]) => {
                const sl = (slots ?? {}) as Record<string, unknown>
                const fmt = (s: string) => {
                  const val = sl[s]
                  if (Array.isArray(val)) return val.length ? val.map(nm).join(', ') : '—'
                  if (s === 'severity') return `${val}/10`
                  return String(val)
                }
                const answered = Object.keys(SLOTS).filter((s) => sl[s] !== undefined)
                return (
                  <details key={c} className="log">
                    <summary>{nm(c)}</summary>
                    <ul className="rows">
                      {answered.map((s) => (
                        <li key={s} className="row-link">
                          <span className="muted">{t(SLOTS, s)}</span>
                          <span>{fmt(s)}</span>
                        </li>
                      ))}
                    </ul>
                  </details>
                )
              })}
              {(v.negatives?.length ?? 0) > 0 &&
                <p><b>{ui('Отрицания:')}</b> {v.negatives!.map(nm).join(', ')}</p>}
              <p><b>{ui('Обзор систем:')}</b> {positive.length === 0
                ? ui('без жалоб') : positive.map(([s]) => nm(s)).join(', ')}</p>
              <p className="muted">{ui('подтверждено пациентом')} · {new Date(summary.begins).toLocaleString()}</p>
            </div>
          </section>
        )
      })()}

      {/* рекомендованные анализы — ИИ ранжирует по ценности и доступности;
          по каждому можно загрузить документ или вписать результат вручную
          (домашние пробы документа не дают) */}
      {workup && (() => {
        const w = workup.value as unknown as Workup
        if (!w.tests?.length) return null
        return (
          <section>
            <h3>{ui('Рекомендованные анализы')}</h3>
            <p className="muted">{ui('Отранжированы по ценности и доступности. По каждому — загрузите документ с результатом или впишите результат сами; всё войдёт в диагноз.')}</p>
            <ul className="cards">
              {w.tests.map((x, i) => {
                const done = results.find((r) => {
                  const v = r.value as { code?: string; test?: string }
                  return matches(v.code ?? null, v.test ?? null, x)
                })
                const doc = docs.find((d) => matches(d.code, d.name, x))
                return (
                  <li key={i} className="card">
                    <b>{i + 1}. {x.test}</b>
                    {x.self && <span className="chip state"> {ui('можно дома')}</span>}
                    <div className="muted">{x.reason}</div>
                    {done && <div>✓ {ui('Результат:')}{' '}
                      {String((done.value as { result?: string }).result ?? '')}</div>}
                    {doc && !done && <div className="muted">✓ {ui('документ загружен')}</div>}
                    {!done && resFor !== x.test && (
                      <div className="inline">
                        <button className="ghost small" onClick={() => { setResFor(x.test); setResText('') }}>
                          {ui('Вписать результат')}
                        </button>
                        <label className="ghost small btn-file">
                          {ui('Загрузить документ')}
                          <input type="file" hidden
                                 onChange={(e) => uploadFor(x, e.target.files?.[0] ?? null)} />
                        </label>
                      </div>
                    )}
                    {resFor === x.test && (
                      <div className="inline">
                        <input value={resText} autoFocus placeholder={ui('что получилось — своими словами')}
                               onChange={(e) => setResText(e.target.value)}
                               onKeyDown={(e) => { if (e.key === 'Enter' && resText.trim()) saveResult(x) }} />
                        <button onClick={() => saveResult(x)} disabled={!resText.trim()}>{ui('Сохранить')}</button>
                        <button className="ghost" onClick={() => setResFor(null)}>{ui('Отмена')}</button>
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          </section>
        )
      })()}

      {/* анализы ещё подбираются (шина обрабатывает событие после подтверждения) */}
      {!workup && workupPending && (
        <section>
          <h3>{ui('Рекомендованные анализы')}</h3>
          <p className="muted parsing">{ui('ИИ подбирает анализы по анамнезу…')}</p>
        </section>
      )}

      <section>
        <h3>{ui('Диагноз (оценка ИИ)')}</h3>
        <div className="inline">
          {/* диагноз по неполному анамнезу вводит в заблуждение — сначала опрос */}
          <button onClick={evaluate} disabled={evaluating || !a || a.gaps.length > 0}>
            {evaluating ? ui('ИИ анализирует…') : (ddx ? ui('Пересчитать диагноз') : ui('Диагноз'))}
          </button>
          <span className="muted">
            {a && a.gaps.length > 0
              ? ui('станет доступно после сбора анамнеза — пройдите опрос')
              : ui('анамнез и оригиналы загруженных документов уйдут ИИ одной задачей')}
          </span>
        </div>
        {/* мягкое предупреждение о неполноте: рекомендованы анализы, а результатов нет */}
        {workup && (workup.value as unknown as Workup).tests?.length > 0
          && docs.length === 0 && results.length === 0 &&
          <p className="muted">{ui('Рекомендованные анализы ещё не загружены — оценка будет менее точной.')}</p>}
        {ddx && (() => {
          const v = ddx.value as unknown as Ddx
          return (
            <div className="card resume">
              {v.urgent && <p className="alert">{ui('⚠ Данные указывают на возможное угрожающее состояние — не откладывайте обращение за помощью.')}</p>}
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
              <p className="muted disclaimer">{ui('Предварительная оценка ИИ — не диагноз и не заменяет осмотр врача. Обсудите результат со специалистом.')}</p>
            </div>
          )
        })()}
      </section>

      {/* жалобы вносятся опросом (анамнез) — ручного ввода кодов нет */}
      {symptoms.length > 0 && (
        <section>
          <h3>{ui('Жалобы')}</h3>
          <ul className="cards">
            {symptoms.map((s) => (
              <li key={s.id} className="card">
                <b>{s.name || symNames[s.code] || s.code}</b>
                {(s.value as { status?: string }).status === 'absent' &&
                  <span className="muted"> {ui('— отсутствует (значимо)')}</span>}
                <span className="muted"> · {String((s.value as { source?: string }).source ?? '')}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* дневник симптомов: журнал замеров в моменте в рамках эпизода */}
      <section>
        <h3>{ui('Дневник симптомов')}</h3>
        <p className="muted">{ui('Замеры в моменте — температура, давление, пульс. Уйдут ИИ в диагноз вместе с анамнезом.')}</p>
        <div className="inline">
          <select value={dCode} onChange={(e) => setDCode(e.target.value)}>
            <option value="">{ui('— параметр —')}</option>
            {diaryDict.map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
          </select>
          <input placeholder={ui('значение')} value={dVal}
                 onChange={(e) => setDVal(e.target.value)}
                 onKeyDown={(e) => { if (e.key === 'Enter') addDiary() }} />
          <button onClick={addDiary} disabled={!dCode || !dVal.trim()}>{ui('Записать')}</button>
        </div>
        <ul className="rows">
          {diary.map((p) => (
            <li key={p.id} className="row-link">
              <span>{p.name || p.code}</span>
              <b>{String(p.value.value ?? '')} {String(p.value.unit ?? '')}</b>
              <span className="muted">{new Date(p.begins).toLocaleString()}</span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3>{ui('Документы')}</h3>
        <p className="muted">{ui('Результаты анализов и обследований. Читаются ИИ при нажатии «Диагноз» (оригиналы), не разбираются при загрузке.')}</p>
        <form className="inline" onSubmit={upload}>
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <input placeholder={ui('название')} value={docName}
                 onChange={(e) => setDocName(e.target.value)} />
          <button type="submit" disabled={!file}>{ui('Загрузить')}</button>
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
                  <span className="chip state">{ui('ИИ')}</span> <b>{f.code}</b>
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
