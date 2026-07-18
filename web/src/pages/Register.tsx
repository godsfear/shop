import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { signupStart, signupConfirm } from '../api'
import { useAuth } from '../auth'
import { ui } from '../i18n'
import { LangSwitch } from './Shell'

// требования к паролю — зеркало бэковой password_issues (models/user.py):
// \p{Ll}/\p{Lu} юникодные, как str.islower/isupper (кириллица считается)
const PW_RULES: [string, (p: string) => boolean][] = [
  ['не короче 8 символов', (p) => p.length >= 8],
  ['строчную букву', (p) => /\p{Ll}/u.test(p)],
  ['заглавную букву', (p) => /\p{Lu}/u.test(p)],
  ['цифру', (p) => /\d/.test(p)],
]

// Регистрация в два шага (учётка создаётся только после кода из письма):
// форма -> код на почту -> подтверждение -> токен
export default function Register() {
  const { setToken } = useAuth()
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [last, setLast] = useState('')
  const [first, setFirst] = useState('')
  const [sex, setSex] = useState('true')
  const [birthdate, setBirthdate] = useState('1990-01-01')
  const [code, setCode] = useState('')
  const [stage, setStage] = useState<'form' | 'code'>('form')
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const pwOk = PW_RULES.every(([, ok]) => ok(password))

  const start = async (e: FormEvent) => {
    e.preventDefault()
    setErr(''); setMsg('')
    try {
      await signupStart(email, password, last.trim(), first.trim(), sex === 'true', birthdate)
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
      await signupStart(email, password, last.trim(), first.trim(), sex === 'true', birthdate)
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
          <input type="password" placeholder={ui('пароль')} value={password}
                 onChange={(e) => setPassword(e.target.value)} />
          {/* живой чек-лист: чего не хватает паролю; исчезает, когда всё ✓ */}
          {password && !pwOk && (
            <ul className="pw-rules">
              {PW_RULES.map(([label, ok]) => (
                <li key={label} className={ok(password) ? 'ok' : ''}>
                  {ok(password) ? '✓' : '○'} {ui(label)}
                </li>
              ))}
            </ul>
          )}
          <input placeholder={ui('фамилия')} value={last} onChange={(e) => setLast(e.target.value)} />
          <input placeholder={ui('имя')} value={first} onChange={(e) => setFirst(e.target.value)} />
          <label className="row">{ui('Пол')}
            <select value={sex} onChange={(e) => setSex(e.target.value)}>
              <option value="true">{ui('муж')}</option>
              <option value="false">{ui('жен')}</option>
            </select>
          </label>
          <label className="row">{ui('Дата рождения')}
            <input type="date" value={birthdate} onChange={(e) => setBirthdate(e.target.value)} />
          </label>
          {/* имя/фамилия обязательны: ими врач представляется пациенту и наоборот */}
          <button type="submit" disabled={!email.trim() || !pwOk || !last.trim() || !first.trim()}>
            {ui('Получить код')}
          </button>
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
