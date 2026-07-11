import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { signin } from '../api'
import { useAuth } from '../auth'

export default function Login() {
  const { setToken } = useAuth()
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setErr('')
    try {
      setToken(await signin(email, password))
      nav('/')
    } catch (e) {
      setErr((e as Error).message)
    }
  }

  return (
    <div className="auth">
      <h1>Медкарта</h1>
      <form onSubmit={submit}>
        <h2>Вход</h2>
        {err && <p className="error">{err}</p>}
        <input placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input type="password" placeholder="пароль" value={password}
               onChange={(e) => setPassword(e.target.value)} />
        <button type="submit">Войти</button>
        <p className="muted">Нет аккаунта? <Link to="/register">Регистрация</Link></p>
      </form>
    </div>
  )
}
