import { useEffect, useState } from 'react'
import {
  addProperty, closeProperty, concepts, dictionary, listProperties,
  propertyHistory, updateProperty,
  type Concepts, type DictItem, type MedProperty,
} from '../api'
import { SECTIONS, UNITS, t } from '../ui'
import { ui } from '../i18n'

// Разделы «Моей карты» в порядке показа; vital — особый (значение+история)
const PROFILE_SECTIONS = ['vital', 'chronic', 'medication', 'allergy',
                          'surgery', 'heredity', 'social', 'risk_factor',
                          'blood', 'vaccination']

function Section({ concept, cid }: { concept: string; cid: string }) {
  const [items, setItems] = useState<MedProperty[]>([])
  const [dict, setDict] = useState<DictItem[]>([])
  const [free, setFree] = useState('')
  const [val, setVal] = useState('')          // значение для vital
  const [picked, setPicked] = useState('')
  const [adding, setAdding] = useState(false)
  const [addFormOpen, setAddFormOpen] = useState(false)
  const [err, setErr] = useState('')
  const [hist, setHist] = useState<Record<string, MedProperty[]>>({})
  const vital = concept === 'vital'
  const names = new Map(dict.map((d) => [d.code, d.name]))
  const selectedCode = picked || free.trim()
  const selectedExists = !vital && items.some((i) => i.code === selectedCode)

  const load = () => listProperties(cid).then(setItems).catch((e) => setErr(e.message))
  useEffect(() => {
    // vital: в карте — только профильные показатели (температура — дневник эпизода)
    dictionary(concept).then((d) =>
      setDict(vital ? d.filter((x) => x.scopes?.includes('profile')) : d)).catch(() => {})
    load()
  }, [cid])

  const add = async () => {
    setErr('')
    const code = selectedCode
    if (!code || selectedExists || adding) return
    setAdding(true)
    try {
      const value: Record<string, unknown> = vital
        ? { value: val.trim(), unit: ui(UNITS[code] ?? '') }   // единица — на языке ввода
        : { status: 'present' }
      const existing = vital ? items.find((i) => i.code === code) : undefined
      if (existing) await updateProperty(existing.id, { ...existing.value, ...value })
      else await addProperty({ category: cid, code, name: names.get(code), value })
      setFree(''); setVal(''); setPicked('')
      setAddFormOpen(false)
      await load()
    } catch (e) { setErr((e as Error).message) }
    finally { setAdding(false) }
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

  const openAddForm = () => {
    setErr('')
    setAddFormOpen(true)
  }

  const closeAddForm = () => {
    setFree(''); setVal(''); setPicked('')
    setAddFormOpen(false)
  }

  return (
    <section className="tile">
      <header>
        <h3>{t(SECTIONS, concept)}</h3>
        {!addFormOpen && (
          <button className="ghost small profile-add" onClick={openAddForm}>
            + {ui('Добавить')}
          </button>
        )}
      </header>
      {err && <p className="error">{err}</p>}
      {items.length === 0 && <p className="muted">{ui('пока пусто')}</p>}
      <ul className={'profile-values' + (vital ? ' profile-vitals' : '')}>
        {items.map((p) => (
          <li key={p.id} className="profile-value-wrap">
            <div className="profile-value">
              <span className="profile-value-name">{p.name || names.get(p.code) || p.code}</span>
              {vital && <b>{String(p.value.value ?? '')} {String(p.value.unit ?? '')}</b>}
              {vital && <button className="ghost small profile-history" onClick={() => toggleHist(p)}>
                {hist[p.id] ? ui('скрыть') : ui('история')}</button>}
              <button className="profile-remove" type="button"
                      title={ui('удалить')}
                      aria-label={`${ui('удалить')}: ${p.name || names.get(p.code) || p.code}`}
                      onClick={() => close(p)}>×</button>
            </div>
            {hist[p.id] && (
              <ul className="rows hist profile-history-list">
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
      {addFormOpen && (
        <div className="profile-editor">
          <div className="inline">
            {dict.length > 0 && (
              <select value={picked} onChange={(e) => {
                setPicked(e.target.value)
                if (e.target.value) setFree('')
              }}>
                <option value="">{ui('— из справочника —')}</option>
                {dict.map((d) => <option key={d.code} value={d.code}
                                         disabled={!vital && items.some((i) => i.code === d.code)}>
                  {d.name}
                </option>)}
              </select>
            )}
            {!vital && <input placeholder={ui('свой вариант')} value={free}
                              onChange={(e) => { setFree(e.target.value); if (e.target.value) setPicked('') }} />}
            {vital && <input placeholder={ui('значение')} value={val}
                             onChange={(e) => setVal(e.target.value)} />}
          </div>
          <div className="inline profile-editor-actions">
            <button onClick={add} disabled={adding || (vital ? !(picked && val.trim())
              : !selectedCode || selectedExists)}>
              {vital ? ui('Записать') : ui('Добавить')}
            </button>
            <button className="ghost" type="button" onClick={closeAddForm}>{ui('Отмена')}</button>
          </div>
        </div>
      )}
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
      <h2>{ui('Моя карта')}</h2>
      <p className="muted">{ui('Постоянные данные о здоровье. Врач увидит их по вашему согласию; опрос при новом эпизоде лишь попросит подтвердить актуальность.')}</p>
      <div className="tiles profile-tiles">
        {PROFILE_SECTIONS.filter((s) => cs[s]).map((s) =>
          <Section key={s} concept={s} cid={cs[s]} />)}
      </div>
    </div>
  )
}
