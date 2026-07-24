import type { VitalValidation } from './api'
import { getLang } from './i18n'

export interface VitalInputResult {
  value?: string
  error?: string
}

// Зеркало клиентского UX серверного контракта. Сервер остаётся окончательным
// источником истины; эта функция нужна для мгновенной подсказки до запроса.
export function normalizeVitalInput(
  raw: string, rule?: VitalValidation,
): VitalInputResult {
  if (!rule) return { error: getLang() === 'ru'
    ? 'Для показателя не настроено правило ввода'
    : 'No input rule is configured for this vital' }
  const text = raw.trim()

  if (rule.kind === 'blood_pressure') {
    const match = text.match(/^(\d{2,3})\s*\/\s*(\d{2,3})$/)
    if (!match) return { error: getLang() === 'ru'
      ? `Введите верхнее/нижнее, например ${rule.example}`
      : `Enter systolic/diastolic, for example ${rule.example}` }
    const systolic = Number(match[1])
    const diastolic = Number(match[2])
    if (systolic < rule.systolic_min || systolic > rule.systolic_max ||
        diastolic < rule.diastolic_min || diastolic > rule.diastolic_max) {
      return { error: getLang() === 'ru'
        ? `Допустимо: верхнее ${rule.systolic_min}–${rule.systolic_max}, нижнее ${rule.diastolic_min}–${rule.diastolic_max}`
        : `Allowed: systolic ${rule.systolic_min}–${rule.systolic_max}, diastolic ${rule.diastolic_min}–${rule.diastolic_max}` }
    }
    if (systolic <= diastolic) return { error: getLang() === 'ru'
      ? 'Верхнее давление должно быть больше нижнего'
      : 'Systolic pressure must be greater than diastolic' }
    return { value: `${systolic}/${diastolic}` }
  }

  const pattern = rule.decimals === 0
    ? /^\d+$/
    : new RegExp(`^\\d+(?:[.,]\\d{1,${rule.decimals}})?$`)
  if (!pattern.test(text)) return { error: getLang() === 'ru'
    ? rule.decimals === 0
      ? `Введите целое число, например ${rule.example}`
      : `Введите число максимум с ${rule.decimals} цифрой после запятой, например ${rule.example}`
    : rule.decimals === 0
      ? `Enter an integer, for example ${rule.example}`
      : `Enter a number with at most ${rule.decimals} decimal place, for example ${rule.example}` }
  const number = Number(text.replace(',', '.'))
  if (number < rule.min || number > rule.max) return { error: getLang() === 'ru'
    ? `Допустимый диапазон: ${rule.min}–${rule.max}`
    : `Allowed range: ${rule.min}–${rule.max}` }
  return { value: number.toFixed(rule.decimals) }
}

export function vitalInputHint(rule?: VitalValidation): string {
  if (!rule) return ''
  if (rule.kind === 'blood_pressure') return getLang() === 'ru'
    ? `Формат ${rule.example}; верхнее ${rule.systolic_min}–${rule.systolic_max}, нижнее ${rule.diastolic_min}–${rule.diastolic_max}`
    : `Format ${rule.example}; systolic ${rule.systolic_min}–${rule.systolic_max}, diastolic ${rule.diastolic_min}–${rule.diastolic_max}`
  const format = rule.decimals === 0
    ? (getLang() === 'ru' ? 'целое число' : 'integer')
    : (getLang() === 'ru' ? `до ${rule.decimals} цифры после запятой` : `up to ${rule.decimals} decimal place`)
  return getLang() === 'ru'
    ? `Формат: ${format}; диапазон ${rule.min}–${rule.max}`
    : `Format: ${format}; range ${rule.min}–${rule.max}`
}
