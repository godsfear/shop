import { useEffect, useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import {
  ApiError, confirmEmail, enroll, getCare, me, openSession, resendConfirm, setCare,
} from '../api'
import { useAuth } from '../auth'
import { loadMeta } from '../ui'

// Плашка «подтвердите почту»: код из письма; без подтверждения нельзя
// запрашивать чужие карты (контроль регистрируемых).
function ConfirmBanner({ onDone }: { onDone: () => void }) {
  const [code, setCode] = useState('')
  const [msg, setMsg] = useState('')
  const submit = async () => {
    setMsg('')
    try { await confirmEmail(code.trim()); onDone() }
    catch (e) { setMsg((e as Error).message) }
  }
  const resend = async () => {
    setMsg('')
    try { await resendConfirm(); setMsg('код отправлен повторно') }
    catch (e) { setMsg((e as Error).message) }
  }
  return (
    <div className="confirm-banner">
      <span>Подтвердите почту — код в письме.</span>
      <input placeholder="код из письма" value={code} inputMode="numeric"
             onChange={(e) => setCode(e.target.value)} />
      <button onClick={submit} disabled={!code.trim()}>Подтвердить</button>
      <button className="ghost" onClick={resend}>Выслать снова</button>
      {msg && <span className="msg-note">{msg}</span>}
    </div>
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
  const [confirmed, setConfirmed] = useState(true)  // до ответа сервера плашку не мигаем
  const care = getCare()

  useEffect(() => {
    me().then((u) => setConfirmed(u.confirmed)).catch(() => {})
  }, [])

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
          } catch (e2) { setStatus('не удалось открыть карту: ' + (e2 as Error).message); return }
        } else {
          setStatus('нет связи с сервером: ' + (e as Error).message)
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
      {!confirmed && <ConfirmBanner onDone={() => setConfirmed(true)} />}
      <main>{ready ? <Outlet /> : <p className="muted">{status || 'открываю сессию…'}</p>}</main>
    </div>
  )
}
