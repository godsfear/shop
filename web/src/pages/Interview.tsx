import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  dictionary, interviewAnswer, interviewOpen,
  type DictItem, type InterviewView,
} from '../api'
import { SECTIONS, STATES, t } from '../ui'
import { ui } from '../i18n'

// Этапы протокола для полосы прогресса (emergency — вне линии, плашкой)
const FLOW = ['complaint', 'symptom', 'ros', 'history', 'completeness', 'summary', 'confirmed']

// tag — жалоба, к которой относится вопрос: рендерится жирным и цветом
interface Msg { who: 'srv' | 'me'; text: string; tag?: string }
type Names = Record<string, string>

// ------------------------------------------------------------------ утилиты
function srvMsg(v: InterviewView, names: Names): { text: string; tag?: string } {
  const q = v.question
  switch (v.state) {
    case 'complaint':
      return { text: ui('Что беспокоит больше всего? Это станет главной жалобой.') }
    case 'symptom':
      return { tag: names[q?.symptom ?? ''] ?? q?.symptom, text: q?.ask ?? '' }
    case 'ros':
      return { text: `${ui('Обзор систем')} — ${names[q?.system ?? ''] ?? q?.system}: ${ui('есть ли жалобы?')}` }
    case 'history':
      return { text: `${ui('Анамнез жизни')} — ${t(SECTIONS, q?.section ?? '')}: ${ui('что отметить?')}` }
    case 'completeness':
      return { text: `${ui('Остались пробелы:')} ${(q?.gaps ?? []).map((g) => t(SECTIONS, g).toLocaleLowerCase()).join(', ')}. ${ui('Заполним?')}` }
    case 'summary':
      return { text: ui('Резюме собрано. Всё ли верно и полно?') }
    case 'emergency':
      return { text: ui('Признаки угрожающего состояния — опрос прерван.') }
    case 'confirmed':
      return { text: ui('Анамнез собран и подтверждён. Спасибо!') }
    default:
      return { text: v.state }
  }
}

// ------------------------------------------------------------ мелкие виджеты
function Chips({ items, picked, onToggle }: {
  items: DictItem[]; picked: string[]; onToggle: (code: string) => void
}) {
  return (
    <div className="inline">
      {items.map((it) => (
        <button key={it.code} type="button"
                className={'chip pick' + (picked.includes(it.code) ? ' on' : '')}
                onClick={() => onToggle(it.code)}>
          {it.name}
        </button>
      ))}
    </div>
  )
}

/** Выбор симптомов: чипы справочника + свой вариант (слаг латиницей не нужен —
 * код придумывает пользователь по-русски, бэк принимает любой code). */
function SymptomPick({ dict, multi, submitLabel, exclude = [], onSubmit }: {
  dict: DictItem[]; multi: boolean; submitLabel: string; exclude?: string[]
  onSubmit: (codes: string[], label: string) => void
}) {
  const [picked, setPicked] = useState<string[]>([])
  const [free, setFree] = useState('')
  // не показываем уже выбранные/разобранные симптомы — иначе опрос циклится
  const avail = dict.filter((d) => !exclude.includes(d.code))
  const toggle = (code: string) => setPicked(multi
    ? (picked.includes(code) ? picked.filter((c) => c !== code) : [...picked, code])
    : [code])
  const submit = () => {
    const codes = [...picked]
    if (free.trim()) codes.push(free.trim())
    if (!codes.length) return
    const names = new Map(dict.map((d) => [d.code, d.name]))
    onSubmit(codes, codes.map((c) => names.get(c) ?? c).join(', '))
  }
  return (
    <div className="answer">
      <Chips items={avail} picked={picked} onToggle={toggle} />
      <div className="inline">
        <input placeholder={ui('свой вариант')} value={free}
               onChange={(e) => setFree(e.target.value)} />
        <button onClick={submit} disabled={!picked.length && !free.trim()}>{submitLabel}</button>
      </div>
    </div>
  )
}

function Severity({ onSubmit }: { onSubmit: (n: number) => void }) {
  const [n, setN] = useState(5)
  return (
    <div className="answer">
      <div className="inline slider">
        <span>0</span>
        <input type="range" min="0" max="10" value={n}
               onChange={(e) => setN(Number(e.target.value))} />
        <span>10</span>
        <b className="sev">{n}</b>
      </div>
      <button onClick={() => onSubmit(n)}>{ui('Ответить')}</button>
    </div>
  )
}

/** Секция анамнеза жизни: чипы справочника (если есть) + свободные строки;
 * пустой ответ — значимое «ничего нет». */
