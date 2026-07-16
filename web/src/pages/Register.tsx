import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { signupStart, signupConfirm } from '../api'
import { useAuth } from '../auth'
import { ui } from '../i18n'
import { LangSwitch } from './Shell'

// Регистрация в два шага (учётка создаётся только после кода из письма):
// форма -> код на почту -> подтверждение -> токен
export default function Register() {
  const { setToken } = useAuth()
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [last, setLast] = useState('')
  const [sex, setSex] = useState('true')
  const [birthdate, setBirthdate] = useState('1990-01-01')
  const [code, setCode] = useState('')
  const [stage, setStage] = useState<'form' | 'code'>('form')
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')

  const start = async (e: FormEvent) => {
    e.preventDefault()
    setErr(''); setMsg('')
    try {
      await signupStart(email, password, last, sex === 'true', birthdate)
      setStage('code')
    } catch (e) { setErr((e as Error).message) }
  }

  const confirm = async (e: FormEvent) => {
    e.preventDefault()
    setErr('')
    try {
      setToken(await signupConfirm(email, code.trim()))
      nav('/')
    } catch (e) { setErr((e as Error).message) }
  }

  const resend = async () => {
    setErr(''); setMsg('')
    try {
      await signupStart(email, password, last, sex === 'true', birthdate)
      setMsg(ui('код отправлен повторно'))
    } catch (e) { setErr((e as Error).message) }
  }

  return (
    <div className="auth">
      <h1>{ui('Медкарта')} <LangSwitch /></h1>
      {stage === 'form' ? (
        <form onSubmit={start}>
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
          <button type="submit" disabled={!email.trim() || !password}>{ui('Получить код')}</button>
          <p className="muted">{ui('Уже есть аккаунт?')} <Link to="/login">{ui('Вход')}</Link></p>
        </form>
      ) : (
        <form onSubmit={confirm}>
          <h2>{ui('Код из письма')}</h2>
          <p className="muted">{ui('Мы отправили код на')} {email}. {ui('Учётная запись появится после подтверждения.')}</p>
          {err && <p className="error">{err}</p>}
          {msg && <p className="muted">{msg}</p>}
          <input placeholder={ui('код из письма')} value={code} inputMode="numeric" autoFocus
                 onChange={(e) => setCode(e.target.value)} />
          <button type="submit" disabled={!code.trim()}>{ui('Создать аккаунт')}</button>
          <div className="inline">
            <button type="button" className="ghost" onClick={resend}>{ui('Выслать снова')}</button>
            <button type="button" className="ghost" onClick={() => { setStage('form'); setCode('') }}>
              {ui('Назад')}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
