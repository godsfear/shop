// Тонкая обёртка над бэкенд-API (/api/v1). JWT из localStorage в Authorization.
// Псевдоним нигде не фигурирует — сервер скоупит по сессии/мосту.
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
let care: Grant | null = null
export const setCare = (g: Grant | null) => { care = g }
export const getCare = () => care

function authHeaders(extra?: HeadersInit): Headers {
  const h = new Headers(extra)
  const token = localStorage.getItem('token')
  if (token) h.set('Authorization', `Bearer ${token}`)
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
    throw new ApiError(res.status, detail)
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

// --- онбординг/сессия (owner: без тела, сервер сам разворачивает мост по JWT) ---
export const enroll = () => req<void>('/me/enroll', { method: 'POST' })
export const openSession = () => req<{ expires_in: number }>('/me/session', { method: 'POST' })
export const concepts = () => req<Concepts>('/me/concepts')
// чужие карты, доступные мне по согласиям (режим «Пациенты», Слой B)
export const listGrants = () => req<Grant[]>('/me/grants')

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
