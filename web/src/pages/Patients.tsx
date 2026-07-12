import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  consentMine, consentRequest, listGrants, setCare,
  type Consent, type Grant,
} from '../api'
import { STATES, t } from '../ui'

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
      await consentRequest(code.trim(), reason.trim() || 'запрос доступа')
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
      <h2>Пациенты</h2>
      {err && <p className="error">{err}</p>}

      <section>
        <h3>Запросить доступ</h3>
        <p className="muted">Пациент сообщает вам код со страницы «Доступы» и сам
        одобряет запрос — доступ можно отозвать в любой момент.</p>
        <form className="inline" onSubmit={request}>
          <input placeholder="код пациента" value={code}
                 onChange={(e) => setCode(e.target.value)} />
          <input placeholder="представьтесь (видно пациенту)" value={reason}
                 onChange={(e) => setReason(e.target.value)} />
          <button type="submit" disabled={!code.trim()}>Запросить</button>
        </form>
        {sent && <p className="muted">Запрос отправлен — ждёт решения пациента.</p>}
      </section>

      {mine.length > 0 && (
        <section>
          <h3>Мои запросы</h3>
          <ul className="rows">
            {mine.map((c) => (
              <li key={c.id} className="row-link">
                <span>{c.reason || 'запрос'}</span>
                <span className="chip state">{REQ_STATES[c.status] ?? t(STATES, c.status)}</span>
                <span className="muted">{new Date(c.begins).toLocaleDateString()}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h3>Доступные карты</h3>
        {grants.length === 0 && <p className="muted">Одобренных доступов пока нет.</p>}
        <ul className="cards">
          {grants.map((g) => (
            <li key={g.link_id} className="card">
              <div className="inline">
                <span>Карта пациента <span className="muted">…{g.link_id.slice(-6)}</span></span>
                <button onClick={() => open(g)}>Открыть карту</button>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
