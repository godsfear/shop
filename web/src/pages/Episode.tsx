import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  getEpisode, renameEpisode, episodeHistory, episodeState, transition, assess,
  episodeProperties, listDocuments, uploadDocument, concepts, dictionary,
  evaluateEpisode, addEpisodeProperty, setDiagnosis, startTreatment, documentContent,
  editAnamnesis, closeEpisodeProperty,
  type Episode as Ep, type FsmState, type Assess, type MedProperty, type Doc,
  type Concepts, type StateLog, type DictItem,
} from '../api'

interface Ddx {
  assessments: { condition: string; likelihood: number; rationale: string }[]
  urgent: boolean; note?: string; docs?: number
}
interface WorkupTest { code?: string; test: string; reason: string; self?: boolean }
interface Workup { tests: WorkupTest[] }
interface PlanItem { code?: string; name: string; reason?: string; prescription?: boolean }
interface Plan { items: PlanItem[]; note?: string; diagnosis?: string }
import { EVENTS, GLUCOSE_CTX, RED_FLAGS, SECTIONS, SLOTS, STATES, UNITS, glucoseAlert, t } from '../ui'
import { ui } from '../i18n'

// Секция пройденного этапа сворачивается (details), текущего — раскрыта
function Stage({ title, done, children }: {
  title: string; done: boolean; children: ReactNode
}) {
  return (
    <section>
      <details open={!done}>
        <summary><h3>{title}</h3></summary>
        {children}
      </details>
    </section>
  )
}

