import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { signin } from '../api'
import { useAuth } from '../auth'
import { ui } from '../i18n'
import { PasswordField } from '../PasswordField'
import { LangSwitch } from './Shell'

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
      <h1>{ui('Медкарта')} <LangSwitch /></h1>
      <form onSubmit={submit}>
        <h2>{ui('Вход')}</h2>
        {err && <p className="error">{err}</p>}
        <input placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <PasswordField placeholder={ui('пароль')} value={password}
                       autoComplete="current-password"
                       onChange={(e) => setPassword(e.target.value)} />
        <button type="submit">{ui('Войти')}</button>
        <p className="muted"><Link to="/reset">{ui('Забыли пароль?')}</Link></p>
        <p className="muted">{ui('Нет аккаунта?')} <Link to="/register">{ui('Регистрация')}</Link></p>
      </form>
    </div>
  )
}
