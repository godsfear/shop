import { useEffect, useState } from 'react'
import { Outlet, Link, useNavigate } from 'react-router-dom'
import { openSession, ApiError } from '../api'
import { useAuth } from '../auth'

// Каркас: открывает owner-сессию. Мост ещё не выпущен (409) -> явный шаг
// онбординга /welcome (пользователь видит момент выпуска ключей).
export default function Shell() {
  const { setToken } = useAuth()
  const nav = useNavigate()
  const [status, setStatus] = useState('')
  const [ready, setReady] = useState(false)   // гейт: дети грузят данные по открытой сессии

  useEffect(() => {
    (async () => {
      try {
        await openSession()
        setReady(true)
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) { nav('/welcome'); return }
        setStatus('нет связи с сервером: ' + (e as Error).message)
      }
    })()
  }, [])

  const logout = () => { setToken(null); nav('/login') }

  return (
    <div className="app">
      <header>
        <Link to="/" className="brand">здоровье</Link>
        <span className="chip on">Моя карта</span>
        <button className="ghost right" onClick={logout}>Выйти</button>
      </header>
      <main>{ready ? <Outlet /> : <p className="muted">{status || 'открываю сессию…'}</p>}</main>
    </div>
  )
}
