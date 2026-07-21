// Тонкая обёртка над бэкенд-API (/api/v1). JWT из localStorage в Authorization.
// Псевдоним нигде не фигурирует — сервер скоупит по сессии/мосту.
import { errText } from './i18n'

const BASE = '/api/v1'

export interface Episode {
  id: string; category: string | null; code: string; name: string | null
  begins: string; ends: string | null
}
export interface MedProperty {
  id: string; category: string | null; code: string; name: string | null
  value: Record<string, unknown>; begins: string; ends: string | null
}
export interface Doc {
  id: string; category: string | null; code: string; name: string | null
  hash: string; algorithm: string; begins: string; ends: string | null
}
export interface Assess { gaps: string[]; alerts: string[] }
export interface FsmState { state: string; available: string[]; states: string[] }
export type Concepts = Record<string, string>
// patient — имя владельца карты (сервер раскрывает только по одобренному согласию)
export interface Grant { link_id: string; key_id: string; patient?: string | null }

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// Режим «Пациенты» (Слой B): пока care-контекст установлен, каждый /me-запрос
// несёт link_id/key_id — сервер резолвит чужую карту по согласию. null = моя карта.
// sessionStorage: режим переживает перезагрузку, но не закрытие вкладки.
let care: Grant | null = JSON.parse(sessionStorage.getItem('care') ?? 'null')
export const setCare = (g: Grant | null) => {
  care = g
  if (g) sessionStorage.setItem('care', JSON.stringify(g))
  else sessionStorage.removeItem('care')
}
export const getCare = () => care

function authHeaders(extra?: HeadersInit): Headers {
  const h = new Headers(extra)
  const token = localStorage.getItem('token')
  if (token) h.set('Authorization', `Bearer ${token}`)
  // бэк отвечает на языке запроса (подписи, вопросы интервью, ИИ)
  h.set('Accept-Language', localStorage.getItem('lang') ?? 'ru')
  return h
}

function withCare(path: string): string {
  if (!care || !path.startsWith('/me')) return path
  const sep = path.includes('?') ? '&' : '?'
  return `${path}${sep}link_id=${care.link_id}&key_id=${encodeURIComponent(care.key_id)}`
}

// скользящая сессия: активному пользователю бэк продлевает токен заголовком
function pickupRefresh(res: Response) {
  const fresh = res.headers.get('X-Refresh-Token')
  if (fresh) localStorage.setItem('token', fresh)
}

// сессия истекла (401 при имевшемся токене): без пугающих ошибок — тихо
// чистим состояние и уводим на экран входа. Формы логина/регистрации не
// задевает: там токена нет, их 401 — «неверный пароль», не истечение.
function authExpired(res: Response, hadToken: boolean) {
  if (res.status !== 401 || !hadToken) return
  localStorage.removeItem('token')
  sessionStorage.removeItem('care')
  if (window.location.pathname !== '/login') window.location.href = '/login'
}

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const hadToken = !!localStorage.getItem('token')
  const res = await fetch(BASE + withCare(path), { ...opts, headers: authHeaders(opts.headers) })
  pickupRefresh(res)
  if (!res.ok) {
    authExpired(res, hadToken)
    let detail: string = res.statusText
    try {
      const j = await res.json()
      detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch { /* тело не JSON */ }
    // detail — код ошибки (контракт бэка), подпись — словарь i18n
    throw new ApiError(res.status, errText(detail))
  }
  if (res.status === 204) return undefined as T
  const ct = res.headers.get('content-type') || ''
  return (ct.includes('application/json') ? await res.json() : await res.text()) as T
}

const json = (body: unknown, method = 'POST'): RequestInit => ({
  method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
})

// --- юр-документы (публичные, до авторизации): текст из БД на языке интерфейса ---
export interface LegalDoc { version: string; title: string; body: string }
export const legalDoc = (code: string) => req<LegalDoc>(`/legal/${code}`)

// --- аутентификация: регистрация двухшаговая (код на почту ДО создания учётки) ---
export const signupStart = (email: string, password: string,
                            last: string, first: string,
                            sex: boolean, birthdate: string, termsAccepted: boolean) =>
  req<void>('/auth/signup/', json(
    { person: { name: { last, first }, sex, birthdate }, contact: { email },
      password, terms_accepted: termsAccepted }))
export async function signupConfirm(email: string, code: string): Promise<string> {
  const r = await req<{ access_token: string }>('/auth/signup/confirm/', json({ email, code }))
  return r.access_token
}
export async function signin(email: string, password: string): Promise<string> {
  const form = new URLSearchParams({ username: email, password })
  const r = await req<{ access_token: string }>('/auth/signin/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form,
  })
  return r.access_token
}

// --- восстановление пароля по коду на почту (ответ на шаг 1 всегда 204) ---
export const requestReset = (email: string) => req<void>('/auth/reset/', json({ email }))
export const confirmReset = (email: string, code: string, password: string) =>
  req<void>('/auth/reset/confirm/', json({ email, code, password }))

