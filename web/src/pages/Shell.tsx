import { useEffect, useState } from 'react'
import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { openSession, getCare, setCare, ApiError } from '../api'
import { useAuth } from '../auth'

// Страницы, которым owner-сессия не нужна: согласия и Слой B работают без неё —
// специалист без собственной карты не должен упираться в онбординг.
const GUEST_OK = ['/access', '/patients']

// Каркас: открывает owner-сессию (мост не выпущен: 409 -> явный онбординг /welcome).
// В режиме «Пациенты» (care) сессия не нужна — Слой B несёт link_id/key_id в запросах.
export default function Shell() {
  const { setToken } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  const [status, setStatus] = useState('')
  const [ready, setReady] = useState(false)   // гейт: дети грузят данные по открытой сессии
  const [sessionOk, setSessionOk] = useState(false)
  const care = getCare()

  useEffect(() => {
    if (care || sessionOk) { setReady(true); return }
    (async () => {
      try {
        await openSession()
        setSessionOk(true)
        setReady(true)
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          if (GUEST_OK.includes(loc.pathname)) { setReady(true); return }
          nav('/welcome'); return
        }
        setStatus('нет связи с сервером: ' + (e as Error).message)
      }
    })()
  }, [care, loc.pathname])

  const logout = () => { setCare(null); setToken(null); nav('/login') }
  const leaveCare = () => { setCare(null); nav('/patients') }

  return (
    <div className="app">
      <header>
        <NavLink to="/" className="brand" end>здоровье</NavLink>
        <nav className="topnav">
          <NavLink to="/" end>Сегодня</NavLink>
          <NavLink to="/access">Доступы</NavLink>
          <NavLink to="/patients">Пациенты</NavLink>
        </nav>
        <button className="ghost right" onClick={logout}>Выйти</button>
      </header>
      {care && (
        <div className="care-banner">
          Карта пациента …{care.link_id.slice(-6)} — доступ по согласию
          <button className="ghost" onClick={leaveCare}>Выйти из карты</button>
        </div>
      )}
      <main>{ready ? <Outlet /> : <p className="muted">{status || 'открываю сессию…'}</p>}</main>
    </div>
  )
}