// Документы «на руки» (направления, рецепты): загрузить может пациент или
// доверенный врач; ИИ их не читает. Открываются в новой вкладке — оттуда печать.
function HandoutDocs({ title, hint, docs, onUpload, busy }: {
  title: string; hint: string; docs: Doc[]; busy: boolean
  onUpload: (f: File) => void
}) {
  const [err, setErr] = useState('')
  const open = async (d: Doc, print: boolean) => {
    setErr('')
    try {
      const url = URL.createObjectURL(await documentContent(d.id))
      const w = window.open(url, '_blank')
      // печать сразу после загрузки; если браузер не дал — вкладка открыта, Ctrl+P
      if (w && print) w.addEventListener('load', () => w.print())
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (e) { setErr((e as Error).message) }
  }
  return (
    <section>
      <h3>{title}</h3>
      <p className="muted">{hint}</p>
      {err && <p className="error">{err}</p>}
      {docs.length === 0 && <p className="muted">{ui('пока пусто')}</p>}
      <ul className="rows">
        {docs.map((d) => (
          <li key={d.id} className="row-link">
            <span>{d.name || d.code}</span>
            <span className="muted">{new Date(d.begins).toLocaleDateString()}</span>
            <button className="ghost small" onClick={() => open(d, false)}>{ui('Открыть')}</button>
            <button className="ghost small" onClick={() => open(d, true)}>{ui('Печать')}</button>
          </li>
        ))}
      </ul>
      <label className="ghost small btn-file">
        {busy ? ui('Загрузка…') : ui('Загрузить документ')}
        <input type="file" hidden disabled={busy}
               onChange={(e) => { const f = e.target.files?.[0]; if (f) onUpload(f); e.target.value = '' }} />
      </label>
    </section>
  )
}

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
  const [referrals, setReferrals] = useState<Doc[]>([])       // направления
  const [prescriptions, setPrescriptions] = useState<Doc[]>([])  // рецепты
  const [handoutBusy, setHandoutBusy] = useState(false)
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
  // правка ответа анамнеза (до диагноза): "<symptom>|<slot>" редактируемой строки
  const [slotEdit, setSlotEdit] = useState<string | null>(null)
  const [slotVal, setSlotVal] = useState('')

  const saveSlot = async (symptom: string, slot: string) => {
    setErr('')
    try {
      await editAnamnesis(id, symptom, slot,
                          slot === 'severity' ? Number(slotVal) : slotVal.trim())
      setSlotEdit(null); setSlotVal('')
      await reload()
    } catch (e) { setErr((e as Error).message) }
  }

  // комментарий = свойство эпизода (concept=note): уходит в ИИ-бандл диагноза
  const addNote = async () => {
    const text = noteText.trim()
    if (!text) return
    setErr('')
    try {
      await addEpisodeProperty(id, {
        category: cs['note'], code: `note-${Date.now()}`,
        value: { text, source: 'patient' },
      })
      setNoteText('')
      await reload()
    } catch (e) { setErr((e as Error).message) }
  }
  const removeNote = async (propId: string) => {
    setErr('')
    try { await closeEpisodeProperty(id, propId); await reload() }
    catch (e) { setErr((e as Error).message) }
  }

  // установленный диагноз, план назначений ИИ и зафиксированное лечение
  const [diagProp, setDiagProp] = useState<MedProperty | null>(null)
  const [plan, setPlan] = useState<MedProperty | null>(null)
  const [treatProp, setTreatProp] = useState<MedProperty | null>(null)
  const [diagOpen, setDiagOpen] = useState(false)
  const [diagText, setDiagText] = useState('')
  const [planPending, setPlanPending] = useState(false)
  const [treatOpen, setTreatOpen] = useState(false)
  const [treatPicked, setTreatPicked] = useState<string[]>([])   // коды из плана ИИ
  const [treatLines, setTreatLines] = useState<string[]>([])     // свои назначения
  const [treatFree, setTreatFree] = useState('')
  // дневник симптомов: замеры в моменте (температура/давление/пульс)
  const [diary, setDiary] = useState<MedProperty[]>([])
  const [diaryDict, setDiaryDict] = useState<DictItem[]>([])
  const [dCode, setDCode] = useState('')
  const [dVal, setDVal] = useState('')
  const [dCtx, setDCtx] = useState('')   // сахар: натощак/после еды (норма зависит)
  const [diaryNote, setDiaryNote] = useState('')   // свободная заметка в дневник
  // комментарии пациента к эпизоду (доп. контекст для диагноза)
  const [notes, setNotes] = useState<MedProperty[]>([])
  const [noteText, setNoteText] = useState('')

  const reload = async () => {
    try {
      setEp(await getEpisode(id))
      setFsm(await episodeState(id))
      const props = await episodeProperties(id)
      setSymptoms(props.filter((p) => p.category === cs['symptom'] && !isAi(p)))
      // находки ИИ из документов; служебные ИИ-свойства (ddx/workup/plan) — не находки
      setFinds(props.filter((p) => isAi(p) && !['ddx', 'workup', 'plan'].includes(p.code)))
      setResults(props.filter((p) =>
        (p.value as { source?: string; result?: string }).source === 'patient'
        && (p.value as { result?: string }).result !== undefined))
      // дневник состояния: замеры (vital) + свои заметки (note, source='diary')
      setDiary(props.filter((p) => (p.category === cs['vital'] && !isAi(p))
        || (p.category === cs['note'] && (p.value as { source?: string }).source === 'diary'))
        .sort((a, b) => b.begins.localeCompare(a.begins)))
      // Комментарии — заметки эпизода, кроме дневниковых
      setNotes(props.filter((p) => p.category === cs['note']
        && (p.value as { source?: string }).source !== 'diary')
        .sort((a, b) => a.begins.localeCompare(b.begins)))
      setDdx(props.find((p) => p.code === 'ddx') ?? null)
      setWorkup(props.find((p) => p.code === 'workup') ?? null)
      const sum = props.find((p) => p.code === 'summary') ?? null
      setSummary(sum)
      setHasSummary(sum !== null)                             // интервью подтверждено
      setDiagProp(props.find((p) => p.code === 'diagnosis') ?? null)
      setPlan(props.find((p) => p.code === 'plan') ?? null)
      setTreatProp(props.find((p) => p.code === 'treatment') ?? null)
      const all = await listDocuments(id)
      // документы «на руки» показываются своими секциями, а не в общем списке
      setDocs(all.filter((d) => d.category !== cs['referral'] && d.category !== cs['prescription']))
      setReferrals(all.filter((d) => d.category === cs['referral']))
      setPrescriptions(all.filter((d) => d.category === cs['prescription']))
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
    // дневник — только показатели «в моменте» (рост и т.п. живут в «Моей карте»)
    dictionary('vital').then((d) =>
      setDiaryDict(d.filter((x) => x.scopes?.includes('diary')))).catch(() => {})
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

  // план назначений генерится в фоне после установки диагноза — опрашиваем,
  // пока не придёт план именно для текущего текста диагноза
  useEffect(() => {
    const dText = (diagProp?.value as { text?: string } | undefined)?.text
    if (!dText) return
    if (plan && (plan.value as unknown as Plan).diagnosis === dText) return
    let stop = false
    setPlanPending(true)
    ;(async () => {
      for (let i = 0; i < 10 && !stop; i++) {
        await new Promise((r) => setTimeout(r, 2500))
        const p = (await episodeProperties(id)).find((x) => x.code === 'plan')
        if (p && (p.value as unknown as Plan).diagnosis === dText) { setPlan(p); break }
      }
      if (!stop) setPlanPending(false)
    })()
    return () => { stop = true }
  }, [diagProp, plan, id])

  const saveDiag = async (source: string) => {
    setErr('')
    try {
      await setDiagnosis(id, diagText.trim(), source)
      setDiagOpen(false); setDiagText('')
      await reload()
    } catch (e) { setErr((e as Error).message) }
  }

  const saveTreatment = async () => {
    setErr('')
    // непустое поле — тоже назначение, даже если «+» не нажали
    const lines = treatFree.trim() ? [...treatLines, treatFree.trim()] : treatLines
    const items = [
      ...((plan?.value as unknown as Plan)?.items ?? [])
        .filter((x) => x.code && treatPicked.includes(x.code))
        .map((x) => ({ code: x.code, name: x.name })),
      ...lines.map((name) => ({ name })),
    ]
    if (!items.length) return
    try {
      await startTreatment(id, items)
      setTreatOpen(false); setTreatPicked([]); setTreatLines([]); setTreatFree('')
      await reload()
    } catch (e) { setErr((e as Error).message) }
  }

  // этап пройден (для сворачивания секций): текущее состояние дальше по маршруту
  const stagePassed = (s: string) =>
    !!fsm && fsm.states.includes(s) && fsm.states.indexOf(fsm.state) > fsm.states.indexOf(s)

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
        value: { value: dVal.trim(), unit: ui(UNITS[dCode] ?? ''), source: 'diary',
                 // контекст замера сахара — идёт и в бандл ИИ (норма зависит от него)
                 ...(dCode === 'glucose' && dCtx ? { context: dCtx } : {}) },
      })
      setDVal(''); setDCtx('')
      await reload()
    } catch (e) { setErr((e as Error).message) }
  }

  // свободная заметка в дневник состояния — свойство эпизода (concept=note,
  // source='diary'): видна в дневнике, но не в «Комментариях»; уходит ИИ в бандл
  const addDiaryNote = async () => {
    const text = diaryNote.trim()
    if (!text) return
    setErr('')
    try {
      await addEpisodeProperty(id, {
        category: cs['note'], code: `diary-${Date.now()}`,
        value: { text, source: 'diary' },
      })
      setDiaryNote('')
      await reload()
    } catch (e) { setErr((e as Error).message) }
  }

  // загрузка направления/рецепта: и пациентом, и врачом по мосту (тот же эндпоинт)
  const uploadHandout = async (concept: 'referral' | 'prescription', f: File) => {
    setErr(''); setHandoutBusy(true)
    try {
      await uploadDocument(f, f.name, concept, cs[concept], id)
      await reload()
    } catch (e) { setErr((e as Error).message) }
    finally { setHandoutBusy(false) }
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
          {/* diagnose/treat — не голые переходы: открывают формы диагноза/назначений */}
          {fsm?.available.map((ev) => (
            <button key={ev} className={fsm.state === 'anamnesis' ? 'ghost' : ''}
                    onClick={() => ev === 'diagnose'
                      ? (setDiagText((diagProp?.value as { text?: string })?.text ?? ''), setDiagOpen(true))
                      : ev === 'treat' ? setTreatOpen(true) : fire(ev)}>
              {t(EVENTS, ev)}
            </button>
          ))}
          {fsm && fsm.available.length === 0 && <span className="muted">{ui('маршрут завершён')}</span>}
        </div>

        {/* форма диагноза: выбрать вариант ИИ (ddx) или вписать свой */}
        {diagOpen && (() => {
          const opts = ((ddx?.value as unknown as Ddx)?.assessments ?? [])
            .slice(0, 5).map((a) => a.condition)
          return (
            <div className="answer">
              {opts.length > 0 && (
                <div className="inline">
                  {opts.map((c) => (
                    <button key={c} type="button"
                            className={'chip pick' + (diagText === c ? ' on' : '')}
                            onClick={() => setDiagText(c)}>{c}</button>
                  ))}
                </div>
              )}
              <p className="muted">{ui('Выберите вариант ИИ или впишите диагноз, поставленный врачом.')}</p>
              <div className="inline">
                <input value={diagText} autoFocus placeholder={ui('диагноз')}
                       onChange={(e) => setDiagText(e.target.value)} />
                <button onClick={() => saveDiag(opts.includes(diagText) ? 'ddx' : 'manual')}
                        disabled={!diagText.trim()}>{ui('Сохранить')}</button>
                <button className="ghost" onClick={() => setDiagOpen(false)}>{ui('Отмена')}</button>
              </div>
            </div>
          )
        })()}

        {/* форма назначений: чипы из плана ИИ (мультивыбор) + свои строки */}
        {treatOpen && (() => {
          const items = ((plan?.value as unknown as Plan)?.items ?? []).filter((x) => x.code)
          const toggle = (c: string) => setTreatPicked(treatPicked.includes(c)
            ? treatPicked.filter((x) => x !== c) : [...treatPicked, c])
          return (
            <div className="answer">
              {items.length > 0 && (
                <div className="inline">
                  {items.map((x) => (
                    <button key={x.code} type="button"
                            className={'chip pick' + (treatPicked.includes(x.code!) ? ' on' : '')}
                            onClick={() => toggle(x.code!)}>{x.name}</button>
                  ))}
                </div>
              )}
              {treatLines.map((l, i) => <p key={i} className="muted">+ {l}</p>)}
              <div className="inline">
                <input placeholder={ui('добавить своё назначение')} value={treatFree}
                       onChange={(e) => setTreatFree(e.target.value)} />
                <button type="button" className="ghost" disabled={!treatFree.trim()}
                        onClick={() => { setTreatLines([...treatLines, treatFree.trim()]); setTreatFree('') }}>+</button>
              </div>
              <div className="inline">
                <button onClick={saveTreatment}
                        disabled={!treatPicked.length && !treatLines.length && !treatFree.trim()}>
                  {ui('Начать лечение')}
                </button>
                <button className="ghost" onClick={() => setTreatOpen(false)}>{ui('Отмена')}</button>
              </div>
            </div>
          )
        })()}
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
          <Stage title={ui('Анамнез (резюме опроса)')} done={stagePassed('anamnesis')}>
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
                // правки — только до диагноза (после — анамнез зафиксирован);
                // associations структурный (очередь разбора) — не редактируется
                const editable = fsm?.state === 'anamnesis'
                return (
                  <details key={c} className="log">
                    <summary>{nm(c)}</summary>
                    <ul className="rows">
                      {answered.map((s) => (
                        <li key={s} className="row-link">
                          <span className="muted">{t(SLOTS, s)}</span>
                          {slotEdit === `${c}|${s}` ? (
                            <span className="inline">
                              <input value={slotVal} autoFocus
                                     type={s === 'severity' ? 'number' : 'text'}
                                     onChange={(e) => setSlotVal(e.target.value)}
                                     onKeyDown={(e) => { if (e.key === 'Enter' && slotVal.trim()) saveSlot(c, s) }} />
                              <button className="ghost small" disabled={!slotVal.trim()}
                                      onClick={() => saveSlot(c, s)}>{ui('Сохранить')}</button>
                              <button className="ghost small"
                                      onClick={() => setSlotEdit(null)}>{ui('Отмена')}</button>
                            </span>
                          ) : (
                            <span>{fmt(s)}
                              {editable && s !== 'associations' &&
                                <button className="ghost small" title={ui('изменить')}
                                        onClick={() => { setSlotEdit(`${c}|${s}`); setSlotVal(String(sl[s] ?? '')) }}>
                                  ✎
                                </button>}
                            </span>
                          )}
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
          </Stage>
        )
      })()}

      {/* комментарии пациента — доп. контекст для диагноза, что не спросил опрос
          (напр. чего НЕ было в начале эпизода при заведении задним числом);
          уходят в ИИ-бандл как свойства эпизода */}
      {hasSummary && (
        <Stage title={ui('Комментарии')} done={stagePassed('anamnesis')}>
          <p className="muted">{ui('Дополнительная информация для диагноза, которую не спросил опрос.')}</p>
          {notes.length > 0 && (
            <ul className="rows">
              {notes.map((n) => (
                <li key={n.id} className="row-link">
                  <span>{String((n.value as { text?: string }).text ?? '')}</span>
                  <button className="ghost small" style={{ marginLeft: 'auto' }}
                          onClick={() => removeNote(n.id)}>{ui('удалить')}</button>
                </li>
              ))}
            </ul>
          )}
          <div className="inline">
            <input placeholder={ui('добавить комментарий')} value={noteText}
                   onChange={(e) => setNoteText(e.target.value)}
                   onKeyDown={(e) => { if (e.key === 'Enter' && noteText.trim()) addNote() }} />
            <button className="ghost small" onClick={addNote} disabled={!noteText.trim()}>+</button>
          </div>
        </Stage>
      )}

      {/* рекомендованные анализы — ИИ ранжирует по ценности и доступности;
          по каждому можно загрузить документ или вписать результат вручную
          (домашние пробы документа не дают) */}
      {workup && (() => {
        const w = workup.value as unknown as Workup
        if (!w.tests?.length) return null
        return (
          <Stage title={ui('Рекомендованные анализы')} done={stagePassed('anamnesis')}>
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
          </Stage>
        )
      })()}

      {/* анализы ещё подбираются (шина обрабатывает событие после подтверждения) */}
      {!workup && workupPending && (
        <section>
          <h3>{ui('Рекомендованные анализы')}</h3>
          <p className="muted parsing">{ui('ИИ подбирает анализы по анамнезу…')}</p>
        </section>
      )}

      <Stage title={ui('Диагноз (оценка ИИ)')} done={stagePassed('anamnesis')}>
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
      </Stage>

      {/* === порядок блоков после «Диагноз (оценка ИИ)» задан владельцем === */}

      {/* дневник состояния: замеры «в моменте» + свои заметки; сворачиваемый */}
      <Stage title={ui('Дневник состояния')} done={false}>
        <p className="muted">{ui('Замеры в моменте (температура, давление, пульс, сахар) и свои заметки о самочувствии. Уйдут ИИ в диагноз вместе с анамнезом.')}</p>
        <div className="inline">
          <select value={dCode} onChange={(e) => { setDCode(e.target.value); setDCtx('') }}>
            <option value="">{ui('— параметр —')}</option>
            {diaryDict.map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
          </select>
          {/* сахар: контекст замера — норма и предупреждение зависят от него */}
          {dCode === 'glucose' && (
            <select value={dCtx} onChange={(e) => setDCtx(e.target.value)}>
              <option value="">{ui('без уточнения')}</option>
              <option value="fasting">{ui('натощак')}</option>
              <option value="postprandial">{ui('после еды')}</option>
            </select>
          )}
          <input placeholder={ui('значение')} value={dVal}
                 onChange={(e) => setDVal(e.target.value)}
                 onKeyDown={(e) => { if (e.key === 'Enter') addDiary() }} />
          <button onClick={addDiary} disabled={!dCode || !dVal.trim()}>{ui('Записать')}</button>
        </div>
        {/* живая подсказка при выходе сахара за границы (информация, не диагноз) */}
        {dCode === 'glucose' && glucoseAlert(dVal, dCtx) &&
          <p className="warn">⚠ {ui(glucoseAlert(dVal, dCtx))}</p>}
        {/* своя заметка о самочувствии (свободный текст) */}
        <div className="inline">
          <input placeholder={ui('своя заметка о самочувствии')} value={diaryNote}
                 onChange={(e) => setDiaryNote(e.target.value)}
                 onKeyDown={(e) => { if (e.key === 'Enter' && diaryNote.trim()) addDiaryNote() }} />
          <button className="ghost small" onClick={addDiaryNote} disabled={!diaryNote.trim()}>+</button>
        </div>
        <ul className="rows">
          {diary.map((p) => {
            const val = p.value as { value?: unknown; unit?: unknown; context?: string; text?: string }
            if (val.text !== undefined) return (        // свободная заметка
              <li key={p.id} className="row-link">
                <span>{String(val.text)}</span>
                <button className="ghost small" style={{ marginLeft: 'auto' }}
                        onClick={() => removeNote(p.id)}>{ui('удалить')}</button>
              </li>
            )
            const alert = p.code === 'glucose' ? glucoseAlert(String(val.value ?? ''), val.context) : ''
            return (
              <li key={p.id} className="row-link">
                <span>{p.name || p.code}
                  {val.context && <span className="muted"> · {ui(GLUCOSE_CTX[val.context] ?? '')}</span>}</span>
                <b>{String(val.value ?? '')} {String(val.unit ?? '')}</b>
                {alert && <span className="warn">⚠ {ui(alert)}</span>}
                <span className="muted">{new Date(p.begins).toLocaleString()}</span>
              </li>
            )
          })}
        </ul>
      </Stage>

      {/* направления на анализы/исследования — выданные врачом бумаги */}
      {diagProp && (
        <HandoutDocs title={ui('Направления')} busy={handoutBusy} docs={referrals}
                     hint={ui('Направления на анализы и исследования. Загрузить может пациент или врач с доступом; ИИ их не читает.')}
                     onUpload={(f) => uploadHandout('referral', f)} />
      )}

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

      {/* установленный диагноз (вручную/из ddx) — не путать с ИИ-оценкой выше */}
      {diagProp && (() => {
        const v = diagProp.value as { text?: string; source?: string }
        return (
          <section>
            <h3>{ui('Диагноз')}</h3>
            <div className="card resume">
              <b>{v.text}</b>{' '}
              <button className="ghost small"
                      onClick={() => { setDiagText(v.text ?? ''); setDiagOpen(true) }}>
                {ui('изменить')}
              </button>
              <p className="muted">{v.source === 'ddx' ? ui('выбран из вариантов ИИ') : ui('внесён вручную')}
                {' · '}{new Date(diagProp.begins).toLocaleDateString()}</p>
            </div>
          </section>
        )
      })()}

      {/* план назначений от ИИ — генерится после установки диагноза */}
      {diagProp && !treatProp && planPending &&
        (!plan || (plan.value as unknown as Plan).diagnosis !== (diagProp.value as { text?: string }).text) && (
        <section>
          <h3>{ui('Назначения (рекомендация ИИ)')}</h3>
          <p className="muted parsing">{ui('ИИ подбирает назначения по диагнозу…')}</p>
        </section>
      )}
      {plan && (() => {
        const v = plan.value as unknown as Plan
        if (!v.items?.length) return null
        return (
          <Stage title={ui('Назначения (рекомендация ИИ)')} done={stagePassed('diagnosis')}>
            <p className="muted">{ui('Отранжированы по важности. Нажмите «Начать лечение», чтобы выбрать из них и/или добавить назначения врача.')}</p>
            <ul className="cards">
              {v.items.map((x, i) => (
                <li key={i} className="card">
                  <b>{i + 1}. {x.name}</b>
                  {x.prescription && <span className="chip state"> {ui('нужно назначение врача')}</span>}
                  <div className="muted">{x.reason}</div>
                </li>
              ))}
            </ul>
            {v.note && <p className="muted">{v.note}</p>}
            <p className="muted disclaimer">{ui('Назначения ИИ — предложения для обсуждения с врачом. Не начинайте приём рецептурных препаратов без назначения врача.')}</p>
          </Stage>
        )
      })()}

      {/* рецепты — выдаются при лечении */}
      {treatProp && (
        <HandoutDocs title={ui('Рецепты')} busy={handoutBusy} docs={prescriptions}
                     hint={ui('Рецепты на препараты. Загрузить может пациент или врач с доступом; ИИ их не читает.')}
                     onUpload={(f) => uploadHandout('prescription', f)} />
      )}

      {/* зафиксированное лечение (выбор пациента) */}
      {treatProp && (() => {
        const its = (treatProp.value as { items?: { code?: string; name: string }[] }).items ?? []
        return (
          <section>
            <h3>{ui('Лечение')}{' '}
              <button className="ghost small"
                      onClick={() => {
                        setTreatPicked(its.filter((i) => i.code).map((i) => i.code!))
                        setTreatLines(its.filter((i) => !i.code).map((i) => i.name))
                        setTreatOpen(true)
                      }}>{ui('изменить')}</button>
            </h3>
            <ul className="rows">
              {its.map((x, i) => (
                <li key={i} className="row-link">
                  <span>{x.name}</span>
                </li>
              ))}
            </ul>
            <p className="muted">{ui('начато')} · {new Date(treatProp.begins).toLocaleDateString()}</p>
          </section>
        )
      })()}
    </div>
  )
}
