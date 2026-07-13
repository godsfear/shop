import { useEffect, useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { openSession, getCare, setCare, ApiError } from '../api'
import { useAuth } from '../auth'

// Каркас: открывает owner-сессию. Мост не выпущен (409) — не тупик: страницы
// работают, дашборд показывает плитку выпуска ключей (needEnroll в Outlet-контекст).
// В режиме «Пациенты» (care) сессия не нужна — Слой B несёт link_id/key_id в запросах.
export default function Shell() {
  const { setToken } = useAuth()
  const nav = useNavigate()
  const [status, setStatus] = useState('')
  const [ready, setReady] = useState(false)   // гейт: дети грузят данные по открытой сессии
  const [sessionOk, setSessionOk] = useState(false)
  const [needEnroll, setNeedEnroll] = useState(false)
  const care = getCare()

  useEffect(() => {
    if (care || sessionOk) { setReady(true); return }
    (async () => {
      try {
        await openSession()
        setSessionOk(true); setNeedEnroll(false)
        setReady(true)
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          setNeedEnroll(true)
          setReady(true)
          return
        }
        setStatus('нет связи с сервером: ' + (e as Error).message)
      }
    })()
  }, [care, sessionOk])

  const onEnrolled = () => setSessionOk(true)  // плитка на дашборде выпустила ключи

  const logout = () => { setCare(null); setToken(null); nav('/login') }
  const leaveCare = () => { setCare(null); nav('/patients') }

  return (
    <div className="app">
      <header>
        <NavLink to="/" className="brand" end>здоровье</NavLink>
        <nav className="topnav">
          <NavLink to="/" end>Сегодня</NavLink>
          <NavLink to="/profile">Моя карта</NavLink>
          <NavLink to="/access">Доступы</NavLink>
          <NavLink to="/patients">Доверили мне</NavLink>
        </nav>
        <button className="ghost right" onClick={logout}>Выйти</button>
      </header>
      {care && (
        <div className="care-banner">
          Карта пациента …{care.link_id.slice(-6)} — доступ по согласию
          <button className="ghost" onClick={leaveCare}>Выйти из карты</button>
        </div>
      )}
      <main>{ready
        ? <Outlet context={{ needEnroll, onEnrolled }} />
        : <p className="muted">{status || 'открываю сессию…'}</p>}</main>
    </div>
  )
}
