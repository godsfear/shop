import { useEffect, useState } from 'react'
import {
  accessLog, consentApprove, consentDeny, consentGranted, consentIncoming,
  consentRevoke, me,
  type AccessLogEntry, type Consent,
} from '../api'

const LOG_EVENTS: Record<string, string> = {
  'key.unwrap': 'просмотр карты',
  'key.unwrap.denied': 'отказ в доступе',
  'breakglass.execute': 'ЭКСТРЕННЫЙ доступ',
}

const TERMS: Record<string, number | null> = {
  'месяц': 30, 'год': 365, 'бессрочно': null,
}

// Центр приватности владельца: входящие запросы, действующие доступы, код пациента.
export default function Access() {
  const [code, setCode] = useState('')
  const [incoming, setIncoming] = useState<Consent[]>([])
  const [granted, setGranted] = useState<Consent[]>([])
  const [log, setLog] = useState<AccessLogEntry[]>([])
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)

  const load = async () => {
    try {
      setIncoming((await consentIncoming()).filter((c) => c.scope === 'medical'))
      setGranted(await consentGranted())
      setLog(await accessLog().catch(() => []))  // журнал пуст, если карта не выпущена
    } catch (e) { setErr((e as Error).message) }
  }
  useEffect(() => { me().then((u) => setCode(u.person)).catch(() => {}); load() }, [])

  const decide = async (c: Consent, days: number | null | 'deny') => {
    setErr('')
    try {
      if (days === 'deny') await consentDeny(c.id)
      else await consentApprove(c.id, days === null ? null :
        new Date(Date.now() + days * 864e5).toISOString())
      await load()
    } catch (e) { setErr((e as Error).message) }
  }

  const revoke = async (c: Consent) => {
    setErr('')
    try { await consentRevoke(c.id); await load() }
    catch (e) { setErr((e as Error).message) }
  }

  const copy = async () => {
    await navigator.clipboard.writeText(code)
    setCopied(true); setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div>
      <h2>Доступ к моей карте</h2>
      {err && <p className="error">{err}</p>}

      <section>
        <h3>Код доступа</h3>
        <p className="muted">Сообщите его доверенному лицу (например, врачу) — оно
        запросит доступ, а решение всегда за вами. Код не раскрывает данные и
        не является псевдонимом — медзаписи им не адресуются.</p>
        <div className="inline">
          <code className="patient-code">{code || '…'}</code>
          <button className="ghost" onClick={copy}>{copied ? 'Скопирован' : 'Скопировать'}</button>
        </div>
      </section>

      <section>
        <h3>Входящие запросы</h3>
        {incoming.length === 0 && <p className="muted">Новых запросов нет.</p>}
        <ul className="cards">
          {incoming.map((c) => (
            <li key={c.id} className="card">
              <p><b>{c.reason || 'без представления'}</b>
                <span className="muted"> · {new Date(c.begins).toLocaleDateString()}</span></p>
              <div className="inline">
                <span className="muted">разрешить на:</span>
                {Object.entries(TERMS).map(([label, days]) => (
                  <button key={label} onClick={() => decide(c, days)}>{label}</button>
                ))}
                <button className="ghost" onClick={() => decide(c, 'deny')}>Отказать</button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3>Журнал доступов</h3>
        <p className="muted">Каждый разворот доступа к карте пишется в защищённый
        от подделки журнал (включая отказы и экстренные доступы). Повторные
        обращения в пределах ~5 минут не дублируются.</p>
        {log.length === 0 && <p className="muted">записей пока нет</p>}
        <ul className="rows">
          {log.map((e, i) => (
            <li key={i} className="row-link">
              <span className={e.event === 'key.unwrap' ? '' : 'error'}>
                {LOG_EVENTS[e.event] ?? e.event}</span>
              <span>{e.who}</span>
              <span className="muted">{new Date(e.at).toLocaleString()}</span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3>Кто видит карту</h3>
        {granted.length === 0 && <p className="muted">Доступов нет — карту видите только вы.</p>}
        <ul className="cards">
          {granted.map((c) => (
            <li key={c.id} className="card">
              <p><b>{c.reason || 'доступ'}</b>
                <span className="muted"> · {c.until
                  ? 'до ' + new Date(c.until).toLocaleDateString() : 'бессрочно'}</span></p>
              <div className="inline">
                <button className="ghost" onClick={() => revoke(c)}>Отозвать</button>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
