"""Тексты юридических документов — сид.

Хранятся в БД как Entity под top-level категорией 'legal' (не медицинский
концепт — не попадает в /me/concepts). Заголовок — Entity.name, тело —
Entity.description (RU-база); английские версии — в Translation (поля name/
description), i18n и фолбэк как везде. Единый источник: текст в одном месте.

Версия действующей редакции — settings.terms_version; при правке текста
поднимать её (на учётке фиксируется, на какую редакцию согласился пользователь).
"""

_AGREEMENT_RU = """\
1. О сервисе. «Медкарта» — личная медицинская карта. Проект некоммерческий: \
пользование бесплатное, ваши данные не продаются, не передаются рекламодателям \
и не используются ни для чего, кроме работы самого сервиса.

2. Какие данные. При регистрации — имя, адрес электронной почты, пол, дата \
рождения. При использовании — сведения о здоровье, которые вы вносите сами: \
жалобы, документы, показатели, питание.

3. Как они разделены. Медицинские сведения хранятся отвязанными от вашей \
личности (псевдонимизация): данные, доступные без ваших ключей, не связаны с \
вашим именем. Сведения, идентифицирующие вас, хранятся отдельно.

4. Кто имеет доступ. По умолчанию — только вы. Другой человек (например, врач \
или близкий) получает доступ к вашей карте исключительно после вашего явного \
согласия и только на указанный вами срок. Согласие можно отозвать в любой \
момент — доступ сразу прекращается. Каждое обращение к карте фиксируется в \
журнале доступа.

5. Обработка искусственным интеллектом. Для подсказок (оценка возможных \
состояний, рекомендации анализов и назначений, подсчёт калорий) внесённые вами \
сведения о здоровье, а также загруженные документы и фотографии передаются во \
внешний сервис ИИ (Google Gemini). Ваши имя и контакты туда не передаются. \
Передача происходит только по вашему действию (например, по кнопке «Диагноз») \
или для расчёта нормы питания.

6. Это не заменяет врача. Сервис и оценки ИИ носят справочный характер, не \
являются медицинским диагнозом и не заменяют консультацию врача.

7. Ваши права. Вы можете в любой момент посмотреть свои данные, отозвать \
выданные согласия и удалить учётную запись вместе с данными.

8. Изменение условий. Условия могут обновляться; при существенных изменениях \
согласие запросим заново. Действующая редакция всегда доступна в приложении.

Регистрируясь, вы подтверждаете, что ознакомились с условиями и даёте согласие \
на обработку своих персональных данных, включая сведения о здоровье, на \
условиях выше."""

_AGREEMENT_EN = """\
1. About the service. Medcard is a personal health record. The project is \
non-commercial: it is free to use, your data is not sold, is not shared with \
advertisers, and is not used for anything other than running the service itself.

2. What data. At registration — your name, email address, sex, and date of \
birth. During use — the health information you enter yourself: complaints, \
documents, measurements, nutrition.

3. How it is separated. Medical information is stored detached from your \
identity (pseudonymization): data accessible without your keys is not linked to \
your name. Information that identifies you is stored separately.

4. Who has access. By default — only you. Another person (for example, a doctor \
or a relative) gets access to your record only after your explicit consent and \
only for the period you specify. Consent can be withdrawn at any time — access \
stops immediately. Every access to the record is written to an access log.

5. Processing by artificial intelligence. For suggestions (assessment of \
possible conditions, recommended tests and prescriptions, calorie counting) the \
health information you enter, as well as uploaded documents and photos, is sent \
to an external AI service (Google Gemini). Your name and contacts are not sent \
there. The transfer happens only by your action (for example, the “Diagnosis” \
button) or to calculate your nutrition target.

6. This does not replace a doctor. The service and AI assessments are for \
reference only, are not a medical diagnosis, and do not replace a doctor’s \
consultation.

7. Your rights. At any time you can view your data, withdraw the consents you \
have granted, and delete your account together with your data.

8. Changes to the terms. The terms may be updated; for significant changes we \
will ask for consent again. The current version is always available in the app.

By registering, you confirm that you have read the terms and give your consent \
to the processing of your personal data, including health information, on the \
terms above."""

# code -> {title_ru, title_en, body_ru, body_en}
LEGAL_DOCS = {
    "agreement": {
        "title_ru": "Пользовательское соглашение и согласие на обработку данных",
        "title_en": "Terms of Use and Consent to Data Processing",
        "body_ru": _AGREEMENT_RU,
        "body_en": _AGREEMENT_EN,
    },
}
