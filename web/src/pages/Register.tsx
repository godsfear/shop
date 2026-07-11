import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { signup } from '../api'
import { useAuth } from '../auth'

export default function Register() {
  const { setToken } = useAuth()
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [last, setLast] = useState('')
  const [sex, setSex] = useState('true')
  const [birthdate, setBirthdate] = useState('1990-01-01')
  const [err, setErr] = useState('')

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setErr('')
    try {
      setToken(await signup(email, password, last, sex === 'true', birthdate))
      nav('/')
    } catch (e) {
      setErr((e as Error).message)
    }
  }

  return (
    <div className="auth">
      <h1>Медкарта</h1>
      <form onSubmit={submit}>
        <h2>Регистрация</h2>
        {err && <p className="error">{err}</p>}
        <input placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input type="password" placeholder="пароль (≥8 символов)" value={password}
               onChange={(e) => setPassword(e.target.value)} />
        <input placeholder="фамилия" value={last} onChange={(e) => setLast(e.target.value)} />
        <label className="row">Пол
          <select value={sex} onChange={(e) => setSex(e.target.value)}>
            <option value="true">муж</option>
            <option value="false">жен</option>
          </select>
        </label>
        <label className="row">Дата рождения
          <input type="date" value={birthdate} onChange={(e) => setBirthdate(e.target.value)} />
        </label>
        <button type="submit">Создать аккаунт</button>
        <p className="muted">Уже есть аккаунт? <Link to="/login">Вход</Link></p>
      </form>
    </div>
  )
}
