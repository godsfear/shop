import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { enroll, openSession } from '../api'

// Явный шаг онбординга: выпуск ключей приватности (enroll). Сюда позже встанет
// клиентский owner-ключ — пользователь должен видеть момент выпуска, а не магию.
export default function Welcome() {
  const nav = useNavigate()
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const start = async () => {
    setBusy(true); setErr('')
    try {
      await enroll()
      await openSession()
      nav('/', { replace: true })
    } catch (e) {
      setErr((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <div className="auth welcome">
      <h1>Ваши данные — под псевдонимом</h1>
      <div className="card panel">
        <p>Медицинские записи хранятся отдельно от вашего имени — под случайным
        псевдонимом. Связывает их только зашифрованный мост, ключ от которого
        принадлежит вам.</p>
        <ul className="muted">
          <li>исследователи и статистика не видят, чьи это данные;</li>
          <li>врач получает доступ только по вашему явному согласию — и вы можете
          отозвать его в любой момент;</li>
          <li>экстренный доступ без вас возможен только по протоколу «двух подтверждений»
          — и вы получите уведомление.</li>
        </ul>
        {err && <p className="error">{err}</p>}
        <button onClick={start} disabled={busy}>
          {busy ? 'Выпускаю ключи…' : 'Выпустить ключи и начать'}
        </button>
      </div>
    </div>
  )
}
