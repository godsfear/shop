import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import {
  addProperty, closeProperty, concepts, listProperties,
  type Concepts, type MedProperty,
} from '../api'
import { ui } from '../i18n'

// локальная дата клиента YYYY-MM-DD (ночь считаем по утренней дате)
const localDay = (shift = 0) => {
  const d = new Date(); d.setDate(d.getDate() + shift)
  return d.toLocaleDateString('sv')
}

// поля ночи: времена — строки "HH:MM", остальное — числа. Всё необязательно —
// заполняйте, что даёт трекер/часы. Порядок = порядок в форме и в карточке.
type Field = { key: string; label: string; type: 'time' | 'number'; unit?: string; min?: number; max?: number }
export const SLEEP_FIELDS: Field[] = [
  { key: 'bedtime', label: 'Когда лёг', type: 'time' },
  { key: 'onset_min', label: 'Время засыпания', type: 'number', unit: 'мин' },
  { key: 'total', label: 'Общее время сна', type: 'time' },
  { key: 'efficiency', label: 'Эффективность сна', type: 'number', unit: '%' },
  { key: 'wake_count', label: 'Пробуждений за ночь', type: 'number' },
  { key: 'wake_min', label: 'Длительность пробуждений', type: 'number', unit: 'мин' },
  { key: 'wellbeing', label: 'Самочувствие утром', type: 'number', min: 1, max: 10 },
  { key: 'pulse', label: 'Ночной пульс', type: 'number', unit: 'уд/мин' },
  { key: 'hrv', label: 'HRV', type: 'number', unit: 'мс' },
  { key: 'spo2', label: 'Ночной SpO₂', type: 'number', unit: '%' },
]

// Журнал сна: каждая ночь — свойство на псевдониме (concept=sleep). ИИ пока не
// задействован — это ручной дневник показателей с трекера.
export default function Sleep() {
  const [cs, setCs] = useState<Concepts>({})
  const [rows, setRows] = useState<MedProperty[]>([])
  const [date, setDate] = useState(localDay())
  const [form, setForm] = useState<Record<string, string>>({})
  const [err, setErr] = useState('')

  const load = async (cat: string) => {
    try { setRows((await listProperties(cat)).sort((a, b) => b.begins.localeCompare(a.begins))) }
    catch (e) { setErr((e as Error).message) }
  }
  useEffect(() => {
    concepts().then((c) => { setCs(c); if (c['sleep']) load(c['sleep']) })
      .catch((e) => setErr((e as Error).message))
  }, [])

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const save = async (e: FormEvent) => {
    e.preventDefault(); setErr('')
    // значение только из заполненных полей; числа приводим к number
    const value: Record<string, unknown> = { date }
    let any = false
    for (const f of SLEEP_FIELDS) {
      const raw = (form[f.key] ?? '').trim()
      if (!raw) continue
      any = true
      value[f.key] = f.type === 'number' ? Number(raw.replace(',', '.')) : raw
    }
    if (!any) { setErr(ui('Заполните хотя бы один показатель.')); return }
    try {
      await addProperty({ category: cs['sleep'], code: `sleep-${date}-${Date.now()}`,
        name: date, value })
      setForm({})
      await load(cs['sleep'])
    } catch (e) { setErr((e as Error).message) }
  }

  const remove = async (id: string) => {
    setErr('')
    try { await closeProperty(id); await load(cs['sleep']) }
    catch (e) { setErr((e as Error).message) }
  }

  return (
    <div>
      <p><Link to="/">{ui('← сегодня')}</Link></p>
      <h2>{ui('Сон')}</h2>
      {err && <p className="error">{err}</p>}

      <section>
        <h3>{ui('Записать ночь')}</h3>
        <form onSubmit={save}>
          <label className="row">{ui('Ночь на дату')}
            <input type="date" value={date} max={localDay()}
                   onChange={(e) => setDate(e.target.value)} />
          </label>
          {SLEEP_FIELDS.map((f) => (
            <label key={f.key} className="row">{ui(f.label)}
              <span className="inline">
                <input type={f.type} inputMode={f.type === 'number' ? 'decimal' : undefined}
                       min={f.min} max={f.max} value={form[f.key] ?? ''}
                       onChange={(e) => set(f.key, e.target.value)} />
                {f.unit && <span className="muted">{ui(f.unit)}</span>}
              </span>
            </label>
          ))}
          <button type="submit">{ui('Записать')}</button>
        </form>
        <p className="muted disclaimer">{ui('Показатели вносите из своего трекера или часов — заполняйте, что есть.')}</p>
      </section>

      <section>
        <h3>{ui('Журнал сна')}</h3>
        <ul className="cards">
          {rows.map((p) => {
            const v = p.value as Record<string, unknown>
            return (
              <li key={p.id} className="card">
                <div className="inline">
                  <b>{String(v.date ?? p.name ?? '')}</b>
                  <button className="ghost small" style={{ marginLeft: 'auto' }}
                          onClick={() => remove(p.id)}>{ui('удалить')}</button>
                </div>
                <div className="sleep-vals">
                  {SLEEP_FIELDS.filter((f) => v[f.key] !== undefined && v[f.key] !== '').map((f) => (
                    <span key={f.key} className="muted">
                      {ui(f.label)}: <b>{String(v[f.key])}{f.unit ? ' ' + ui(f.unit) : ''}</b>
                    </span>
                  ))}
                </div>
              </li>
            )
          })}
        </ul>
        {rows.length === 0 && <p className="muted">{ui('пока пусто')}</p>}
      </section>
    </div>
  )
}
