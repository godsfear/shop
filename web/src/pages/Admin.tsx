import { useEffect, useState } from 'react'
import { adminStats } from '../api'
import { ui } from '../i18n'

// счётчики по смысловым группам; ключ из /admin/stats -> человекочитаемо
const GROUPS: { title: string; rows: [string, string][] }[] = [
  { title: 'Люди и учётки', rows: [
    ['users', 'Пользователи'],
    ['users_confirmed', '— подтвердили почту'],
    ['persons', 'Персоны'],
  ] },
  { title: 'Псевдонимы', rows: [
    ['pseudonyms_issued', 'Выдано (используются)'],
    ['pseudonyms_pool_free', 'Свободный пул (создаются заранее)'],
  ] },
  { title: 'Медицинские данные', rows: [
    ['episodes', 'Эпизоды (болезни и травмы)'],
    ['medical_facts', 'Мед. факты (симптомы, показатели, сон, питание…)'],
    ['documents', 'Документы'],
    ['consents', 'Согласия на доступ'],
    ['keys', 'Ключи шифрования'],
  ] },
  { title: 'Справочник (системное)', rows: [
    ['dictionary_items', 'Элементы справочников'],
    ['translations', 'Переводы справочников'],
  ] },
]

// Админ-статистика: read-only «сколько в базе чего». Доступ гейтит бэк
// (require_admin) — не-админу роутер покажет страницу, но данные вернут 403.
export default function Admin() {
  const [stats, setStats] = useState<Record<string, number> | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    adminStats().then(setStats).catch((e) => setErr((e as Error).message))
  }, [])

  return (
    <div className="page">
      <h2>{ui('Статистика базы')}</h2>
      {err && <p className="error">{err}</p>}
      {stats && GROUPS.map((g) => (
        <section className="tile" key={g.title}>
          <h3>{ui(g.title)}</h3>
          <table className="stats">
            <tbody>
              {g.rows.map(([key, label]) => (
                <tr key={key}>
                  <td>{ui(label)}</td>
                  <td className="num">{(stats[key] ?? 0).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  )
}
