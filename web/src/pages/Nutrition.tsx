import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import {
  addMeal, closeProperty, getNutrition,
  type MealValue, type Nutrition as NutritionData, type NutritionNorm,
} from '../api'
import { ui } from '../i18n'

// локальная дата клиента YYYY-MM-DD: сутки считает пользователь, не UTC
export const localDay = (shift = 0) => {
  const d = new Date()
  d.setDate(d.getDate() + shift)
  return d.toLocaleDateString('sv')
}

// Полоска «потреблено / норма»; перебор нормы — предупреждающим цветом
export function MacroBar({ label, got, norm, unit }: {
  label: string; got: number; norm?: number; unit: string
}) {
  const pct = norm ? Math.min(100, Math.round((got / norm) * 100)) : 0
  return (
    <div className="macro">
      <span className="muted">{label}</span>
      <div className="track"><div className={'fill' + (norm && got > norm * 1.15 ? ' over' : '')}
                                  style={{ width: `${pct}%` }} /></div>
      <span>{Math.round(got)}{norm ? ` / ${Math.round(norm)}` : ''} {unit}</span>
    </div>
  )
}

// дефицит показываем ближе к концу дня: раньше он ещё «не наеден» честно
function deficits(totals: Record<string, number>, norm: NutritionNorm | null): string[] {
  if (!norm || new Date().getHours() < 17) return []
  const out: string[] = []
  const check = (got: number, need?: number, label?: string) => {
    if (need && got < need * 0.6 && label) out.push(label)
  }
  check(totals.protein ?? 0, norm.protein_g, ui('белков'))
  check(totals.fat ?? 0, norm.fat_g, ui('жиров'))
  check(totals.carbs ?? 0, norm.carbs_g, ui('углеводов'))
  return out
}

export default function Nutrition() {
  const [day, setDay] = useState(localDay())
  const [data, setData] = useState<NutritionData | null>(null)
  const [desc, setDesc] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const load = async (d: string) => {
    try { setData(await getNutrition(d)) } catch (e) { setErr((e as Error).message) }
  }
  useEffect(() => { setData(null); load(day) }, [day])

  // поллинг, пока ИИ оценивает приём или пересчитывает норму
  const pending = !!data && (data.norm?.status === 'pending'
    || data.meals.some((m) => (m.value as MealValue).status === 'estimating'))
  useEffect(() => {
    if (!pending) return
    const t = setInterval(() => load(day), 3000)
    return () => clearInterval(t)
  }, [pending, day])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setErr(''); setBusy(true)
    try {
      await addMeal(day, desc.trim(), photo)
      setDesc(''); setPhoto(null)
      if (fileRef.current) fileRef.current.value = ''
      await load(day)
    } catch (e) { setErr((e as Error).message) }
    finally { setBusy(false) }
  }

  const remove = async (id: string) => {
    setErr('')
    try { await closeProperty(id); await load(day) }
    catch (e) { setErr((e as Error).message) }
  }

  const norm = data?.norm ?? null
  const totals = data?.totals ?? {}
  const lack = deficits(totals, norm)

  return (
    <div>
      <p><Link to="/">{ui('← сегодня')}</Link></p>
      <h2>{ui('Питание')}</h2>
      <div className="inline">
        <button className="ghost small" onClick={() => setDay(localDay(-1))}>←</button>
        <b>{day === localDay() ? ui('сегодня') : day}</b>
        <button className="ghost small" disabled={day >= localDay()}
                onClick={() => setDay(localDay(0))}>→</button>
      </div>
      {err && <p className="error">{err}</p>}

      <section>
        <h3>{ui('Норма на день')}
          {norm?.status === 'pending' && <span className="muted"> · {ui('обновляется…')}</span>}
        </h3>
        <div className="card resume">
          <MacroBar label={ui('калории')} got={totals.kcal ?? 0} norm={norm?.kcal} unit={ui('ккал')} />
          <MacroBar label={ui('белки')} got={totals.protein ?? 0} norm={norm?.protein_g} unit={ui('г')} />
          <MacroBar label={ui('жиры')} got={totals.fat ?? 0} norm={norm?.fat_g} unit={ui('г')} />
          <MacroBar label={ui('углеводы')} got={totals.carbs ?? 0} norm={norm?.carbs_g} unit={ui('г')} />
          {lack.length > 0 &&
            <p className="alert">{ui('Сегодня маловато')}: {lack.join(', ')}.</p>}
          {norm?.note && <p className="muted">{norm.note}</p>}
          <p className="muted disclaimer">{ui('Норма рассчитана ИИ по данным карты — это ориентир, не лечебная диета.')}</p>
        </div>
      </section>

      <section>
        <h3>{ui('Что съели')}</h3>
        <form className="inline" onSubmit={submit}>
          <input placeholder={ui('опишите еду (например: борщ и два куска хлеба)')}
                 value={desc} onChange={(e) => setDesc(e.target.value)} />
          <label className="ghost small btn-file">
            {photo ? photo.name.slice(0, 18) : ui('Фото')}
            <input ref={fileRef} type="file" accept="image/*" hidden
                   onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
          </label>
          <button type="submit" disabled={busy || (!desc.trim() && !photo)}>
            {busy ? ui('Загрузка…') : ui('Оценить')}
          </button>
        </form>
        <ul className="cards">
          {(data?.meals ?? []).map((m) => {
            const v = m.value as MealValue
            return (
              <li key={m.id} className="card">
                <div className="inline">
                  <b>{v.desc || ui('приём пищи')}</b>
                  {v.status === 'estimating'
                    ? <span className="muted parsing">{ui('ИИ считает…')}</span>
                    : <span className="chip state">{Math.round(v.totals?.kcal ?? 0)} {ui('ккал')}</span>}
                  <button className="ghost small" style={{ marginLeft: 'auto' }}
                          onClick={() => remove(m.id)}>{ui('удалить')}</button>
                </div>
                {(v.items ?? []).map((it, i) => (
                  <div key={i} className="muted">
                    {it.name} — {Math.round(it.kcal)} {ui('ккал')} · {ui('Б')} {Math.round(it.protein)} / {ui('Ж')} {Math.round(it.fat)} / {ui('У')} {Math.round(it.carbs)}
                  </div>
                ))}
                {v.note && <div className="muted">{v.note}</div>}
              </li>
            )
          })}
        </ul>
        {data && data.meals.length === 0 && <p className="muted">{ui('пока пусто')}</p>}
      </section>
    </div>
  )
}
