// Подписи доменных кодов приходят из GET /me/meta — единый источник истины
// это сид/БД (Category.name + метки в value.fsm). Здесь только кэш и t():
// доменных текстов во фронте нет; правка подписи в сиде видна без правки кода.
import { meta } from './api'

export const STATES: Record<string, string> = {}
export const EVENTS: Record<string, string> = {}
export const KINDS: Record<string, string> = {}     // концепты-эпизоды: болезнь/травма
export const SECTIONS: Record<string, string> = {}  // все концепты: секции анамнеза/карты
export const RED_FLAGS: Record<string, string> = {}
export const SLOTS: Record<string, string> = {}     // слоты анамнеза: onset -> «начало»

let loading: Promise<void> | null = null
// однократная загрузка (Shell ждёт её до рендера страниц); при ошибке
// t() отдаёт код как есть — интерфейс живёт, просто без подписей
export const loadMeta = () => loading ??= meta().then((m) => {
  Object.assign(STATES, m.states)
  Object.assign(EVENTS, m.events)
  Object.assign(KINDS, m.kinds)
  Object.assign(SECTIONS, m.concepts)
  Object.assign(RED_FLAGS, m.red_flags)
  Object.assign(SLOTS, m.slots)
}).catch(() => { loading = null })

export const t = (dict: Record<string, string>, code: string) => dict[code] ?? code

// единицы показателей (vital) — «Моя карта» и дневник симптомов эпизода;
// подпись локализуется через ui() в момент записи
export const UNITS: Record<string, string> = {
  height: 'см', weight: 'кг', blood_pressure: 'мм рт. ст.', pulse: 'уд/мин',
  temperature: '°C',
}
