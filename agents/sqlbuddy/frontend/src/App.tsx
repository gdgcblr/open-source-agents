import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api, ApiError } from './api'
import type { Answer, Dialect, SchemaInput, SessionDetail, SessionSummary } from './types'

const DIALECTS: { value: Dialect; label: string }[] = [
  { value: 'postgresql', label: 'PostgreSQL' },
  { value: 'mysql', label: 'MySQL' },
  { value: 'sqlite', label: 'SQLite' },
]

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Something went wrong. Please try again.'
}

export default function App() {
  const [question, setQuestion] = useState('')
  const [dialect, setDialect] = useState<Dialect>('sqlite')
  const [schemaText, setSchemaText] = useState('')
  const [schemaFile, setSchemaFile] = useState('')
  const [schema, setSchema] = useState<SchemaInput | null>(null)
  const [answer, setAnswer] = useState<Answer | null>(null)
  const [sessionId, setSessionId] = useState<string>()
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const refreshSessions = useCallback(async () => {
    try { setSessions(await api.listSessions()) } catch (problem) { setError(errorMessage(problem)) }
  }, [])

  useEffect(() => { void refreshSessions() }, [refreshSessions])

  function parseSchema(raw: string): SchemaInput {
    if (raw.length > 12000) throw new Error('Schema file is too large. Please keep it under 12,000 characters.')
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || !Array.isArray((parsed as SchemaInput).tables)) {
      throw new Error('Schema JSON must have a "tables" list.')
    }
    const tables = (parsed as SchemaInput).tables
    if (tables.length > 100 || tables.some((table) => !table || typeof table.name !== 'string' || !table.name.trim() || !Array.isArray(table.columns) || table.columns.length === 0 || table.columns.length > 100 || table.columns.some((column) => typeof column !== 'string' || !column.trim()))) {
      throw new Error('Each table needs a name and a list of non-empty column names (up to 100 each).')
    }
    return { tables }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setNotice('')
    if (!question.trim()) { setError('Type a question before asking SQLBuddy.'); return }
    let schemaValue = schema
    if (schemaText.trim()) {
      try { schemaValue = parseSchema(schemaText) } catch (problem) { setError(problem instanceof Error ? problem.message : 'Check your schema details.'); return }
    }
    setBusy(true)
    try {
      const result = await api.createQuery(question.trim(), dialect, schemaValue, sessionId)
      setAnswer(result.answer)
      setSessionId(result.session_id)
      await refreshSessions()
    } catch (problem) { setError(errorMessage(problem)) } finally { setBusy(false) }
  }

  async function loadFile(file?: File) {
    setError('')
    if (!file) return
    if (file.size > 12000) { setError('Please choose a JSON file under 12,000 bytes.'); return }
    try {
      const text = await file.text()
      const parsed = parseSchema(text)
      setSchema(parsed)
      setSchemaText(JSON.stringify(parsed, null, 2))
      setSchemaFile(file.name)
    } catch (problem) {
      setSchema(null)
      setSchemaText('')
      setSchemaFile('')
      setError(problem instanceof Error ? problem.message : 'Could not read that schema file.')
    }
  }

  async function openSession(item: SessionSummary) {
    setError('')
    try {
      const detail = await api.getSession(item.id)
      showSession(detail)
    } catch (problem) { setError(errorMessage(problem)) }
  }

  function showSession(detail: SessionDetail) {
    const latest = detail.messages[detail.messages.length - 1]
    setSessionId(detail.id)
    setDialect(latest?.dialect ?? detail.dialect)
    setQuestion(latest?.question ?? '')
    setAnswer(latest?.answer ?? null)
    setNotice(`Opened “${detail.title}”.`)
    setError('')
  }

  async function renameSession(item: SessionSummary) {
    const title = window.prompt('Choose a name for this saved session:', item.title)
    if (!title?.trim()) return
    try { await api.renameSession(item.id, title.trim()); await refreshSessions() }
    catch (problem) { setError(errorMessage(problem)) }
  }

  async function deleteSession(item: SessionSummary) {
    if (!window.confirm(`Delete “${item.title}” and its saved messages?`)) return
    try {
      await api.deleteSession(item.id)
      if (sessionId === item.id) startNew()
      await refreshSessions()
      setNotice('Saved session deleted.')
    } catch (problem) { setError(errorMessage(problem)) }
  }

  function startNew() {
    setQuestion(''); setSchemaText(''); setSchema(null); setSchemaFile(''); setAnswer(null)
    setSessionId(undefined); setError(''); setNotice('Ready for a new question.')
  }

  async function copySql() {
    if (!answer?.sql) return
    try { await navigator.clipboard.writeText(answer.sql); setNotice('SQL copied to clipboard.') }
    catch { setError('Could not copy automatically. Select the SQL and copy it with Ctrl+C.') }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="SQLBuddy home"><span className="brand-mark">S</span><span>sqlbuddy<span className="brand-dot">.</span></span></a>
        <span className="local-badge"><span /> Runs on your computer</span>
      </header>
      <div className="workspace" id="top">
        <aside className="sidebar" aria-label="Saved sessions">
          <div className="sidebar-heading"><div><span className="eyebrow">WORKSPACE</span><h2>Your history</h2></div><button className="icon-button" onClick={startNew} aria-label="Start a new question" title="New question">＋</button></div>
          <button className="new-query" onClick={startNew}><span>＋</span> New question</button>
          <div className="session-list">
            {sessions.length === 0 ? <p className="history-empty">Your saved questions will appear here.</p> : sessions.map((item) => (
              <div className={`session-row ${sessionId === item.id ? 'selected' : ''}`} key={item.id}>
                <button className="session-open" onClick={() => void openSession(item)} title={item.title}><span className="session-title">{item.title}</span><span className="session-meta">{item.dialect} · {new Date(item.updated_at).toLocaleDateString()}</span></button>
                <details className="session-menu"><summary aria-label={`Options for ${item.title}`}>···</summary><div className="menu-popover"><button onClick={() => void renameSession(item)}>Rename</button><button className="danger-text" onClick={() => void deleteSession(item)}>Delete</button></div></details>
              </div>
            ))}
          </div>
          <div className="sidebar-note"><span>🔒</span><p>Your saved history stays in a local SQLite file on this computer.</p></div>
        </aside>

        <main className="main-content">
          <div className="hero"><div className="eyebrow"><span className="sparkle">✳</span> YOUR SQL COPILOT</div><h1>SQL, <span>clearly.</span></h1><p>Describe what you need. Get a thoughtful query with a clear explanation.</p></div>

          <form className="query-card" onSubmit={(event) => void submit(event)}>
            <div className="card-topline"><label htmlFor="question">WHAT WOULD YOU LIKE TO QUERY?</label><span>{question.length}/4,000</span></div>
            <textarea id="question" value={question} onChange={(event) => setQuestion(event.target.value.slice(0, 4000))} maxLength={4000} placeholder="For example: Show me the 10 most recent orders with each customer's name…" rows={4} />
            <div className="form-divider" />
            <div className="settings-row">
              <div className="field-group"><label htmlFor="dialect">DATABASE TYPE</label><select id="dialect" value={dialect} onChange={(event) => setDialect(event.target.value as Dialect)}>{DIALECTS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>
              <div className="field-group schema-field"><label htmlFor="schema">YOUR TABLES <span>(OPTIONAL)</span></label><textarea id="schema" value={schemaText} onChange={(event) => { setSchemaText(event.target.value); setSchemaFile(''); setSchema(null) }} placeholder={'Paste schema JSON, e.g. {"tables":[{"name":"users","columns":["id","email"]}]}'} rows={2} /></div>
              <label className="file-button">{schemaFile ? `✓ ${schemaFile}` : '↑ Load JSON'}<input type="file" accept=".json,application/json" onChange={(event) => void loadFile(event.target.files?.[0])} aria-label="Load schema JSON file" /></label>
            </div>
            <div className="submit-row"><span className="privacy-hint"><span>✦</span> Read-only suggestions. Never run automatically.</span><button className="ask-button" type="submit" disabled={busy}>{busy ? <><span className="spinner" /> Thinking…</> : <>Ask SQLBuddy <span>↗</span></>}</button></div>
          </form>

          {error && <div className="alert error-alert" role="alert"><span>!</span><p>{error}</p><button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
          {notice && !error && <div className="notice" role="status">{notice}</div>}

          {answer ? <section className="answer-card" aria-label="SQLBuddy answer">
            <div className="answer-header"><div><span className="answer-icon">✳</span><div><h2>Your SQL suggestion</h2><p>For {DIALECTS.find((item) => item.value === dialect)?.label} · Generated just now</p></div></div><button className="secondary-button" onClick={() => void copySql()} disabled={!answer.sql}>▢ Copy SQL</button></div>
            {answer.sql ? <div className="sql-block"><div className="code-top"><span><i /> SQL</span><span>{dialect.toUpperCase()}</span></div><pre><code>{answer.sql}</code></pre></div> : <div className="blocked-sql">SQLBuddy did not provide an executable query because the request may change data.</div>}
            <div className="answer-section"><h3><span className="section-icon">↗</span> Explanation</h3><p>{answer.explanation}</p></div>
            {answer.assumptions.length > 0 && <div className="answer-section"><h3><span className="section-icon">◷</span> Assumptions</h3><ul>{answer.assumptions.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
            {answer.risks.length > 0 && <div className="answer-section risk-section"><h3><span className="section-icon">△</span> Risks & things to verify</h3><ul>{answer.risks.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
            <div className="unverified-note">ⓘ This SQL is generated text. It has not been run or verified.</div>
          </section> : <div className="empty-state"><div className="empty-art"><span>SELECT</span><span>✳</span><span>FROM ideas</span></div><h2>Your next query starts here</h2><p>Tell SQLBuddy what data you need. Add table details for a more tailored suggestion.</p></div>}
          <footer>SQLBuddy can make mistakes. Review suggestions carefully before using them.</footer>
        </main>
      </div>
    </div>
  )
}
