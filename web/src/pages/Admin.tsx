import { useEffect, useState } from 'react'
import { adminStats } from '../api'
import { ui } from '../i18n'

// подписи счётчиков (ключ из /admin/stats -> человекочитаемо через ui())
const LABELS: Record<string, string> = {
  users: 'Пользователи',
  users_confirmed: '— из них подтвердили почту',
  persons: 'Персоны',
  pseudonyms: 'Псевдонимы (выданы)',
  pseudonym_pool_free: 'Псевдонимы (свободный пул)',
  properties: 'Медицинские записи',
  documents: 'Документы',
  blobs: 'Файлы (блобы)',
  consents: 'Согласия на доступ',
  keys: 'Ключи шифрования',
  entities: 'Справочные сущности',
  translations: 'Переводы',
}

// Админ-статистика: read-only «сколько в базе чего». Доступ гейтит бэк
// (require_admin) — не-админа сюда пустит роутер, но данные вернут 403.
export default function Admin() {
  const [stats, setStats] = useState<Record<string, number> | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    adminStats().then(setStats).catch((e) => setErr((e as Error).message))
  }, [])

  return (
    <section className="tile">
      <h2>{ui('Статистика базы')}</h2>
      {err && <p className="error">{err}</p>}
      {stats && (
        <table className="stats">
          <tbody>
            {Object.entries(stats).map(([k, v]) => (
              <tr key={k}>
                <td>{ui(LABELS[k] ?? k)}</td>
                <td className="num">{v.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
