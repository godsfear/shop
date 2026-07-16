// Словарь хрома интерфейса (кнопки, заголовки, подсказки). Доменные подписи
// (концепты, состояния, справочники) сюда НЕ входят — они приходят из БД
// через /me/meta и /me/dictionary на языке Accept-Language (см. ui.ts).
//
// Ключ — русская строка как есть в коде: читаемо, ru не требует словаря,
// недостающий перевод виден сразу (показывается русский). Новый язык =
// ещё одна колонка-словарь и пункт в LANGS.
export type Lang = 'ru' | 'en'
export const LANGS: Lang[] = ['ru', 'en']

export const getLang = (): Lang =>
  (localStorage.getItem('lang') as Lang) === 'en' ? 'en' : 'ru'

// смена языка перезагружает страницу: все данные (meta, словари, вопросы
// интервью) перезапрашиваются с новым Accept-Language — проще и надёжнее,
// чем инвалидировать кэши точечно
export const setLang = (l: Lang) => {
  localStorage.setItem('lang', l)
  window.location.reload()
}

const EN: Record<string, string> = {
  // общее
  'Медкарта': 'Health Record',
  'Отмена': 'Cancel',
  'Сохранить': 'Save',
  'Ответить': 'Answer',
  'название': 'title',
  'свой вариант': 'your own option',
  // вход/регистрация
  'Вход': 'Sign in',
  'Войти': 'Sign in',
  'пароль': 'password',
  'Нет аккаунта?': 'No account?',
  'Регистрация': 'Sign up',
  'пароль (≥8 символов)': 'password (≥8 characters)',
  'фамилия': 'last name',
  'Пол': 'Sex',
  'муж': 'male',
  'жен': 'female',
  'Дата рождения': 'Date of birth',
  'Создать аккаунт': 'Create account',
  'Уже есть аккаунт?': 'Already have an account?',
  // каркас (Shell)
  'здоровье': 'health',
  'Сегодня': 'Today',
  'Моя карта': 'My record',
  'Доступы': 'Access',
  'Доверили мне': 'Shared with me',
  'Выйти': 'Log out',
  'Подтвердите почту — код в письме.': 'Confirm your email — the code is in the message.',
  'код из письма': 'code from the email',
  'Подтвердить': 'Confirm',
  'Выслать снова': 'Resend',
  'код отправлен повторно': 'code sent again',
  'Карта пациента': 'Patient record',
  '— доступ по согласию': '— access by consent',
  'Выйти из карты': 'Leave record',
  'открываю сессию…': 'opening session…',
  'не удалось открыть карту:': 'failed to open the record:',
  'нет связи с сервером:': 'no connection to the server:',
  // дашборд
  'Эпизоды': 'Episodes',
  '+ Новый': '+ New',
  'Что случилось?': 'What happened?',
  'Сейчас ничего не беспокоит. Заболели или травма — откройте эпизод.':
    'Nothing bothers you right now. Got sick or injured — open an episode.',
  'История болезни': 'Past episodes',
  'Документы': 'Documents',
  'Анализы и выписки — на странице эпизода.': 'Test results and reports live on the episode page.',
  'Сон': 'Sleep',
  'Нагрузки': 'Activity',
  'Питание': 'Nutrition',
  'скоро': 'soon',
  'от': 'from',
  'Справочник пуст — на сервере не прогнан медицинский сид':
    'Dictionary is empty — the medical seed has not been run on the server',
  // эпизод
  'диагноз / название': 'diagnosis / title',
  'Эпизод': 'Episode',
  'переименовать': 'rename',
  '← сегодня': '← today',
  'Пройти опрос (анамнез)': 'Take the interview (anamnesis)',
  'интервью': 'interview',
  'маршрут завершён': 'journey complete',
  'Журнал': 'Log',
  'Стоит дополнить': 'Worth completing',
  'Признак возможного угрожающего состояния': 'Sign of a possibly life-threatening condition',
  '— не откладывайте обращение за помощью.': '— do not delay seeking medical help.',
  'Рассказ пока неполон:': 'The story is still incomplete:',
  'Быстрее всего — пройти опрос.': 'The fastest way is the interview.',
  'Рекомендованные анализы': 'Recommended tests',
  'ИИ предлагает сдать для уточнения. Загрузите результаты ниже — они войдут в диагноз.':
    'The AI suggests these to clarify the picture. Upload the results below — they will feed the diagnosis.',
  'ИИ подбирает анализы по анамнезу…': 'The AI is selecting tests from your history…',
  'Диагноз (оценка ИИ)': 'Diagnosis (AI assessment)',
  'ИИ анализирует…': 'AI is analyzing…',
  'Пересчитать диагноз': 'Reassess diagnosis',
  'Диагноз': 'Diagnosis',
  'станет доступно после сбора анамнеза — пройдите опрос':
    'available after the history is taken — do the interview',
  'анамнез и оригиналы загруженных документов уйдут ИИ одной задачей':
    'the history and original documents go to the AI as one task',
  'Рекомендованные анализы ещё не загружены — оценка будет менее точной.':
    'Recommended test results are not uploaded yet — the assessment will be less accurate.',
  '⚠ Данные указывают на возможное угрожающее состояние — не откладывайте обращение за помощью.':
    '⚠ The data points to a possibly life-threatening condition — do not delay seeking help.',
  'Предварительная оценка ИИ — не диагноз и не заменяет осмотр врача. Обсудите результат со специалистом.':
    'A preliminary AI assessment — not a diagnosis and no substitute for a doctor. Discuss the result with a specialist.',
  'Жалобы': 'Complaints',
  '— отсутствует (значимо)': '— absent (significant)',
  'Результаты анализов и обследований. Читаются ИИ при нажатии «Диагноз» (оригиналы), не разбираются при загрузке.':
    'Test and exam results. Read by the AI when you press “Diagnosis” (originals); not parsed on upload.',
  'Загрузить': 'Upload',
  'ИИ': 'AI',
  // интервью
  'Что беспокоит больше всего? Это станет главной жалобой.':
    'What bothers you most? This becomes the chief complaint.',
  'Обзор систем': 'Review of systems',
  'есть ли жалобы?': 'any complaints?',
  'Анамнез жизни': 'Life history',
  'что отметить?': 'anything to note?',
  'Остались пробелы:': 'Gaps remain:',
  'Заполним?': 'Fill them in?',
  'Резюме собрано. Всё ли верно и полно?': 'Summary is ready. Is everything correct and complete?',
  'Признаки угрожающего состояния — опрос прерван.':
    'Signs of a life-threatening condition — the interview is paused.',
  'Анамнез собран и подтверждён. Спасибо!': 'History taken and confirmed. Thank you!',
  '← к эпизоду': '← to the episode',
  'Красный флаг:': 'Red flag:',
  'Опрос прерван — при угрозе жизни звоните': 'Interview paused — if life is at risk call',
  'Это главная жалоба': 'This is the chief complaint',
  'Отметьте, что появилось одновременно — каждый уйдёт в разбор.':
    'Mark what appeared at the same time — each will be examined.',
  'ничего': 'nothing',
  'Ничего сопутствующего': 'Nothing associated',
  'ответ свободным текстом': 'answer in free text',
  'всё в порядке': 'all clear',
  'Всё в порядке': 'All clear',
  'Есть жалобы': 'There are complaints',
  'В карте:': 'On record:',
  'всё актуально': 'all up to date',
  'Актуально': 'Up to date',
  'Дополнить…': 'Add more…',
  'добавить свободной строкой': 'add as free text',
  'Готово': 'Done',
  'Ничего нет': 'Nothing',
  'ничего нет': 'nothing',
  'Главная жалоба:': 'Chief complaint:',
  'Симптомы:': 'Symptoms:',
  'Отрицания:': 'Negatives:',
  'Обзор систем:': 'Review of systems:',
  'без жалоб': 'no complaints',
  'всё верно': 'all correct',
  'Всё верно': 'All correct',
  'Да, ещё…': 'Yes, more…',
  'Добавить в разбор': 'Add for examination',
  'помощь оказана — продолжаем': 'help received — continuing',
  'Продолжить опрос': 'Resume the interview',
  'К эпизоду': 'To the episode',
  // доступы (владелец)
  'Доступ к моей карте': 'Access to my record',
  'Код доступа': 'Access code',
  'Сообщите его доверенному лицу (например, врачу) — оно запросит доступ, а решение всегда за вами. Код не раскрывает данные и не является псевдонимом — медзаписи им не адресуются.':
    'Give it to a trusted person (e.g. your doctor) — they request access, the decision is always yours. The code reveals no data and is not a pseudonym — medical records are not addressed by it.',
  'Скопирован': 'Copied',
  'Скопировать': 'Copy',
  'Входящие запросы': 'Incoming requests',
  'Новых запросов нет.': 'No new requests.',
  'без представления': 'no introduction',
  'разрешить на:': 'allow for:',
  'месяц': 'a month',
  'год': 'a year',
  'бессрочно': 'indefinitely',
  'Отказать': 'Deny',
  'Журнал доступов': 'Access log',
  'Каждый разворот доступа к карте пишется в защищённый от подделки журнал (включая отказы и экстренные доступы). Повторные обращения в пределах ~5 минут не дублируются.':
    'Every unwrap of access to the record is written to a tamper-evident log (including denials and emergency access). Repeats within ~5 minutes are not duplicated.',
  'записей пока нет': 'no entries yet',
  'просмотр карты': 'record viewed',
  'отказ в доступе': 'access denied',
  'ЭКСТРЕННЫЙ доступ': 'EMERGENCY access',
  'Кто видит карту': 'Who can see the record',
  'Доступов нет — карту видите только вы.': 'No grants — only you can see the record.',
  'доступ': 'access',
  'до': 'until',
  'Отозвать': 'Revoke',
  // пациенты (специалист)
  'Запросить доступ': 'Request access',
  'Владелец карты сообщает вам код доступа со страницы «Доступы» и сам одобряет запрос — и может отозвать его в любой момент.':
    'The record owner gives you the access code from their “Access” page and approves the request — and can revoke it at any time.',
  'код доступа владельца': "owner's access code",
  'представьтесь (видно пациенту)': 'introduce yourself (visible to the patient)',
  'Запросить': 'Request',
  'запрос доступа': 'access request',
  'Запрос отправлен — ждёт решения пациента.': "Request sent — awaiting the patient's decision.",
  'Мои запросы': 'My requests',
  'запрос': 'request',
  'ожидает решения': 'awaiting decision',
  'одобрено': 'approved',
  'отказано': 'denied',
  'отозвано': 'revoked',
  'истекло': 'expired',
  'Доступные карты': 'Available records',
  'Одобренных доступов пока нет.': 'No approved grants yet.',
  'Открыть карту': 'Open record',
  // моя карта
  'Постоянные данные о здоровье. Врач увидит их по вашему согласию; опрос при новом эпизоде лишь попросит подтвердить актуальность.':
    'Permanent health data. A doctor sees it with your consent; a new episode interview only asks you to confirm it is up to date.',
  'пока пусто': 'empty so far',
  'скрыть': 'hide',
  'история': 'history',
  'закрыть': 'close',
  '— из справочника —': '— from the dictionary —',
  'значение': 'value',
  'Записать': 'Record',
  'Добавить': 'Add',
  'см': 'cm',
  'кг': 'kg',
  'мм рт. ст.': 'mmHg',
  'уд/мин': 'bpm',
}

// Перевод строки хрома: ru — как есть, иначе словарь (фолбэк — русский ключ,
// чтобы недостающий перевод был виден, а не падал)
export const ui = (s: string): string => (getLang() === 'ru' ? s : (EN[s] ?? s))
