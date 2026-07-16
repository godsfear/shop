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
export interface Grant { link_id: string; key_id: string }

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

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + withCare(path), { ...opts, headers: authHeaders(opts.headers) })
  if (!res.ok) {
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

// --- аутентификация ---
export async function signup(email: string, password: string, last: string,
                             sex: boolean, birthdate: string): Promise<string> {
  const body = { person: { name: { last }, sex, birthdate }, contact: { email }, password }
  const r = await req<{ access_token: string }>('/auth/signup/', json(body))
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

// --- профиль ---
export interface Me { id: string; person: string; contact: { email?: string }
                      confirmed: boolean }
export const me = () => req<Me>('/auth/user/')
// подтверждение почты кодом из письма
export const confirmEmail = (code: string) => req<Me>('/auth/confirm/', json({ code }))
export const resendConfirm = () => req<void>('/auth/confirm/resend/', { method: 'POST' })

// --- согласия (consent-first доступ) ---
export interface Consent {
  id: string; table: string; objectid: string; grantee: string
  scope: string; status: string; until: string | null; reason: string | null
  begins: string; ends: string | null
}
export const consentIncoming = () => req<Consent[]>('/consent/incoming')
export const consentMine = () => req<Consent[]>('/consent/mine')
export const consentGranted = () => req<Consent[]>('/consent/granted')
export const consentRequest = (subjectId: string, reason: string) =>
  req<Consent>('/consent/request', json({
    subject_table: 'person', subject_id: subjectId, scope: 'medical', reason }))
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

// --- симптомы/находки эпизода ---
export const episodeProperties = (id: string, category?: string) =>
  req<MedProperty[]>(`/me/episodes/${id}/properties` + (category ? `?category=${category}` : ''))
export const addEpisodeProperty = (
  id: string, p: { category?: string; code: string; name?: string; value: Record<string, unknown> },
) => req<MedProperty>(`/me/episodes/${id}/properties`, json(p))

// --- документы ---
export const listDocuments = (episodeId?: string) =>
  req<Doc[]>('/me/documents' + (episodeId ? `?episode_id=${episodeId}` : ''))
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
