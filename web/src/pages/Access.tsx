import { useEffect, useState } from 'react'
import {
  accessLog, consentApprove, consentDeny, consentGranted, consentIncoming,
  consentRevoke, me,
  type AccessLogEntry, type Consent,
} from '../api'
import { ui } from '../i18n'

const LOG_EVENTS: Record<string, string> = {
  'key.unwrap': 'просмотр карты',
  'key.unwrap.denied': 'отказ в доступе',
  'breakglass.execute': 'ЭКСТРЕННЫЙ доступ',
}

const TERMS: Record<string, number | null> = {
  'месяц': 30, 'год': 365, 'бессрочно': null,
}

function periodBounds(from: string, to: string) {
  const begins = from ? new Date(`${from}T00:00:00`).toISOString() : undefined
  let ends: string | undefined
  if (to) {
    const next = new Date(`${to}T00:00:00`)
    next.setDate(next.getDate() + 1) // дата «по» включительно
    ends = next.toISOString()
  }
  return { begins, ends }
}

function localDateValue(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function lastSevenDays() {
  const today = new Date()
  const from = new Date(today)
  from.setDate(from.getDate() - 6)
  return { from: localDateValue(from), to: localDateValue(today) }
}

const DEFAULT_LOG_PERIOD = lastSevenDays()

// Центр приватности владельца: входящие запросы, действующие доступы, код пациента.
export default function Access() {
  const [code, setCode] = useState('')
  const [incoming, setIncoming] = useState<Consent[]>([])
  const [granted, setGranted] = useState<Consent[]>([])
  const [log, setLog] = useState<AccessLogEntry[]>([])
  const [logFrom, setLogFrom] = useState(DEFAULT_LOG_PERIOD.from)
  const [logTo, setLogTo] = useState(DEFAULT_LOG_PERIOD.to)
  const [logErr, setLogErr] = useState('')
  const [logLoading, setLogLoading] = useState(false)
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)

  const load = async () => {
    try {
      setIncoming((await consentIncoming()).filter((c) => c.scope === 'medical'))
      setGranted(await consentGranted())
    } catch (e) { setErr((e as Error).message) }
  }

  const loadLog = async (from = logFrom, to = logTo) => {
    if (from && to && from > to) {
      setLogErr(ui('Начало периода не может быть позже окончания.'))
      return
    }
    setLogErr('')
    setLogLoading(true)
    try { setLog(await accessLog(periodBounds(from, to))) }
    catch (e) { setLogErr((e as Error).message) }
    finally { setLogLoading(false) }
  }

  const resetLogFilter = () => {
    setLogFrom(DEFAULT_LOG_PERIOD.from); setLogTo(DEFAULT_LOG_PERIOD.to)
    void loadLog(DEFAULT_LOG_PERIOD.from, DEFAULT_LOG_PERIOD.to)
  }

  const showAllLog = () => {
    setLogFrom(''); setLogTo('')
    void loadLog('', '')
  }

  useEffect(() => {
    me().then((u) => setCode(u.person)).catch(() => {})
    load()
    void loadLog(DEFAULT_LOG_PERIOD.from, DEFAULT_LOG_PERIOD.to)
  }, [])

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
      <h2>{ui('Доступ к моей карте')}</h2>
      {err && <p className="error">{err}</p>}

      <section>
        <h3>{ui('Код доступа')}</h3>
        <p className="muted">{ui('Сообщите его доверенному лицу (например, врачу) — оно запросит доступ, а решение всегда за вами. Код не раскрывает данные и не является псевдонимом — медзаписи им не адресуются.')}</p>
        <div className="inline">
          <code className="patient-code">{code || '…'}</code>
          <button className="ghost" onClick={copy}>{copied ? ui('Скопирован') : ui('Скопировать')}</button>
        </div>
      </section>

      <section>
        <h3>{ui('Входящие запросы')}</h3>
        {incoming.length === 0 && <p className="muted">{ui('Новых запросов нет.')}</p>}
        <ul className="cards">
          {incoming.map((c) => (
            <li key={c.id} className="card">
              <p><b>{c.reason || ui('без представления')}</b>
                <span className="muted"> · {new Date(c.begins).toLocaleDateString()}</span></p>
              <div className="inline">
                <span className="muted">{ui('разрешить на:')}</span>
                {Object.entries(TERMS).map(([label, days]) => (
                  <button key={label} onClick={() => decide(c, days)}>{ui(label)}</button>
                ))}
                <button className="ghost" onClick={() => decide(c, 'deny')}>{ui('Отказать')}</button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <details className="access-log">
          <summary>
            <span className="access-log-chevron" aria-hidden="true" />
            <h3>{ui('Журнал доступов')}</h3>
            <span className="muted">{log.length}</span>
          </summary>
          <p className="muted">{ui('Каждый разворот доступа к карте пишется в защищённый от подделки журнал (включая отказы и экстренные доступы). Повторные обращения в пределах ~5 минут не дублируются.')}</p>
          <div className="inline access-log-filter">
            <label>
              <span>{ui('С')}</span>
              <input type="date" value={logFrom}
                     max={logTo || undefined}
                     onChange={(e) => { setLogFrom(e.target.value); setLogErr('') }} />
            </label>
            <label>
              <span>{ui('По')}</span>
              <input type="date" value={logTo}
                     min={logFrom || undefined}
                     onChange={(e) => { setLogTo(e.target.value); setLogErr('') }} />
            </label>
            <button onClick={() => loadLog()} disabled={logLoading}>
              {logLoading ? ui('Загрузка…') : ui('Применить')}
            </button>
            <button className="ghost" onClick={resetLogFilter}>{ui('7 дней')}</button>
            <button className="ghost" onClick={showAllLog}>{ui('Всё время')}</button>
          </div>
          {logErr && <p className="error">{logErr}</p>}
          {!logLoading && log.length === 0 &&
            <p className="muted">{ui('записей за период нет')}</p>}
          {log.length > 0 && (
            <div className="access-log-scroll">
              <ul className="rows">
                {log.map((e, i) => (
                  <li key={`${e.at}-${i}`} className="row-link access-log-row">
                    <span className={e.event === 'key.unwrap' ? '' : 'error'}>
                      {ui(LOG_EVENTS[e.event] ?? e.event)}</span>
                    <span>{e.who}</span>
                    <span className="muted">{new Date(e.at).toLocaleString()}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </details>
      </section>

      <section>
        <h3>{ui('Кто видит карту')}</h3>
        {granted.length === 0 && <p className="muted">{ui('Доступов нет — карту видите только вы.')}</p>}
        <ul className="cards">
          {granted.map((c) => (
            <li key={c.id} className="card">
              <p><b>{c.reason || ui('доступ')}</b>
                <span className="muted"> · {c.until
                  ? ui('до') + ' ' + new Date(c.until).toLocaleDateString() : ui('бессрочно')}</span></p>
              <div className="inline">
                <button className="ghost" onClick={() => revoke(c)}>{ui('Отозвать')}</button>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