// роли из JWT (только для показа/скрытия UI — доступ enforce'ит бэк)
export function tokenRoles(): string[] {
  const token = localStorage.getItem('token')
  if (!token) return []
  try { return JSON.parse(atob(token.split('.')[1])).roles ?? [] } catch { return [] }
}
export const isAdmin = () => tokenRoles().includes('admin')

// --- админ: статистика «сколько в базе чего» ---
export const adminStats = () => req<Record<string, number>>('/admin/stats')

// --- профиль ---
export interface Me { id: string; person: string; contact: { email?: string }
                      confirmed: boolean }
export const me = () => req<Me>('/auth/user/')

// --- согласия (consent-first доступ) ---
export interface Consent {
  id: string; table: string; objectid: string; grantee: string
  scope: string; status: string; until: string | null; reason: string | null
  begins: string; ends: string | null
}
export const consentIncoming = () => req<Consent[]>('/consent/incoming')
export const consentMine = () => req<Consent[]>('/consent/mine')
export const consentGranted = () => req<Consent[]>('/consent/granted')
// reason — необязательное дополнение (должность/клиника): имя запрашивающего
// сервер подставляет сам из профиля (анти-спуфинг)
export const consentRequest = (subjectId: string, reason?: string) =>
  req<Consent>('/consent/request', json({
    subject_table: 'person', subject_id: subjectId, scope: 'medical',
    reason: reason || null }))
export const consentApprove = (id: string, until: string | null) =>
  req<Consent>(`/consent/${id}/approve`, json({ until }))
export const consentDeny = (id: string) => req<Consent>(`/consent/${id}/deny`, json({}))
export const consentRevoke = (id: string) => req<Consent>(`/consent/${id}/revoke`, json({}))

// --- онбординг/сессия (owner: без тела, сервер сам разворачивает мост по JWT) ---
export const enroll = () => req<void>('/me/enroll', { method: 'POST' })
export const openSession = () => req<{ expires_in: number }>('/me/session', { method: 'POST' })
export const concepts = () => req<Concepts>('/me/concepts')
// чужие карты, доступные мне по согласиям (режим «Пациенты», Слой B)
export const listGrants = () => req<Grant[]>('/me/grants')
// журнал доступов к моей карте (append-only аудит ключей)
export interface AccessLogEntry { at: string; event: string; who: string }
export const accessLog = () => req<AccessLogEntry[]>('/me/access-log')

// --- эпизоды ---
export interface StateLog { state: string; event: string | null; begins: string; ends: string | null }
export const listEpisodes = () => req<Episode[]>('/me/episodes')
export const getEpisode = (id: string) => req<Episode>(`/me/episodes/${id}`)
export const createEpisode = (category: string, code: string, name: string) =>
  req<Episode>('/me/episodes', json({ category, code, name }))
// название появляется после диагноза — при создании эпизода его ещё нет
export const renameEpisode = (id: string, name: string) =>
  req<Episode>(`/me/episodes/${id}`, json({ name }, 'PATCH'))
export const episodeHistory = (id: string) => req<StateLog[]>(`/me/episodes/${id}/history`)
export const episodeState = (id: string) => req<FsmState>(`/me/episodes/${id}/state`)
export const transition = (id: string, event: string) =>
  req<FsmState>(`/me/episodes/${id}/transition`, json({ event }))
export const assess = (id: string) => req<Assess>(`/me/episodes/${id}/assess`)

// --- профиль здоровья: правка/закрытие/история записи на псевдониме ---
export const listProperties = (category?: string) =>
  req<MedProperty[]>('/me/properties' + (category ? `?category=${category}` : ''))
export const addProperty = (p: { category?: string; code: string; name?: string;
                                 value: Record<string, unknown> }) =>
  req<MedProperty>('/me/properties', json(p))
export const updateProperty = (id: string, value: Record<string, unknown>) =>
  req<MedProperty>(`/me/properties/${id}`, json(value, 'PATCH'))
export const closeProperty = (id: string) =>
  req<MedProperty>(`/me/properties/${id}`, { method: 'DELETE' })
export const propertyHistory = (id: string) =>
  req<MedProperty[]>(`/me/properties/${id}/history`)

// --- сон: журнал ночей + оценка ИИ за период (ставится при записи) ---
export interface SleepAssessment { quality?: string; summary?: string; status?: string; nights?: number }
export interface SleepJournal { entries: MedProperty[]; assessment: SleepAssessment | null }
export const getSleep = () => req<SleepJournal>('/me/sleep')
export const addSleep = (day: string, value: Record<string, unknown>) =>
  req<MedProperty>('/me/sleep', json({ day, value }))

// --- ИИ-оценка эпизода (результат — Property code='ddx' на эпизоде) ---
export const evaluateEpisode = (id: string) =>
  req<{ queued: boolean }>(`/me/episodes/${id}/evaluate`, { method: 'POST' })

