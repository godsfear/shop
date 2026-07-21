import { useState, type InputHTMLAttributes } from 'react'
import { ui } from './i18n'

const EYE = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z" /><circle cx="12" cy="12" r="3" />
  </svg>
)
const EYE_OFF = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-11-8-11-8a18.5 18.5 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
    <line x1="1" y1="1" x2="23" y2="23" />
  </svg>
)

// Поле пароля с «глазком»: показать введённое, чтобы проверить перед отправкой.
// Принимает те же props, что <input> (кроме type — им управляет сам компонент).
export function PasswordField(props: Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>) {
  const [show, setShow] = useState(false)
  const hint = ui(show ? 'Скрыть пароль' : 'Показать пароль')
  return (
    <div className="pw-field">
      <input {...props} type={show ? 'text' : 'password'} />
      <button type="button" className="pw-eye" tabIndex={-1} aria-label={hint} title={hint}
              onClick={() => setShow((s) => !s)}>
        {show ? EYE_OFF : EYE}
      </button>
    </div>
  )
}
