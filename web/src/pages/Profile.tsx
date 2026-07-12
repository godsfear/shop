import { useEffect, useState } from 'react'
import {
  addProperty, closeProperty, concepts, dictionary, listProperties,
  propertyHistory, updateProperty,
  type Concepts, type DictItem, type MedProperty,
} from '../api'
import { SECTIONS, t } from '../ui'

// Разделы «Моей карты» в порядке показа; vital — особый (значение+история)
const PROFILE_SECTIONS = ['vital', 'chronic', 'medication', 'allergy',
                          'surgery', 'heredity', 'social', 'risk_factor',
                          'blood', 'vaccination']
const UNITS: Record<string, string> = {
  height: 'см', weight: 'кг', blood_pressure: 'мм рт. ст.', pulse: 'уд/мин',
}

function Section({ concept, cid }: { concept: string; cid: string }) {
  const [items, setItems] = useState<MedProperty[]>([])
  const [dict, setDict] = useState<DictItem[]>([])
  const [free, setFree] = useState('')
  const [val, setVal] = useState('')          // значение для vital
  const [picked, setPicked] = useState('')
  const [err, setErr] = useState('')
  const [hist, setHist] = useState<Record<string, MedProperty[]>>({})
  const vital = concept === 'vital'
  const names = new Map(dict.map((d) => [d.code, d.name]))

  const load = () => listProperties(cid).then(setItems).catch((e) => setErr(e.message))
  useEffect(() => { dictionary(concept).then(setDict).catch(() => {}); load() }, [cid])

  const add = async () => {
    setErr('')
    const code = picked || free.trim()
    if (!code) return
    try {
      const value: Record<string, unknown> = vital
        ? { value: val.trim(), unit: UNITS[code] ?? '' }
        : { status: 'present' }
      const existing = vital ? items.find((i) => i.code === code) : undefined
      if (existing) await updateProperty(existing.id, { ...existing.value, ...value })
      else await addProperty({ category: cid, code, name: names.get(code), value })
      setFree(''); setVal(''); setPicked('')
      await load()
    } catch (e) { setErr((e as Error).message) }
  }

  const close = async (p: MedProperty) => {
    setErr('')
    try { await closeProperty(p.id); await load() }
    catch (e) { setErr((e as Error).message) }
  }

  const toggleHist = async (p: MedProperty) => {
    if (hist[p.id]) { setHist(({ [p.id]: _, ...rest }) => rest); return }
    setHist({ ...hist, [p.id]: await propertyHistory(p.id) })
  }

  return (
    <section className="tile">
      <header><h3>{t(SECTIONS, concept)}</h3></header>
      {err && <p className="error">{err}</p>}
      {items.length === 0 && <p className="muted">пока пусто</p>}
      <ul className="rows">
        {items.map((p) => (
          <li key={p.id}>
            <div className="row-link">
              <span>{p.name || names.get(p.code) || p.code}</span>
              {vital && <b>{String(p.value.value ?? '')} {String(p.value.unit ?? '')}</b>}
              {vital && <button className="ghost small" onClick={() => toggleHist(p)}>
                {hist[p.id] ? 'скрыть' : 'история'}</button>}
              <button className="ghost small" style={{ marginLeft: 'auto' }}
                      onClick={() => close(p)}>закрыть</button>
            </div>
            {hist[p.id] && (
              <ul className="rows hist">
                {hist[p.id].map((h) => (
                  <li key={h.id} className="row-link muted">
                    <span>{String(h.value.value ?? '')} {String(h.value.unit ?? '')}</span>
                    <span>{new Date(h.begins).toLocaleDateString()}</span>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
      <div className="inline">
        {dict.length > 0 && (
          <select value={picked} onChange={(e) => setPicked(e.target.value)}>
            <option value="">— из справочника —</option>
            {dict.map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
          </select>
        )}
        {!vital && <input placeholder="свой вариант" value={free}
                          onChange={(e) => setFree(e.target.value)} />}
        {vital && <input placeholder="значение" value={val}
                         onChange={(e) => setVal(e.target.value)} />}
        <button onClick={add} disabled={vital ? !(picked && val.trim()) : !(picked || free.trim())}>
          {vital ? 'Записать' : 'Добавить'}
        </button>
      </div>
    </section>
  )
}

// «Моя карта»: постоянные данные владельца — просмотр и дополнение.
// Интервью эпизода их не пересобирает, а просит подтвердить актуальность.
export default function Profile() {
  const [cs, setCs] = useState<Concepts>({})
  useEffect(() => { concepts().then(setCs).catch(() => {}) }, [])
  return (
    <div>
      <h2>Моя карта</h2>
      <p className="muted">Постоянные данные о здоровье. Врач увидит их по вашему
      согласию; опрос при новом эпизоде лишь попросит подтвердить актуальность.</p>
      <div className="tiles">
        {PROFILE_SECTIONS.filter((s) => cs[s]).map((s) =>
          <Section key={s} concept={s} cid={cs[s]} />)}
      </div>
    </div>
  )
}