// --- интервью (сбор анамнеза): сервер ведёт опрос, фронт рендерит вопросы ---
export interface InterviewQuestion {
  ask?: string; field?: string
  symptom?: string; slot?: string; system?: string; section?: string; gaps?: string[]
  known?: string[]   // что уже в карте (секции анамнеза — подтверждение актуальности)
}
export interface InterviewSummary {
  chief_complaint: string | null
  symptoms: Record<string, Record<string, unknown>>
  negatives: string[]
  ros: Record<string, 'clear' | string[]>
}
export interface InterviewView {
  state: string; queue: string[]; done: string[]
  question?: InterviewQuestion
  summary?: InterviewSummary
  alerts?: string[]
}
export const interviewOpen = (id: string) =>
  req<InterviewView>(`/me/episodes/${id}/interview`, { method: 'POST' })
export const interviewState = (id: string) =>
  req<InterviewView>(`/me/episodes/${id}/interview`)
export const interviewAnswer = (id: string, body: Record<string, unknown>) =>
  req<InterviewView>(`/me/episodes/${id}/interview/answer`, json(body))

// --- справочники концептов (reference): чипы выбора ---
// scopes (только vital): где уместен показатель — profile и/или diary
export interface DictItem { code: string; name: string; scopes?: string[] }
export const dictionary = (concept: string) => req<DictItem[]>(`/me/dictionary/${concept}`)

// подписи доменных кодов (единый источник — БД), см. ui.ts/loadMeta
export type Meta = Record<'concepts' | 'kinds' | 'states' | 'events' | 'red_flags' | 'slots',
  Record<string, string>>
export const meta = () => req<Meta>('/me/meta')

// комментарии эпизода = свойства эпизода (concept=note); удаление — эпизод-скоуп
export const closeEpisodeProperty = (episodeId: string, propId: string) =>
  req<MedProperty>(`/me/episodes/${episodeId}/properties/${propId}`, { method: 'DELETE' })

// правка ответа анамнеза (опечатки) — только до постановки диагноза
export const editAnamnesis = (id: string, symptom: string, slot: string,
                              value: string | number) =>
  req<void>(`/me/episodes/${id}/anamnesis`, json({ symptom, slot, value }, 'PATCH'))

// --- диагноз и лечение ---
export const setDiagnosis = (id: string, text: string, source = 'manual') =>
  req<void>(`/me/episodes/${id}/diagnosis`, json({ text, source }))
export const startTreatment = (id: string, items: { code?: string; name: string }[]) =>
  req<void>(`/me/episodes/${id}/treatment`, json({ items }))

// --- симптомы/находки эпизода ---
export const episodeProperties = (id: string, category?: string) =>
  req<MedProperty[]>(`/me/episodes/${id}/properties` + (category ? `?category=${category}` : ''))
export const addEpisodeProperty = (
  id: string, p: { category?: string; code: string; name?: string; value: Record<string, unknown> },
) => req<MedProperty>(`/me/episodes/${id}/properties`, json(p))

// --- питание: приёмы пищи (оценка ИИ) и суточная норма ---
export interface MealItem { name: string; kcal: number; protein: number; fat: number; carbs: number }
export interface MealValue {
  desc?: string; day?: string; status?: string
  items?: MealItem[]; totals?: Record<string, number>; note?: string
}
export interface NutritionNorm {
  kcal?: number; protein_g?: number; fat_g?: number; carbs_g?: number
  note?: string; date?: string; status?: string
}
export interface Nutrition {
  day: string; norm: NutritionNorm | null
  meals: MedProperty[]; totals: Record<string, number>
}
export const getNutrition = (day: string) => req<Nutrition>(`/me/nutrition?day=${day}`)
export async function addMeal(day: string, desc: string, photo?: File | null): Promise<MedProperty> {
  const fd = new FormData()
  fd.append('day', day)
  fd.append('desc', desc)
  if (photo) fd.append('file', photo)
  return req<MedProperty>('/me/meals', { method: 'POST', body: fd })
}

// --- документы ---
export const listDocuments = (episodeId?: string) =>
  req<Doc[]>('/me/documents' + (episodeId ? `?episode_id=${episodeId}` : ''))
// содержимое документа (направление/рецепт/анализ) — blob для просмотра и печати;
// идёт с Authorization, поэтому просто <a href> не подойдёт
export async function documentContent(id: string): Promise<Blob> {
  const hadToken = !!localStorage.getItem('token')
  const res = await fetch(BASE + withCare(`/me/documents/${id}/content`),
                          { headers: authHeaders() })
  pickupRefresh(res)
  if (!res.ok) {
    authExpired(res, hadToken)
    throw new ApiError(res.status, errText(res.statusText))
  }
  return res.blob()
}
export async function uploadDocument(file: File, name: string, code: string,
                                     category?: string, episodeId?: string): Promise<Doc> {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('name', name)
  fd.append('code', code)
  if (category) fd.append('category', category)
  const q = episodeId ? `?episode_id=${episodeId}` : ''
  return req<Doc>('/me/documents' + q, { method: 'POST', body: fd })
}
