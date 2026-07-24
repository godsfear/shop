import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  listEpisodes, createEpisode, episodeState, concepts, getDiary, getNutrition, getSleep,
  type Episode, type Concepts, type MedProperty, type Nutrition, type SleepJournal,
} from '../api'
import { MacroBar, localDay } from './Nutrition'
import { KINDS, STATES, t } from '../ui'
import { ui } from '../i18n'

// available пуст -> маршрут завершён: эпизод уходит в «Историю болезни»
interface EpisodeRow extends Episode { fsm?: string; closed?: boolean }
type OptionalTile = 'nutrition' | 'sleep' | 'activity'
type TileVisibility = Record<OptionalTile, boolean>

const TILE_VISIBILITY_KEY = 'dashboard-optional-tiles'
const tileVisibility = (): TileVisibility => {
  try {
    const saved = JSON.parse(localStorage.getItem(TILE_VISIBILITY_KEY) ?? '{}')
    return {
      nutrition: saved.nutrition !== false,
      sleep: saved.sleep !== false,
      activity: saved.activity !== false,
    }
  } catch { return { nutrition: true, sleep: true, activity: true } }
}

function DiaryLabel({ entry }: { entry: MedProperty }) {
  const p = entry
  const v = p.value as { value?: unknown; unit?: unknown; text?: string }
  if (v.text !== undefined) return <>{String(v.text)}</>
  return (
    <>
      <b className="diary-parameter-name">{p.name || p.code}</b>
      <span className="diary-parameter-value">
        {String(v.value ?? '')} {String(v.unit ?? '')}
      </span>
    </>
  )
}

function isToday(value: string) {
  const date = new Date(value)
  const today = new Date()
  return date.getFullYear() === today.getFullYear()
    && date.getMonth() === today.getMonth()
    && date.getDate() === today.getDate()
}

function EpisodeLink({ ep }: { ep: EpisodeRow }) {
  return (
    <Link to={`/episode/${ep.id}`} className="row-link episode-link">
      <span>{ep.name || ep.code}</span>
      {ep.fsm && <span className="chip state">{t(STATES, ep.fsm)}</span>}
      <span className="muted">{new Date(ep.begins).toLocaleDateString()}</span>
    </Link>
  )
}

// Дашборд «Сегодня»: эпизоды и общий дневник всегда под рукой; дополнительные
// плашки пользователь может скрыть без потери самих данных.
export default function Dashboard() {
  const nav = useNavigate()
  const [eps, setEps] = useState<EpisodeRow[]>([])
  const [cs, setCs] = useState<Concepts>({})
  const [err, setErr] = useState('')
  const [creating, setCreating] = useState(false)
  const [nutri, setNutri] = useState<Nutrition | null>(null)
  const [sleep, setSleep] = useState<SleepJournal | null>(null)
  const [diary, setDiary] = useState<MedProperty[]>([])
  const [visibleTiles, setVisibleTiles] = useState<TileVisibility>(tileVisibility)

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
    getDiary().then(setDiary).catch(() => {})
  }, [])

  const setTileVisibility = (tile: OptionalTile, visible: boolean) => {
    const next = { ...visibleTiles, [tile]: visible }
    setVisibleTiles(next)
    localStorage.setItem(TILE_VISIBILITY_KEY, JSON.stringify(next))
  }

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
  const todayDiary = diary.filter((p) => isToday(p.begins))
  const dashboardDiary = todayDiary.length > 0 ? todayDiary : diary.slice(0, 2)

  return (
    <div>
      <details className="dashboard-settings">
        <summary>{ui('Настроить плашки')}</summary>
        <div className="inline">
          <label><input type="checkbox" checked={visibleTiles.nutrition}
                        onChange={(e) => setTileVisibility('nutrition', e.target.checked)} /> {ui('Питание')}</label>
          <label><input type="checkbox" checked={visibleTiles.sleep}
                        onChange={(e) => setTileVisibility('sleep', e.target.checked)} /> {ui('Сон')}</label>
          <label><input type="checkbox" checked={visibleTiles.activity}
                        onChange={(e) => setTileVisibility('activity', e.target.checked)} /> {ui('Нагрузки')}</label>
        </div>
      </details>

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

      <section className="tile">
        <header><h3>{ui('Дневник состояния')}</h3>
          <Link to="/diary"><button className="ghost">{ui('Открыть')}</button></Link>
        </header>
        {diary.length === 0 ? <p className="muted">{ui('пока пусто')}</p> : (
          <ul className="rows dashboard-diary-rows">
            {dashboardDiary.map((p) => (
              <li key={p.id} className="row-link">
                <span className="dashboard-diary-label"><DiaryLabel entry={p} /></span>
                <span className="muted dashboard-diary-time">{todayDiary.length > 0
                  ? new Date(p.begins).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                  : new Date(p.begins).toLocaleDateString()}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* питание: сегодняшние ккал против нормы ИИ; вся лента — на /nutrition */}
      {visibleTiles.nutrition && <section className="tile">
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
      </section>}

      {visibleTiles.sleep && <section className="tile">
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
      </section>}

      {/* перспектива: данные подключатся новыми концептами ядра */}
      {visibleTiles.activity &&
        <section className="tile future"><header><h3>{ui('Нагрузки')}</h3></header><p>{ui('скоро')}</p></section>}
      </div>
    </div>
  )
}
