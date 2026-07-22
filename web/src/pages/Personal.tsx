import { useEffect, useState, type FormEvent } from 'react'
import { me, getPerson, updatePerson } from '../api'
import { ui } from '../i18n'

// Личные данные (домен личности): пока страна и город проживания. Это данные
// о САМом пользователе (не о пациенте care-режима) — берём свою персону из me().
export default function Personal() {
  const [pid, setPid] = useState('')
  const [country, setCountry] = useState('')
  const [city, setCity] = useState('')
  const [err, setErr] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    (async () => {
      try {
        const m = await me()
        setPid(m.person)
        const p = await getPerson(m.person)
        setCountry(p.residence?.country ?? '')
        setCity(p.residence?.city ?? '')
      } catch (e) { setErr((e as Error).message) }
    })()
  }, [])

  const save = async (e: FormEvent) => {
    e.preventDefault(); setErr(''); setSaved(false)
    try {
      await updatePerson(pid, { residence: { country: country.trim(), city: city.trim() } })
      setSaved(true)
    } catch (e) { setErr((e as Error).message) }
  }

  return (
    <section className="tile">
      <h2>{ui('Личные данные')}</h2>
      <p className="muted">{ui('Страна и город проживания — учитываются в оценках ИИ (эндемичные и сезонные факторы, климат).')}</p>
      {err && <p className="error">{err}</p>}
      <form onSubmit={save} className="sleep-form">
        <label className="row">{ui('Страна')}
          <input value={country} placeholder={ui('например, Россия')}
                 onChange={(e) => { setCountry(e.target.value); setSaved(false) }} />
        </label>
        <label className="row">{ui('Город')}
          <input value={city} placeholder={ui('например, Москва')}
                 onChange={(e) => { setCity(e.target.value); setSaved(false) }} />
        </label>
        <div className="inline">
          <button type="submit" disabled={!pid}>{ui('Сохранить')}</button>
          {saved && <span className="muted">{ui('сохранено')}</span>}
        </div>
      </form>
    </section>
  )
}
