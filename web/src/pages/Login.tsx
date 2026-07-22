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
      <details className="data-protect">
        <summary>{ui('Как защищены ваши данные')}</summary>
        <ul>
          <li><b>{ui('Разделение.')}</b> {ui('Медкарта хранится под обезличенным псевдонимом, а имя и контакты — отдельно; связь между ними зашифрована.')}</li>
          <li><b>{ui('Шифрование.')}</b> {ui('Медицинская часть базы зашифрована. Мастер-ключ хранится в облачном хранилище ключей (Google Cloud KMS), не на сервере; каждый доступ к нему логируется и может быть мгновенно отозван.')}</li>
          <li><b>{ui('Доступ по согласию.')}</b> {ui('Врач или близкий видит вашу карту только когда вы это разрешили; согласие можно отозвать.')}</li>
          <li><b>{ui('Изоляция и аудит.')}</b> {ui('Доступ к строкам ограничен на уровне базы (RLS); все обращения к ключам пишутся в неизменяемый журнал.')}</li>
          <li><b>{ui('Транспорт и пароли.')}</b> {ui('Соединение по HTTPS; пароли хранятся только в виде необратимого хеша.')}</li>
        </ul>
        <p className="muted">{ui('Оценки делает ИИ (Google Gemini) — ему передаются медицинские данные без вашего имени; это вспомогательный инструмент, не диагноз.')}{' '}
          <Link to="/legal">{ui('Подробнее — в Пользовательском соглашении')}</Link>.</p>
      </details>
    </div>
  )
}
