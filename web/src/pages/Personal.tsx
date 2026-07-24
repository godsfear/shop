import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  cities as loadCities,
  countries as loadCountries,
  getPerson,
  me,
  updatePerson,
  type GeographyOption,
} from '../api'
import { ui } from '../i18n'

// Личные данные (домен личности): пока страна и город проживания. Это данные
// о САМом пользователе (не о пациенте care-режима) — берём свою персону из me().
export default function Personal() {
  const [pid, setPid] = useState('')
  const [countryCode, setCountryCode] = useState('')
  const [city, setCity] = useState('')
  const storedCityCode = useRef('')
  const [countryOptions, setCountryOptions] = useState<GeographyOption[]>([])
  const [cityOptions, setCityOptions] = useState<GeographyOption[]>([])
  const [loadingCities, setLoadingCities] = useState(false)
  const [err, setErr] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    (async () => {
      try {
        const [m, options] = await Promise.all([me(), loadCountries()])
        setCountryOptions(options)
        setPid(m.person)
        const p = await getPerson(m.person)
        const storedCountry = p.residence?.country_code?.toLowerCase()
        const matchedCountry = options.find((item) =>
          item.code === storedCountry ||
          item.name.localeCompare(p.residence?.country ?? '', undefined, { sensitivity: 'base' }) === 0
        )
        setCountryCode(matchedCountry?.code ?? '')
        setCity(p.residence?.city ?? '')
        storedCityCode.current = p.residence?.city_code ?? ''
      } catch (e) { setErr((e as Error).message) }
    })()
  }, [])

  useEffect(() => {
    let cancelled = false
    setCityOptions([])
    if (!countryCode) {
      setLoadingCities(false)
      return () => { cancelled = true }
    }
    setLoadingCities(true)
    loadCities(countryCode)
      .then((options) => {
        if (cancelled) return
        setCityOptions(options)
        const localized = options.find((item) => item.code === storedCityCode.current)
        if (localized) setCity(localized.name)
        storedCityCode.current = ''
      })
      .catch((e) => { if (!cancelled) setErr((e as Error).message) })
      .finally(() => { if (!cancelled) setLoadingCities(false) })
    return () => { cancelled = true }
  }, [countryCode])

  const save = async (e: FormEvent) => {
    e.preventDefault(); setErr(''); setSaved(false)
    try {
      const country = countryOptions.find((item) => item.code === countryCode)
      const matchedCity = cityOptions.find((item) =>
        item.name.localeCompare(city.trim(), undefined, { sensitivity: 'base' }) === 0
      )
      await updatePerson(pid, {
        residence: {
          country: country?.name ?? '',
          city: city.trim(),
          country_code: country?.code,
          city_code: matchedCity?.code,
        },
      })
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
          <select value={countryCode} onChange={(e) => {
            setCountryCode(e.target.value)
            storedCityCode.current = ''
            setCity(''); setSaved(false)
          }}>
            <option value="">{ui('— выберите страну —')}</option>
            {countryOptions.map((item) =>
              <option key={item.code} value={item.code}>{item.name}</option>
            )}
          </select>
        </label>
        <label className="row">{ui('Город')}
          <input value={city} list="residence-cities"
                 disabled={!countryCode || loadingCities}
                 placeholder={loadingCities ? ui('загрузка…') : ui('начните вводить город')}
                 onChange={(e) => {
                   const value = e.target.value
                   setCity(value); setSaved(false)
                 }} />
          <datalist id="residence-cities">
            {cityOptions.map((item) =>
              <option key={item.code} value={item.name} />
            )}
          </datalist>
        </label>
        <div className="inline">
          <button type="submit" disabled={!pid || !countryCode || !city.trim()}>
            {ui('Сохранить')}
          </button>
          {saved && <span className="muted">{ui('сохранено')}</span>}
        </div>
      </form>
    </section>
  )
}
