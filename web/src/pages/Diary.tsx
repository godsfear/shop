import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  addDiaryEntry, closeProperty, concepts, dictionary, getDiary,
  type Concepts, type DictItem, type MedProperty,
} from '../api'
import { GLUCOSE_CTX, UNITS, glucoseAlert } from '../ui'
import { ui } from '../i18n'
import { normalizeVitalInput, vitalInputHint } from '../vitals'

type Editor = 'vital' | 'note' | null

function periodBounds(from: string, to: string) {
  const begins = from ? new Date(`${from}T00:00:00`).toISOString() : undefined
  const ends = to ? new Date(`${to}T23:59:59.999`).toISOString() : undefined
  return { begins, ends }
}

function localDateValue(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function lastSevenDays() {
  const today = new Date()
  const from = new Date(today)
  from.setDate(from.getDate() - 6)
  return { from: localDateValue(from), to: localDateValue(today) }
}

const DEFAULT_DIARY_PERIOD = lastSevenDays()

// Общий дневник состояния: записи лежат на медкарте, а не внутри эпизода.
// Поэтому новый эпизод сразу видит историю измерений и заметок пациента.
export default function Diary() {
  const [cs, setCs] = useState<Concepts>({})
  const [dict, setDict] = useState<DictItem[]>([])
  const [entries, setEntries] = useState<MedProperty[]>([])
  const [editor, setEditor] = useState<Editor>(null)
  const [code, setCode] = useState('')
  const [value, setValue] = useState('')
  const [context, setContext] = useState('')
  const [note, setNote] = useState('')
  const [err, setErr] = useState('')
  const [valueErr, setValueErr] = useState('')
  const [filterFrom, setFilterFrom] = useState(DEFAULT_DIARY_PERIOD.from)
  const [filterTo, setFilterTo] = useState(DEFAULT_DIARY_PERIOD.to)
  const [filterCode, setFilterCode] = useState('')
  const [loading, setLoading] = useState(false)
  const selectedRule = dict.find((item) => item.code === code)?.validation

  const load = async (from = filterFrom, to = filterTo, parameter = filterCode) => {
    if (from && to && from > to) {
      setErr(ui('Начало периода не может быть позже окончания.'))
      return
    }
    setErr('')
    setLoading(true)
    try { setEntries(await getDiary({ ...periodBounds(from, to), code: parameter || undefined })) }
    catch (e) { setErr((e as Error).message) }
    finally { setLoading(false) }
  }

  useEffect(() => {
    concepts().then(setCs).catch(() => {})
    dictionary('vital').then((d) => setDict(d.filter((x) => x.scopes?.includes('diary')))).catch(() => {})
    load(DEFAULT_DIARY_PERIOD.from, DEFAULT_DIARY_PERIOD.to, '')
  }, [])

  const showLastSevenDays = () => {
    const period = lastSevenDays()
    setFilterFrom(period.from); setFilterTo(period.to)
    void load(period.from, period.to, filterCode)
  }

  const showAllTime = () => {
    setFilterFrom(''); setFilterTo('')
    void load('', '', filterCode)
  }

  const closeEditor = () => {
    setCode(''); setValue(''); setContext(''); setNote(''); setValueErr('')
    setEditor(null)
  }

  const addVital = async () => {
    if (!code || !value.trim() || !cs.vital) return
    setErr('')
    const checked = normalizeVitalInput(value, selectedRule)
    if (!checked.value) { setValueErr(checked.error || ''); return }
    setValueErr('')
    try {
      const names = new Map(dict.map((d) => [d.code, d.name]))
      await addDiaryEntry({
        category: cs.vital, code, name: names.get(code),
        value: { value: checked.value, unit: ui(UNITS[code] ?? ''),
                 ...(code === 'glucose' && context ? { context } : {}) },
      })
      closeEditor()
      await load()
    } catch (e) { setErr((e as Error).message) }
  }

  const addNote = async () => {
    if (!note.trim() || !cs.note) return
    setErr('')
    try {
      await addDiaryEntry({
        category: cs.note, code: `diary-${Date.now()}`,
        value: { text: note.trim() },
      })
      closeEditor()
      await load()
    } catch (e) { setErr((e as Error).message) }
  }

  const remove = async (id: string) => {
    setErr('')
    try { await closeProperty(id); await load() }
    catch (e) { setErr((e as Error).message) }
  }

  return (
    <div>
      <p><Link to="/">{ui('← сегодня')}</Link></p>
      <h2>{ui('Дневник состояния')}</h2>
      <p className="muted">{ui('Замеры и заметки хранятся в общем дневнике и доступны всем эпизодам.')}</p>
      {err && <p className="error">{err}</p>}

      <section>
        <div className="inline">
          {editor === null && (
            <>
              <button className="ghost" onClick={() => setEditor('vital')}>{ui('Добавить замер')}</button>
              <button className="ghost" onClick={() => setEditor('note')}>{ui('Добавить заметку')}</button>
            </>
          )}
        </div>

        {editor === 'vital' && (
          <div className="card diary-editor">
            <div className="inline">
              <select value={code} onChange={(e) => {
                setCode(e.target.value); setContext(''); setValue(''); setValueErr('')
              }}>
                <option value="">{ui('— параметр —')}</option>
                {dict.map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
              </select>
              {code === 'glucose' && (
                <select value={context} onChange={(e) => setContext(e.target.value)}>
                  <option value="">{ui('без уточнения')}</option>
                  <option value="fasting">{ui('натощак')}</option>
                  <option value="postprandial">{ui('после еды')}</option>
                </select>
              )}
              <input autoFocus placeholder={selectedRule?.example || ui('значение')}
                     inputMode={selectedRule?.kind === 'blood_pressure' ? 'text'
                       : selectedRule?.kind === 'number' && selectedRule.decimals === 0
                         ? 'numeric' : 'decimal'}
                     value={value}
                     onChange={(e) => { setValue(e.target.value); setValueErr('') }}
                     onKeyDown={(e) => { if (e.key === 'Enter') addVital() }} />
              <button onClick={addVital} disabled={!code || !value.trim()}>{ui('Записать')}</button>
              <button className="ghost" onClick={closeEditor}>{ui('Отмена')}</button>
            </div>
            {code && vitalInputHint(selectedRule) &&
              <p className="muted profile-value-hint">{vitalInputHint(selectedRule)}</p>}
            {valueErr && <p className="error profile-value-hint">{valueErr}</p>}
            {code === 'glucose' && glucoseAlert(value, context) &&
              <p className="warn">⚠ {ui(glucoseAlert(value, context))}</p>}
          </div>
        )}

        {editor === 'note' && (
          <div className="card diary-editor">
            <div className="inline">
              <input autoFocus placeholder={ui('своя заметка о самочувствии')} value={note}
                     onChange={(e) => setNote(e.target.value)}
                     onKeyDown={(e) => { if (e.key === 'Enter') addNote() }} />
              <button onClick={addNote} disabled={!note.trim()}>{ui('Добавить')}</button>
              <button className="ghost" onClick={closeEditor}>{ui('Отмена')}</button>
            </div>
          </div>
        )}
      </section>

      <div className="inline diary-filter">
        <label>
          <span>{ui('С')}</span>
          <input type="date" value={filterFrom} max={filterTo || undefined}
                 onChange={(e) => { setFilterFrom(e.target.value); setErr('') }} />
        </label>
        <label>
          <span>{ui('По')}</span>
          <input type="date" value={filterTo} min={filterFrom || undefined}
                 onChange={(e) => { setFilterTo(e.target.value); setErr('') }} />
        </label>
        <label>
          <span>{ui('Параметр')}</span>
          <select value={filterCode}
                  onChange={(e) => { setFilterCode(e.target.value); setErr('') }}>
            <option value="">{ui('Все параметры')}</option>
            {dict.map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
          </select>
        </label>
        <button onClick={() => load()} disabled={loading}>
          {loading ? ui('Загрузка…') : ui('Применить')}
        </button>
        <button className="ghost" onClick={showLastSevenDays}>{ui('7 дней')}</button>
        <button className="ghost" onClick={showAllTime}>{ui('Всё время')}</button>
      </div>

      {!loading && entries.length === 0 ? (
        <p className="muted">{filterFrom || filterTo || filterCode
          ? ui('записей по выбранным фильтрам нет') : ui('пока пусто')}</p>
      ) : (
        <ul className="rows diary-entries">
          {entries.map((p) => {
            const val = p.value as { value?: unknown; unit?: unknown; context?: string; text?: string }
            const isNote = val.text !== undefined
            const unit = String(val.unit ?? '').trim()
            const alert = p.code === 'glucose' ? glucoseAlert(String(val.value ?? ''), val.context) : ''
            return (
              <li key={p.id} className="row-link">
                <span className={`diary-entry-label${isNote ? '' : ' diary-parameter-name'}`}>
                  {isNote ? String(val.text) : p.name || p.code}
                  {!isNote && unit &&
                    <span className="diary-parameter-unit"> ({unit})</span>}
                  {!isNote && val.context && <span className="muted"> · {ui(GLUCOSE_CTX[val.context] ?? '')}</span>}</span>
                {!isNote && <span className="diary-entry-value diary-parameter-value">
                  {String(val.value ?? '')}</span>}
                {alert && <span className="warn diary-entry-alert">⚠ {ui(alert)}</span>}
                <span className="muted diary-entry-time">{new Date(p.begins).toLocaleString()}</span>
                <button className="ghost small diary-entry-remove"
                        onClick={() => remove(p.id)}>{ui('удалить')}</button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
