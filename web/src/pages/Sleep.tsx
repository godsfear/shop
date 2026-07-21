import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import {
  addSleep, closeProperty, getSleep,
  type MedProperty, type SleepAssessment,
} from '../api'
import { ui } from '../i18n'

const localDay = (shift = 0) => {
  const d = new Date(); d.setDate(d.getDate() + shift)
  return d.toLocaleDateString('sv')
}

// "HH:MM" -> минуты
const parseHM = (s?: string): number | null => {
  const m = /^(\d{1,2}):(\d{2})$/.exec((s ?? '').trim())
  return m ? +m[1] * 60 + +m[2] : null
}
// эффективность = время сна / время в постели × 100; постель = встал − лёг (через полночь)
const efficiency = (bedtime?: string, getup?: string, total?: string): number | null => {
  const bt = parseHM(bedtime), gu = parseHM(getup), tot = parseHM(total)
  if (bt == null || gu == null || tot == null) return null
  let tib = gu - bt; if (tib <= 0) tib += 1440
  return tib > 0 ? Math.round((tot / tib) * 100) : null
}

// показатели ночи для журнала (порядок карточки); efficiency/wellbeing — особые
const LABELS: { key: string; label: string; unit?: string }[] = [
  { key: 'bedtime', label: 'Когда лёг' },
  { key: 'getup', label: 'Когда встал' },
  { key: 'onset_min', label: 'Время засыпания', unit: 'мин' },
  { key: 'total', label: 'Общее время сна' },
  { key: 'efficiency', label: 'Эффективность сна', unit: '%' },
  { key: 'wake_count', label: 'Пробуждений за ночь' },
  { key: 'wake_min', label: 'Длительность пробуждений', unit: 'мин' },
  { key: 'wellbeing', label: 'Самочувствие утром' },
  { key: 'pulse', label: 'Ночной пульс', unit: 'уд/мин' },
  { key: 'hrv', label: 'HRV', unit: 'мс' },
  { key: 'spo2', label: 'Ночной SpO₂', unit: '%' },
]

export default function Sleep() {
  const [entries, setEntries] = useState<MedProperty[]>([])
  const [assess, setAssess] = useState<SleepAssessment | null>(null)
  const [date, setDate] = useState(localDay())
  const [f, setF] = useState<Record<string, string>>({})
  const [wb, setWb] = useState(7)          // самочувствие утром — слайдер 1..10
  const [err, setErr] = useState('')

  const load = async () => {
    try { const j = await getSleep(); setEntries(j.entries); setAssess(j.assessment) }
    catch (e) { setErr((e as Error).message) }
  }
  useEffect(() => { load() }, [])
  // пока ИИ считает оценку за период — поллим
  useEffect(() => {
    if (assess?.status !== 'pending') return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [assess?.status])

  const set = (k: string, v: string) => setF((s) => ({ ...s, [k]: v }))
  const eff = efficiency(f.bedtime, f.getup, f.total)

  const save = async (e: FormEvent) => {
    e.preventDefault(); setErr('')
    const value: Record<string, unknown> = { wellbeing: wb }
    for (const [k, raw] of Object.entries(f)) {
      const v = raw.trim(); if (!v) continue
      value[k] = ['bedtime', 'getup', 'total'].includes(k) ? v : Number(v.replace(',', '.'))
    }
    if (eff != null) value.efficiency = eff
    try {
      await addSleep(date, value)
      setF({}); setWb(7)
      await load()
    } catch (e) { setErr((e as Error).message) }
  }

  const remove = async (id: string) => {
    setErr('')
    try { await closeProperty(id); await load() } catch (e) { setErr((e as Error).message) }
  }

  const numField = (key: string, label: string, unit?: string, min?: number, max?: number) => (
    <label className="row" key={key}>{ui(label)}
      <span className="inline">
        <input type="number" inputMode="decimal" min={min} max={max}
               value={f[key] ?? ''} onChange={(e) => set(key, e.target.value)} />
        {unit && <span className="muted">{ui(unit)}</span>}
      </span>
    </label>
  )
  const timeField = (key: string, label: string) => (
    <label className="row" key={key}>{ui(label)}
      <input type="time" value={f[key] ?? ''} onChange={(e) => set(key, e.target.value)} />
    </label>
  )

  return (
    <div>
      <p><Link to="/">{ui('← сегодня')}</Link></p>
      <h2>{ui('Сон')}</h2>
      {err && <p className="error">{err}</p>}

      {/* оценка ИИ за период (учитывает данные «Моей карты») */}
      <section>
        <h3>{ui('Оценка сна')}
          {assess?.status === 'pending' && <span className="muted"> · {ui('обновляется…')}</span>}
        </h3>
        {assess?.summary ? (
          <div className="card resume">
            {assess.quality && assess.quality !== '—' &&
              <p><b>{ui('Качество')}: {assess.quality}</b></p>}
            <p>{assess.summary}</p>
            <p className="muted disclaimer">{ui('Оценка ИИ по журналу и данным карты — ориентир, не диагноз.')}</p>
          </div>
        ) : <p className="muted">{ui('Оценка появится после первой записи ночи.')}</p>}
      </section>

      <section>
        <h3>{ui('Записать ночь')}</h3>
        <form onSubmit={save} className="sleep-form">
          <label className="row">{ui('Ночь на дату')}
            <input type="date" value={date} max={localDay()}
                   onChange={(e) => setDate(e.target.value)} />
          </label>
          {timeField('bedtime', 'Когда лёг')}
          {timeField('getup', 'Когда встал')}
          {numField('onset_min', 'Время засыпания', 'мин')}
          {timeField('total', 'Общее время сна')}
          <label className="row">{ui('Эффективность сна')}
            <span className="muted">{eff != null ? `${eff} %` : '—'}</span>
          </label>
          {numField('wake_count', 'Пробуждений за ночь')}
          {numField('wake_min', 'Длительность пробуждений', 'мин')}
          <label className="row">{ui('Самочувствие утром')}
            <span className="inline">
              <input type="range" min={1} max={10} value={wb}
                     onChange={(e) => setWb(+e.target.value)} />
              <b>{wb}/10</b>
            </span>
          </label>
          {numField('pulse', 'Ночной пульс', 'уд/мин')}
          {numField('hrv', 'HRV', 'мс')}
          {numField('spo2', 'Ночной SpO₂', '%')}
          <button type="submit">{ui('Записать')}</button>
        </form>
        <p className="muted disclaimer">{ui('Показатели вносите из своего трекера или часов — заполняйте, что есть. Эффективность считается сама.')}</p>
      </section>

      <section>
        <h3>{ui('Журнал сна')}</h3>
        <ul className="cards">
          {entries.map((p) => {
            const v = p.value as Record<string, unknown>
            return (
              <li key={p.id} className="card">
                <div className="inline">
                  <b>{String(v.date ?? p.name ?? '')}</b>
                  <button className="ghost small" style={{ marginLeft: 'auto' }}
                          onClick={() => remove(p.id)}>{ui('удалить')}</button>
                </div>
                <div className="sleep-vals">
                  {LABELS.filter((x) => v[x.key] !== undefined && v[x.key] !== '').map((x) => (
                    <span key={x.key} className="muted">
                      {ui(x.label)}: <b>{String(v[x.key])}{x.key === 'wellbeing' ? '/10'
                        : x.unit ? ' ' + ui(x.unit) : ''}</b>
                    </span>
                  ))}
                </div>
              </li>
            )
          })}
        </ul>
        {entries.length === 0 && <p className="muted">{ui('пока пусто')}</p>}
      </section>
    </div>
  )
}
