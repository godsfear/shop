import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { signup } from '../api'
import { useAuth } from '../auth'
import { ui } from '../i18n'
import { LangSwitch } from './Shell'

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
      <h1>{ui('Медкарта')} <LangSwitch /></h1>
      <form onSubmit={submit}>
        <h2>{ui('Регистрация')}</h2>
        {err && <p className="error">{err}</p>}
        <input placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input type="password" placeholder={ui('пароль (≥8 символов)')} value={password}
               onChange={(e) => setPassword(e.target.value)} />
        <input placeholder={ui('фамилия')} value={last} onChange={(e) => setLast(e.target.value)} />
        <label className="row">{ui('Пол')}
          <select value={sex} onChange={(e) => setSex(e.target.value)}>
            <option value="true">{ui('муж')}</option>
            <option value="false">{ui('жен')}</option>
          </select>
        </label>
        <label className="row">{ui('Дата рождения')}
          <input type="date" value={birthdate} onChange={(e) => setBirthdate(e.target.value)} />
        </label>
        <button type="submit">{ui('Создать аккаунт')}</button>
        <p className="muted">{ui('Уже есть аккаунт?')} <Link to="/login">{ui('Вход')}</Link></p>
      </form>
    </div>
  )
}