function ItemsEditor({ dict, onSubmit }: {
  dict: DictItem[]; onSubmit: (items: { code: string; name?: string }[], label: string) => void
}) {
  const [picked, setPicked] = useState<string[]>([])
  const [lines, setLines] = useState<string[]>([])
  const [free, setFree] = useState('')
  const toggle = (code: string) => setPicked(
    picked.includes(code) ? picked.filter((c) => c !== code) : [...picked, code])
  const add = () => { if (free.trim()) { setLines([...lines, free.trim()]); setFree('') } }
  const submit = () => {
    const names = new Map(dict.map((d) => [d.code, d.name]))
    // непустое поле — тоже пункт, даже если «+» не нажали (иначе ввод теряется)
    const allLines = free.trim() ? [...lines, free.trim()] : lines
    const items = [
      ...picked.map((c) => ({ code: c })),
      ...allLines.map((l) => ({ code: l })),
    ]
    const label = items.length
      ? items.map((i) => names.get(i.code) ?? i.code).join(', ')
      : ui('ничего нет')
    onSubmit(items, label)
  }
  return (
    <div className="answer">
      {dict.length > 0 && <Chips items={dict} picked={picked} onToggle={toggle} />}
      {lines.map((l, i) => <p key={i} className="muted">+ {l}</p>)}
      <div className="inline">
        <input placeholder={ui('добавить свободной строкой')} value={free}
               onChange={(e) => setFree(e.target.value)} />
        <button type="button" className="ghost" onClick={add} disabled={!free.trim()}>+</button>
      </div>
      <div className="inline">
        <button onClick={submit}>
          {picked.length || lines.length || free.trim() ? ui('Готово') : ui('Ничего нет')}
        </button>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ страница
export default function Interview() {
  const { id = '' } = useParams()
  const [view, setView] = useState<InterviewView | null>(null)
  const [feed, setFeed] = useState<Msg[]>([])
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [symDict, setSymDict] = useState<DictItem[]>([])
  const [secDict, setSecDict] = useState<DictItem[]>([])   // справочник текущей секции
  const [rosOpen, setRosOpen] = useState(false)            // «есть жалобы» -> выбор
  const [moreOpen, setMoreOpen] = useState(false)          // «да, ещё…» из резюме
  const [histEdit, setHistEdit] = useState(false)          // «дополнить» вместо подтверждения
  const [free, setFree] = useState('')                     // текстовый слот
  const names = useRef<Names>({})
  const endRef = useRef<HTMLDivElement>(null)

  const remember = (items: DictItem[]) =>
    items.forEach((it) => { names.current[it.code] = it.name })

  const show = (v: InterviewView) => {
    setView(v)
    setRosOpen(false); setMoreOpen(false); setHistEdit(false); setFree('')
    setFeed((f) => [...f, { who: 'srv', ...srvMsg(v, names.current) }])
    if (v.state === 'history' || v.state === 'completeness') {
      const section = v.question?.section ?? v.question?.gaps?.[0]
      if (section) dictionary(section).then((d) => { remember(d); setSecDict(d) })
      else setSecDict([])
    }
  }

  const started = useRef(false)
  useEffect(() => {
    if (started.current) return  // StrictMode зовёт эффект дважды — открытие одно
    started.current = true
    ;(async () => {
      try {
        const [sym, sys] = await Promise.all([dictionary('symptom'), dictionary('system')])
        remember(sym); remember(sys); setSymDict(sym)
        show(await interviewOpen(id))
      } catch (e) { setErr((e as Error).message) }
    })()
  }, [id])

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [feed])

  const answer = async (body: Record<string, unknown>, echo: string) => {
    if (busy) return  // защита от двойного клика: параллельные ответы — гонка
    setErr(''); setBusy(true)
    setFeed((f) => [...f, { who: 'me', text: echo }])
    try { show(await interviewAnswer(id, body)) }
    catch (e) { setErr((e as Error).message) }
    finally { setBusy(false) }
  }

  const q = view?.question
  const state = view?.state ?? ''
  // уже покрытые жалобы (разобранные + в очереди + текущая) — прячем из выбора
  const covered = [...(view?.done ?? []), ...(view?.queue ?? []), q?.symptom]
    .filter(Boolean) as string[]
  const cur = FLOW.indexOf(state)

  return (
    <div className="interview">
      <p><Link to={`/episode/${id}`}>{ui('← к эпизоду')}</Link></p>
      <div className="timeline">
        {FLOW.map((st, i) => (
          <span key={st}
                className={'st' + (i < cur ? ' done' : '') + (i === cur ? ' cur' : '')}>
            {t(STATES, st)}
          </span>
        ))}
      </div>
      {state === 'emergency' && (
        <div className="stripe">
          <b>{ui('Красный флаг:')} {(view?.alerts ?? []).join(', ')}.</b>{' '}
          {ui('Опрос прерван — при угрозе жизни звоните')} <b>103 / 112</b>.
        </div>
      )}

      <div className="feed">
        {feed.map((m, i) => (
          <div key={i} className={`msg ${m.who}`}>
            {m.tag && <span className="sym-tag">{m.tag}</span>}{m.tag ? ': ' : ''}{m.text}
          </div>
        ))}
        <div ref={endRef} />
      </div>
      {err && <p className="error">{err}</p>}

      {!busy && view && (
        <div className="composer">
          {state === 'complaint' &&
            <SymptomPick dict={symDict} multi={false} submitLabel={ui('Это главная жалоба')}
                         onSubmit={(codes, label) => answer({ symptom: codes[0] }, label)} />}

          {state === 'symptom' && q?.slot === 'severity' &&
            <Severity onSubmit={(n) => answer({ value: n }, String(n))} />}

          {state === 'symptom' && q?.slot === 'associations' && (
            <div className="answer">
              <p className="muted">{ui('Отметьте, что появилось одновременно — каждый уйдёт в разбор.')}</p>
              <SymptomPick dict={symDict} multi submitLabel={ui('Ответить')} exclude={covered}
                           onSubmit={(codes, label) => answer({ value: codes }, label)} />
              <button className="ghost" onClick={() => answer({ value: [] }, ui('ничего'))}>
                {ui('Ничего сопутствующего')}
              </button>
            </div>
          )}

          {state === 'symptom' && q?.slot !== 'severity' && q?.slot !== 'associations' && (
            <div className="answer inline">
              <input placeholder={ui('ответ свободным текстом')} value={free} autoFocus
                     onChange={(e) => setFree(e.target.value)}
                     onKeyDown={(e) => { if (e.key === 'Enter' && free.trim()) answer({ value: free.trim() }, free.trim()) }} />
              <button onClick={() => answer({ value: free.trim() }, free.trim())}
                      disabled={!free.trim()}>{ui('Ответить')}</button>
            </div>
          )}

          {state === 'ros' && !rosOpen && (
            <div className="answer inline">
              <button className="ghost" onClick={() => answer({ positive: false }, ui('всё в порядке'))}>
                {ui('Всё в порядке')}
              </button>
              <button onClick={() => setRosOpen(true)}>{ui('Есть жалобы')}</button>
            </div>
          )}
          {state === 'ros' && rosOpen &&
            <SymptomPick dict={symDict} multi submitLabel={ui('Ответить')} exclude={covered}
                         onSubmit={(codes, label) =>
                           answer({ positive: true, symptoms: codes }, label)} />}

          {/* секция уже заполнена в карте — просим подтвердить актуальность */}
          {state === 'history' && (q?.known?.length ?? 0) > 0 && !histEdit && (
            <div className="answer">
              <p className="muted">{ui('В карте:')} {q!.known!
                .map((c) => names.current[c] ?? c).join(', ')}</p>
              <div className="inline">
                <button onClick={() => answer({ confirmed: true }, ui('всё актуально'))}>
                  {ui('Актуально')}
                </button>
                <button className="ghost" onClick={() => setHistEdit(true)}>{ui('Дополнить…')}</button>
              </div>
            </div>
          )}
          {state === 'history' && ((q?.known?.length ?? 0) === 0 || histEdit) &&
            <ItemsEditor dict={secDict}
                         onSubmit={(items, label) => answer({ items }, label)} />}

          {state === 'completeness' &&
            <ItemsEditor dict={secDict}
                         onSubmit={(items, label) =>
                           answer({ section: q?.gaps?.[0], items }, label)} />}

          {state === 'summary' && view.summary && !moreOpen && (
            <div className="answer">
              <div className="card resume">
                <p><b>{ui('Главная жалоба:')}</b> {names.current[view.summary.chief_complaint ?? ''] ?? view.summary.chief_complaint}</p>
                <p><b>{ui('Симптомы:')}</b> {Object.keys(view.summary.symptoms)
                  .map((c) => names.current[c] ?? c).join(', ') || '—'}</p>
                {view.summary.negatives.length > 0 &&
                  <p><b>{ui('Отрицания:')}</b> {view.summary.negatives
                    .map((c) => names.current[c] ?? c).join(', ')}</p>}
                <p><b>{ui('Обзор систем:')}</b> {Object.entries(view.summary.ros)
                  .filter(([, v]) => v !== 'clear').length === 0
                    ? ui('без жалоб')
                    : Object.entries(view.summary.ros).filter(([, v]) => v !== 'clear')
                        .map(([s]) => names.current[s] ?? s).join(', ')}</p>
              </div>
              <div className="inline">
                <button onClick={() => answer({ confirmed: true }, ui('всё верно'))}>{ui('Всё верно')}</button>
                <button className="ghost" onClick={() => setMoreOpen(true)}>{ui('Да, ещё…')}</button>
              </div>
            </div>
          )}
          {state === 'summary' && moreOpen &&
            <SymptomPick dict={symDict} multi submitLabel={ui('Добавить в разбор')} exclude={covered}
                         onSubmit={(codes, label) => answer({ more: codes }, label)} />}

          {state === 'emergency' && (
            <div className="answer inline">
              <button onClick={() => answer({ resume: true }, ui('помощь оказана — продолжаем'))}>
                {ui('Продолжить опрос')}
              </button>
            </div>
          )}

          {state === 'confirmed' && (
            <div className="answer inline">
              <Link to={`/episode/${id}`}><button>{ui('К эпизоду')}</button></Link>
            </div>
          )}
        </div>
      )}
      {busy && <p className="muted">…</p>}
    </div>
  )
}
