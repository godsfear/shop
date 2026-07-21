import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { requestReset, confirmReset } from '../api'
import { ui } from '../i18n'
import { LangSwitch } from './Shell'

// требования к паролю — зеркало бэковой password_issues (models/user.py)
const PW_RULES: [string, (p: string) => boolean][] = [
  ['не короче 8 символов', (p) => p.length >= 8],
  ['строчную букву', (p) => /\p{Ll}/u.test(p)],
  ['заглавную букву', (p) => /\p{Lu}/u.test(p)],
  ['цифру', (p) => /\d/.test(p)],
]

// Восстановление пароля в два шага: email -> код на почту -> новый пароль.
// Шаг 1 всегда «успешен» (сервер не палит, есть ли адрес) — сразу к вводу кода.
export default function Reset() {
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [stage, setStage] = useState<'email' | 'code' | 'done'>('email')
  const [err, setErr] = useState('')
  const pwOk = PW_RULES.every(([, ok]) => ok(password))

  const start = async (e: FormEvent) => {
    e.preventDefault()
    setErr('')
    try {
      await requestReset(email.trim())
      setStage('code')
    } catch (e) { setErr((e as Error).message) }
  }

  const confirm = async (e: FormEvent) => {
    e.preventDefault()
    setErr('')
    try {
      await confirmReset(email.trim(), code.trim(), password)
      setStage('done')
    } catch (e) { setErr((e as Error).message) }
  }

  return (
    <div className="auth">
      <h1>{ui('Медкарта')} <LangSwitch /></h1>
      {stage === 'email' ? (
        <form onSubmit={start}>
          <h2>{ui('Восстановление пароля')}</h2>
          {err && <p className="error">{err}</p>}
          <p className="muted">{ui('Введите email — вышлем код для смены пароля.')}</p>
          <input placeholder="email" value={email} autoFocus
                 onChange={(e) => setEmail(e.target.value)} />
          <button type="submit" disabled={!email.trim()}>{ui('Получить код')}</button>
          <p className="muted"><Link to="/login">{ui('← ко входу')}</Link></p>
        </form>
      ) : stage === 'code' ? (
        <form onSubmit={confirm}>
          <h2>{ui('Новый пароль')}</h2>
          <p className="muted">{ui('Если такой адрес зарегистрирован, на него отправлен код.')}</p>
          {err && <p className="error">{err}</p>}
          <input placeholder={ui('код из письма')} value={code} inputMode="numeric" autoFocus
                 onChange={(e) => setCode(e.target.value)} />
          <input type="password" placeholder={ui('новый пароль')} value={password}
                 onChange={(e) => setPassword(e.target.value)} />
          {password && !pwOk && (
            <ul className="pw-rules">
              {PW_RULES.map(([label, ok]) => (
                <li key={label} className={ok(password) ? 'ok' : ''}>
                  {ok(password) ? '✓' : '○'} {ui(label)}
                </li>
              ))}
            </ul>
          )}
          <input type="password" placeholder={ui('повторите пароль')} value={password2}
                 onChange={(e) => setPassword2(e.target.value)} />
          {password2 && password2 !== password &&
            <p className="error">{ui('пароли не совпадают')}</p>}
          <button type="submit" disabled={!code.trim() || !pwOk || password2 !== password}>
            {ui('Сменить пароль')}
          </button>
          <div className="inline">
            <button type="button" className="ghost"
                    onClick={() => { setStage('email'); setCode('') }}>{ui('Назад')}</button>
          </div>
        </form>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); nav('/login') }}>
          <h2>{ui('Пароль изменён')}</h2>
          <p className="muted">{ui('Теперь войдите с новым паролем.')}</p>
          <button type="submit">{ui('Войти')}</button>
        </form>
      )}
    </div>
  )
}
