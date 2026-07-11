import { useEffect, useState } from 'react'
import { Outlet, Link, useNavigate } from 'react-router-dom'
import { enroll, openSession } from '../api'
import { useAuth } from '../auth'

// Каркас: при входе идемпотентно выпускает мост (enroll) и открывает медсессию.
// Псевдоним разворачивается на сервере — фронт его не видит.
export default function Shell() {
  const { setToken } = useAuth()
  const nav = useNavigate()
  const [status, setStatus] = useState('открываю сессию…')
  const [ready, setReady] = useState(false)   // гейт: дети грузят данные только по открытой сессии

  useEffect(() => {
    (async () => {
      try {
        await enroll()
        await openSession()
        setStatus('сессия активна')
        setReady(true)
      } catch (e) {
        setStatus('ошибка сессии: ' + (e as Error).message)
      }
    })()
  }, [])

  const logout = () => { setToken(null); nav('/login') }

  return (
    <div className="app">
      <header>
        <Link to="/" className="brand">Медкарта</Link>
        <span className="status">{status}</span>
        <button onClick={logout}>Выйти</button>
      </header>
      <main>{ready ? <Outlet /> : <p className="muted">{status}</p>}</main>
    </div>
  )
}
