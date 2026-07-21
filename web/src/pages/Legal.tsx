import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { legalDoc, type LegalDoc } from '../api'
import { ui } from '../i18n'
import { LangSwitch } from './Shell'

// Юр-документ тянется из БД (единый источник) на языке интерфейса; текст в
// приложении не дублируется. Тело — абзацы через пустую строку.
export default function Legal() {
  const [doc, setDoc] = useState<LegalDoc | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    legalDoc('agreement').then(setDoc).catch((e) => setErr((e as Error).message))
  }, [])

  return (
    <div className="auth legal">
      <h1>{ui('Медкарта')} <LangSwitch /></h1>
      <div className="panel">
        {err && <p className="error">{err}</p>}
        {doc && (
          <>
            <h2>{doc.title}</h2>
            {doc.body.split('\n\n').map((p, i) => <p key={i}>{p}</p>)}
            <p className="muted">{ui('Редакция:')} {doc.version}</p>
          </>
        )}
        <p><Link to="/register">{ui('← к регистрации')}</Link></p>
      </div>
    </div>
  )
}
