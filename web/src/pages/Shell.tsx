import { useEffect, useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { ApiError, enroll, getCare, openSession, setCare } from '../api'
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
  const care = getCare()

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
      <header>
        <NavLink to="/" className="brand" end>{ui('здоровье')}</NavLink>
        <nav className="topnav">
          <NavLink to="/" end>{ui('Сегодня')}</NavLink>
          <NavLink to="/profile">{ui('Моя карта')}</NavLink>
          <NavLink to="/access">{ui('Доступы')}</NavLink>
          <NavLink to="/patients">{ui('Доверили мне')}</NavLink>
        </nav>
        <LangSwitch className="right" />
        <button className="ghost" onClick={logout}>{ui('Выйти')}</button>
      </header>
      {care && (
        <div className="care-banner">
          {ui('Карта пациента')} …{care.link_id.slice(-6)} {ui('— доступ по согласию')}
          <button className="ghost" onClick={leaveCare}>{ui('Выйти из карты')}</button>
        </div>
      )}
      <main>{ready ? <Outlet /> : <p className="muted">{status || ui('открываю сессию…')}</p>}</main>
    </div>
  )
}
