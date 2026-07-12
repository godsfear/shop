// Словарь интерфейса: системные коды бэка -> русские подписи.
// Единственное место маппинга (i18n-задел): новые состояния/события/секции — сюда.
export const STATES: Record<string, string> = {
  anamnesis: 'анамнез', diagnosis: 'диагноз', treatment: 'лечение',
  remission: 'ремиссия', recovered: 'выздоровление',
  // интервью
  complaint: 'жалоба', symptom: 'симптомы', ros: 'обзор систем',
  history: 'анамнез жизни', completeness: 'полнота', summary: 'резюме',
  confirmed: 'подтверждено', emergency: 'экстренно',
}

export const EVENTS: Record<string, string> = {
  diagnose: 'Поставить диагноз', treat: 'Начать лечение', recover: 'Выздоровление',
  remit: 'Ремиссия', relapse: 'Рецидив',
}

export const KINDS: Record<string, string> = { illness: 'болезнь', injury: 'травма' }

export const SECTIONS: Record<string, string> = {
  symptom: 'симптомы', medication: 'лекарства', allergy: 'аллергии',
  chronic: 'хронические состояния', heredity: 'наследственность',
  surgery: 'операции/госпитализации', social: 'социальный анамнез',
  risk_factor: 'факторы риска', vital: 'показатели',
  blood: 'группа крови', vaccination: 'прививки',
}

export const t = (dict: Record<string, string>, code: string) => dict[code] ?? code
