import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  listEpisodes, createEpisode, episodeState, concepts, getNutrition, getSleep,
  type Episode, type Concepts, type Nutrition, type SleepJournal,
} from '../api'
import { MacroBar, localDay } from './Nutrition'
import { KINDS, STATES, t } from '../ui'
import { ui } from '../i18n'

// available пуст -> маршрут завершён: эпизод уходит в «Историю болезни»
interface EpisodeRow extends Episode { fsm?: string; closed?: boolean }

function EpisodeLink({ ep }: { ep: EpisodeRow }) {
  return (
    <Link to={`/episode/${ep.id}`} className="row-link">
      <span>{ep.name || ep.code}</span>
      {ep.fsm && <span className="chip state">{t(STATES, ep.fsm)}</span>}
      <span className="muted">{new Date(ep.begins).toLocaleDateString()}</span>
    </Link>
  )
}

// Дашборд «Сегодня»: сетка плиток-трекеров. Эпизоды — первая плитка;
// сон/нагрузки/питание зарезервированы пунктиром (перспектива, сетка не меняется).
export default function Dashboard() {
  const nav = useNavigate()
  const [eps, setEps] = useState<EpisodeRow[]>([])
  const [cs, setCs] = useState<Concepts>({})
  const [err, setErr] = useState('')
  const [creating, setCreating] = useState(false)
  const [nutri, setNutri] = useState<Nutrition | null>(null)
  const [sleep, setSleep] = useState<SleepJournal | null>(null)

  const load = async () => {
    try {
      const list = await listEpisodes()
      // состояние каждого эпизода — параллельно; упавшие не роняют дашборд
      const states = await Promise.allSettled(list.map((e) => episodeState(e.id)))
      setEps(list.map((e, i) => {
        const st = states[i]
        return st.status === 'fulfilled'
          ? { ...e, fsm: st.value.state, closed: st.value.available.length === 0 }
          : { ...e }
      }))
    } catch (e) { setErr((e as Error).message) }
  }
  useEffect(() => {
    concepts().then((c) => {
      setCs(c)
      if (Object.keys(c).length === 0)
        setErr(ui('Справочник пуст — на сервере не прогнан медицинский сид') +
               ' (uv run python scripts/bootstrap_dev.py)')
    }).catch((e) => setErr((e as Error).message))
    load()
    getNutrition(localDay()).then(setNutri).catch(() => {})
    getSleep().then(setSleep).catch(() => {})
  }, [])

  // эпизод открывается жалобой, а не диагнозом: имени пока нет — авто по дате;
  // назвать можно на странице эпизода, когда диагноз поставлен
  const create = async (kind: string) => {
    setErr('')
    const cat = cs[kind]
    if (!cat) return
    try {
      const auto = `${t(KINDS, kind)} ${ui('от')} ${new Date().toLocaleDateString()}`
      const ep = await createEpisode(cat, `ep-${Date.now()}`,
        auto[0].toUpperCase() + auto.slice(1))
      nav(`/episode/${ep.id}`)
    } catch (e) { setErr((e as Error).message) }
  }

  const active = eps.filter((e) => !e.closed)
  const closed = eps.filter((e) => e.closed)

  return (
    <div className="tiles">
      {err && <p className="error" style={{ gridColumn: '1 / -1' }}>{err}</p>}

      <section className="tile">
        <header><h3>{ui('Эпизоды')}</h3>
          <button className="ghost" onClick={() => setCreating(!creating)}
                  disabled={!Object.keys(cs).length}>
            {creating ? ui('Отмена') : ui('+ Новый')}
          </button>
        </header>
        {creating && (
          <div className="inline">
            <span className="muted">{ui('Что случилось?')}</span>
            {Object.entries(KINDS).map(([k, label]) => (
              <button key={k} onClick={() => create(k)}>{label}</button>
            ))}
          </div>
        )}
        {active.length === 0 && !creating &&
          <p className="muted">{ui('Сейчас ничего не беспокоит. Заболели или травма — откройте эпизод.')}</p>}
        <ul className="rows">
          {active.map((ep) => <li key={ep.id}><EpisodeLink ep={ep} /></li>)}
        </ul>
        {closed.length > 0 && (
          <details className="log">
            <summary>{ui('История болезни')} ({closed.length})</summary>
            <ul className="rows">
              {closed.map((ep) => <li key={ep.id}><EpisodeLink ep={ep} /></li>)}
            </ul>
          </details>
        )}
      </section>

      {/* питание: сегодняшние ккал против нормы ИИ; вся лента — на /nutrition */}
      <section className="tile">
        <header><h3>{ui('Питание')}</h3>
          <Link to="/nutrition"><button className="ghost">{ui('Открыть')}</button></Link>
        </header>
        {nutri ? (
          <>
            <MacroBar label={ui('калории')} got={nutri.totals.kcal ?? 0}
                      norm={nutri.norm?.kcal} unit={ui('ккал')} />
            <MacroBar label={ui('белки')} got={nutri.totals.protein ?? 0}
                      norm={nutri.norm?.protein_g} unit={ui('г')} />
            <p className="muted">{nutri.meals.length
              ? `${ui('приёмов сегодня')}: ${nutri.meals.length}`
              : ui('Сфотографируйте или опишите еду — ИИ посчитает калории.')}</p>
          </>
        ) : <p className="muted">…</p>}
      </section>

      <section className="tile">
        <header><h3>{ui('Сон')}</h3>
          <Link to="/sleep"><button className="ghost">{ui('Открыть')}</button></Link>
        </header>
        {sleep?.assessment?.summary ? (
          <>
            {sleep.assessment.quality && sleep.assessment.quality !== '—' &&
              <p><b>{ui('Качество')}: {sleep.assessment.quality}</b>
                {sleep.assessment.status === 'pending' && <span className="muted"> · {ui('обновляется…')}</span>}</p>}
            <p className="muted">{sleep.assessment.summary}</p>
          </>
        ) : sleep && sleep.entries.length > 0
          ? <p className="muted">{ui('Оценка сна обновляется…')}</p>
          : <p className="muted">{ui('Запишите ночь — сон, пробуждения, пульс, HRV.')}</p>}
      </section>

      {/* перспектива: данные подключатся новыми концептами ядра */}
      <section className="tile future"><header><h3>{ui('Нагрузки')}</h3></header><p>{ui('скоро')}</p></section>
    </div>
  )
}
