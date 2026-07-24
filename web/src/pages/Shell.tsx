import { useEffect, useState } from 'react'
import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom'
import {
  ApiError, concepts, enroll, getCare, getPerson, isAdmin, listProperties, me, openSession,
  setCare,
} from '../api'
import { useAuth } from '../auth'
import { loadMeta } from '../ui'
import { getLang, setLang, ui } from '../i18n'

// Переключатель языка: показывает, НА ЧТО переключить; смена перезагружает
// страницу (данные перезапрашиваются с новым Accept-Language)
export function LangSwitch({ className = '' }: { className?: string }) {
  const other = getLang() === 'ru' ? 'en' : 'ru'
  return (
    <button className={`ghost ${className}`} onClick={() => setLang(other)}>
      {other.toUpperCase()}
    </button>
  )
}

// Каркас: открывает owner-сессию (ключи выпускаются при регистрации; 409 у
// старых учёток лечится автоматическим довыпуском). В режиме «Пациенты» (care)
// сессия не нужна — Слой B несёт link_id/key_id в каждом запросе.
export default function Shell() {
  const { setToken } = useAuth()
  const nav = useNavigate()
  const [status, setStatus] = useState('')
  const [ready, setReady] = useState(false)   // гейт: дети грузят данные по открытой сессии
  const [sessionOk, setSessionOk] = useState(false)
  const [profileName, setProfileName] = useState('')
  // подсказка «заполните карту»: показывается, пока нет роста и веса —
  // без них ИИ-оценки (норма питания, диагноз) заметно грубее
  const [needProfile, setNeedProfile] = useState(false)
  const [hintHidden, setHintHidden] = useState(
    sessionStorage.getItem('profile-hint-hidden') === '1')
  const care = getCare()
  const location = useLocation()

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const currentUser = await me()
        const person = await getPerson(currentUser.person)
        const name = [person.name.first, person.name.last]
          .filter((part): part is string => typeof part === 'string' && !!part.trim())
          .join(' ')
        if (!cancelled) setProfileName(name)
      } catch { /* имя не должно мешать открытию приложения */ }
    })()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!ready || care) { setNeedProfile(false); return }
    // перепроверка при смене страницы: заполнил рост/вес — баннер сам исчез
    (async () => {
      try {
        const cs = await concepts()
        if (!cs['vital']) return
        const have = new Set((await listProperties(cs['vital'])).map((p) => p.code))
        setNeedProfile(!(have.has('height') && have.has('weight')))
      } catch { /* не мешаем работе, если проверка не удалась */ }
    })()
  }, [ready, care, location.pathname])

  useEffect(() => {
    // подписи доменных кодов (/me/meta) — до рендера страниц; при ошибке коды как есть
    if (care || sessionOk) { loadMeta().finally(() => setReady(true)); return }
    (async () => {
      try {
        await openSession()
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          try {
            await enroll()          // учётка старше автовыпуска — довыпустить ключи
            await openSession()
          } catch (e2) { setStatus(ui('не удалось открыть карту:') + ' ' + (e2 as Error).message); return }
        } else {
          setStatus(ui('нет связи с сервером:') + ' ' + (e as Error).message)
          return
        }
      }
      setSessionOk(true)   // эффект перезапустится и догрузит meta -> ready
    })()
  }, [care, sessionOk])

  const logout = () => { setCare(null); setToken(null); nav('/login') }
  const leaveCare = () => { setCare(null); nav('/patients') }

  return (
    <div className="app">
      <div className="app-sticky">
        <header>
          <NavLink to="/" className="brand" end>{profileName || ui('здоровье')}</NavLink>
          <nav className="topnav">
            <NavLink to="/" end>{ui('Сегодня')}</NavLink>
            <NavLink to="/profile">{ui('Моя карта')}</NavLink>
            <NavLink to="/personal">{ui('Личные данные')}</NavLink>
            <NavLink to="/access">{ui('Доступы')}</NavLink>
            <NavLink to="/patients">{ui('Доверили мне')}</NavLink>
            {isAdmin() && <NavLink to="/admin">{ui('Админ')}</NavLink>}
          </nav>
          <LangSwitch className="right" />
          <button className="ghost" onClick={logout}>{ui('Выйти')}</button>
        </header>
        {care && (
          <div className="care-banner">
            {care.patient
              ? <>{ui('Карта пациента')}: <b>{care.patient}</b></>
              : <>{ui('Карта пациента')} …{care.link_id.slice(-6)}</>}
            {' '}{ui('— доступ по согласию')}
            <button className="ghost" onClick={leaveCare}>{ui('Выйти из карты')}</button>
          </div>
        )}
      </div>
      {needProfile && !hintHidden && !care && (
        <div className="confirm-banner">
          <span>{ui('Заполните рост и вес в «Моей карте» — ИИ будет точнее считать норму питания и оценивать здоровье.')}</span>
          <NavLink to="/profile"><button>{ui('Заполнить')}</button></NavLink>
          <button className="ghost" onClick={() => {
            sessionStorage.setItem('profile-hint-hidden', '1'); setHintHidden(true)
          }}>{ui('Позже')}</button>
        </div>
      )}
      <main>{ready ? <Outlet /> : <p className="muted">{status || ui('открываю сессию…')}</p>}</main>
    </div>
  )
}
