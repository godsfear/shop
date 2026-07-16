import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  consentMine, consentRequest, listGrants, setCare,
  type Consent, type Grant,
} from '../api'
import { STATES, t } from '../ui'
import { ui } from '../i18n'

const REQ_STATES: Record<string, string> = {
  requested: 'ожидает решения', approved: 'одобрено',
  denied: 'отказано', revoked: 'отозвано', expired: 'истекло',
}

// Режим специалиста: запрос доступа по коду пациента, мои запросы, доступные карты.
export default function Patients() {
  const nav = useNavigate()
  const [grants, setGrants] = useState<Grant[]>([])
  const [mine, setMine] = useState<Consent[]>([])
  const [code, setCode] = useState('')
  const [reason, setReason] = useState('')
  const [err, setErr] = useState('')
  const [sent, setSent] = useState(false)

  const load = async () => {
    try {
      setGrants(await listGrants())
      setMine((await consentMine()).filter((c) => c.scope === 'medical'))
    } catch (e) { setErr((e as Error).message) }
  }
  useEffect(() => { load() }, [])

  const request = async (e: FormEvent) => {
    e.preventDefault()
    setErr(''); setSent(false)
    try {
      await consentRequest(code.trim(), reason.trim() || ui('запрос доступа'))
      setCode(''); setReason(''); setSent(true)
      await load()
    } catch (e) { setErr((e as Error).message) }
  }

  const open = (g: Grant) => {
    setCare(g)          // все /me-запросы дальше идут в карту пациента (Слой B)
    nav('/')
  }

  return (
    <div>
      <h2>{ui('Доверили мне')}</h2>
      {err && <p className="error">{err}</p>}

      <section>
        <h3>{ui('Запросить доступ')}</h3>
        <p className="muted">{ui('Владелец карты сообщает вам код доступа со страницы «Доступы» и сам одобряет запрос — и может отозвать его в любой момент.')}</p>
        <form className="inline" onSubmit={request}>
          <input placeholder={ui('код доступа владельца')} value={code}
                 onChange={(e) => setCode(e.target.value)} />
          <input placeholder={ui('представьтесь (видно пациенту)')} value={reason}
                 onChange={(e) => setReason(e.target.value)} />
          <button type="submit" disabled={!code.trim()}>{ui('Запросить')}</button>
        </form>
        {sent && <p className="muted">{ui('Запрос отправлен — ждёт решения пациента.')}</p>}
      </section>

      {mine.length > 0 && (
        <section>
          <h3>{ui('Мои запросы')}</h3>
          <ul className="rows">
            {mine.map((c) => (
              <li key={c.id} className="row-link">
                <span>{c.reason || ui('запрос')}</span>
                <span className="chip state">{ui(REQ_STATES[c.status] ?? t(STATES, c.status))}</span>
                <span className="muted">{new Date(c.begins).toLocaleDateString()}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h3>{ui('Доступные карты')}</h3>
        {grants.length === 0 && <p className="muted">{ui('Одобренных доступов пока нет.')}</p>}
        <ul className="cards">
          {grants.map((g) => (
            <li key={g.link_id} className="card">
              <div className="inline">
                <span>{ui('Карта пациента')} <span className="muted">…{g.link_id.slice(-6)}</span></span>
                <button onClick={() => open(g)}>{ui('Открыть карту')}</button>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
