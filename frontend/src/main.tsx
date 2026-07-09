import React, { FormEvent, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Database,
  Gauge,
  LayoutDashboard,
  Loader2,
  Play,
  RefreshCw,
  Server,
  Settings,
  XCircle,
} from 'lucide-react'
import './styles.css'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

type Dashboard = {
  id: number
  name: string
  description?: string | null
  archived: boolean
  updated_at?: string | null
}

type SupersetDatabase = {
  id: number
  name: string
  backend?: string | null
}

type MigrationJob = {
  id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  progress: { percent: number; stage: string; detail?: string | null }
  requested_dashboards: number
  results: Array<Record<string, any>>
  summary?: {
    overall_status: string
    dashboard_names: string[]
    dashboards_requested: number
    dashboards_migrated: number
    charts_migrated: number
    failed_charts: number
    skipped_charts: number
    warnings: Array<Record<string, any>>
    superset_dashboard_ids: number[]
    duration_seconds: number
  } | null
  error?: string | null
}

type Credentials = {
  metabase_url: string
  metabase_email: string
  metabase_password: string
  superset_url: string
  superset_username: string
  superset_password: string
  superset_database_id: string
}

const initialCredentials: Credentials = {
  metabase_url: 'http://localhost:3000',
  metabase_email: '',
  metabase_password: '',
  superset_url: 'http://localhost:8088',
  superset_username: '',
  superset_password: '',
  superset_database_id: '',
}

async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: body ? 'POST' : 'GET',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail ?? `Request failed with status ${response.status}`)
  }
  return payload as T
}

function App() {
  const [activeView, setActiveView] = useState<'dashboard' | 'migration' | 'history' | 'settings'>('dashboard')
  const [credentials, setCredentials] = useState<Credentials>(initialCredentials)
  const [dashboards, setDashboards] = useState<Dashboard[]>([])
  const [databases, setDatabases] = useState<SupersetDatabase[]>([])
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [job, setJob] = useState<MigrationJob | null>(null)
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState<'dashboards' | 'databases' | 'migration' | null>(null)

  const stats = useMemo(() => {
    const summary = job?.summary
    return [
      { label: 'Dashboards', value: summary?.dashboards_migrated ?? dashboards.length, tone: 'blue' },
      { label: 'Selected', value: selected.size, tone: 'green' },
      { label: 'Charts Migrated', value: summary?.charts_migrated ?? 0, tone: 'blue' },
      { label: 'Failed Charts', value: summary?.failed_charts ?? 0, tone: 'red' },
    ]
  }, [dashboards.length, job?.summary, selected.size])

  function updateCredential(name: keyof Credentials, value: string) {
    setCredentials(current => ({ ...current, [name]: value }))
  }

  function toggleDashboard(id: number) {
    setSelected(current => {
      const next = new Set(current)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  function explainConnectionError(error: unknown, service: 'Metabase' | 'Superset') {
    const raw = error instanceof Error ? error.message : String(error)
    if (raw.includes('Could not reach') || raw.includes('502')) {
      const port = service === 'Metabase' ? '3000' : '8088'
      return `${service} is not reachable at the URL entered. Start ${service}, check that it is running on port ${port}, then try again. Original error: ${raw}`
    }
    return raw
  }

  async function loadDashboards(event?: FormEvent) {
    event?.preventDefault()
    setLoading('dashboards')
    setMessage('Connecting to Metabase and reading accessible dashboards...')
    try {
      const result = await api<Dashboard[]>('/api/metabase/dashboards', {
        metabase_url: credentials.metabase_url,
        metabase_email: credentials.metabase_email,
        metabase_password: credentials.metabase_password,
      })
      setDashboards(result)
      setSelected(new Set(result.map(item => item.id)))
      setMessage(`Loaded ${result.length} dashboard${result.length === 1 ? '' : 's'} from Metabase.`)
    } catch (error) {
      setMessage(explainConnectionError(error, 'Metabase'))
      setDashboards([])
      setSelected(new Set())
    } finally {
      setLoading(null)
    }
  }

  async function loadDatabases(event?: FormEvent) {
    event?.preventDefault()
    setLoading('databases')
    setMessage('Authenticating with Superset and reading database metadata...')
    try {
      const result = await api<SupersetDatabase[]>('/api/superset/databases', {
        superset_url: credentials.superset_url,
        superset_username: credentials.superset_username,
        superset_password: credentials.superset_password,
      })
      setDatabases(result)
      setMessage(`Loaded ${result.length} Superset database${result.length === 1 ? '' : 's'}.`)
    } catch (error) {
      setMessage(explainConnectionError(error, 'Superset'))
    } finally {
      setLoading(null)
    }
  }

  async function startMigration(event?: FormEvent) {
    event?.preventDefault()
    setActiveView('migration')
    if (selected.size === 0) {
      setMessage('Load dashboards from Metabase, then select at least one dashboard before starting migration.')
      return
    }
    setLoading('migration')
    setMessage('Migration job starting...')
    try {
      const started = await api<MigrationJob>('/api/migrations', {
        ...credentials,
        superset_database_id: credentials.superset_database_id ? Number(credentials.superset_database_id) : null,
        dashboard_ids: Array.from(selected),
      })
      setJob(started)
      pollMigration(started.id)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
      setLoading(null)
    }
  }

  async function pollMigration(jobId: string) {
    const interval = window.setInterval(async () => {
      try {
        const current = await api<MigrationJob>(`/api/migrations/${jobId}`)
        setJob(current)
        setMessage(current.progress.detail ?? current.progress.stage)
        if (current.status === 'completed' || current.status === 'failed') {
          window.clearInterval(interval)
          setLoading(null)
        }
      } catch (error) {
        window.clearInterval(interval)
        setLoading(null)
        setMessage(error instanceof Error ? error.message : String(error))
      }
    }, 900)
  }

  const allSelected = dashboards.length > 0 && selected.size === dashboards.length
  const canMigrate = !loading

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <Gauge size={34} />
          <div>
            <strong>MigrAI</strong>
            <span>Metabase to Superset</span>
          </div>
        </div>
        <nav>
          <button className={activeView === 'dashboard' ? 'active' : ''} onClick={() => setActiveView('dashboard')}><LayoutDashboard size={20} /> Dashboard</button>
          <button className={activeView === 'migration' ? 'active' : ''} onClick={() => setActiveView('migration')}><RefreshCw size={20} /> Migration</button>
          <button className={activeView === 'history' ? 'active' : ''} onClick={() => setActiveView('history')}><Activity size={20} /> History</button>
          <button className={activeView === 'settings' ? 'active' : ''} onClick={() => setActiveView('settings')}><Settings size={20} /> Settings</button>
        </nav>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">API-driven dashboard migration</p>
            <h1>MigrAI</h1>
          </div>
          <button className="primary" disabled={!canMigrate} onClick={startMigration}>
            {loading === 'migration' ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
            Start Migration
          </button>
        </header>

        <section className="stats-grid">
          {stats.map(stat => (
            <article className="metric-card" key={stat.label}>
              <span>{stat.label}</span>
              <strong className={stat.tone}>{stat.value}</strong>
            </article>
          ))}
        </section>

        {message && activeView !== 'migration' && (
          <section className={`panel message-panel ${message.includes('not reachable') || message.includes('Original error') ? 'message-error' : 'message-info'}`}>
            {message.includes('not reachable') || message.includes('Original error') ? <XCircle size={22} /> : <CheckCircle2 size={22} />}
            <p>{message}</p>
          </section>
        )}

        {activeView === 'dashboard' && <section className="connection-grid">
          <form className="panel" onSubmit={loadDashboards}>
            <div className="panel-title"><Database size={20} /><h2>Metabase</h2></div>
            <Field label="URL" value={credentials.metabase_url} onChange={value => updateCredential('metabase_url', value)} />
            <Field label="Email" type="email" value={credentials.metabase_email} onChange={value => updateCredential('metabase_email', value)} />
            <Field label="Password" type="password" value={credentials.metabase_password} onChange={value => updateCredential('metabase_password', value)} />
            <button className="secondary" disabled={loading === 'dashboards'}>
              {loading === 'dashboards' ? <Loader2 className="spin" size={17} /> : <RefreshCw size={17} />}
              Load Dashboards
            </button>
          </form>

          <form className="panel" onSubmit={loadDatabases}>
            <div className="panel-title"><Server size={20} /><h2>Apache Superset</h2></div>
            <Field label="URL" value={credentials.superset_url} onChange={value => updateCredential('superset_url', value)} />
            <Field label="Username" value={credentials.superset_username} onChange={value => updateCredential('superset_username', value)} />
            <Field label="Password" type="password" value={credentials.superset_password} onChange={value => updateCredential('superset_password', value)} />
            <label className="field">
              <span>Database</span>
              <select value={credentials.superset_database_id} onChange={event => updateCredential('superset_database_id', event.target.value)}>
                <option value="">Auto match by metadata</option>
                {databases.map(database => (
                  <option value={database.id} key={database.id}>{database.name}</option>
                ))}
              </select>
            </label>
            <button className="secondary" disabled={loading === 'databases'}>
              {loading === 'databases' ? <Loader2 className="spin" size={17} /> : <RefreshCw size={17} />}
              Load Databases
            </button>
          </form>
        </section>}

        {activeView === 'dashboard' && <section className="panel dashboard-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Dashboard selection</p>
              <h2>Accessible Metabase dashboards</h2>
            </div>
            <button className="ghost" disabled={!dashboards.length} onClick={() => setSelected(allSelected ? new Set() : new Set(dashboards.map(item => item.id)))}>
              {allSelected ? 'Clear all' : 'Select all'}
            </button>
          </div>
          <div className="dashboard-list">
            {dashboards.length === 0 ? (
              <div className="empty-state">Load dashboards after entering Metabase credentials.</div>
            ) : dashboards.map(dashboard => (
              <label className="dashboard-row" key={dashboard.id}>
                <input type="checkbox" checked={selected.has(dashboard.id)} onChange={() => toggleDashboard(dashboard.id)} />
                <span>
                  <strong>{dashboard.name}</strong>
                  <small>#{dashboard.id}{dashboard.updated_at ? ` · Updated ${new Date(dashboard.updated_at).toLocaleDateString()}` : ''}</small>
                </span>
              </label>
            ))}
          </div>
        </section>}

        {activeView === 'migration' && <section className="panel progress-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Migration progress</p>
              <h2>{job ? job.progress.stage : 'Ready'}</h2>
            </div>
            {job?.status === 'completed' ? <CheckCircle2 className="ok" /> : job?.status === 'failed' ? <XCircle className="bad" /> : null}
          </div>
          <div className="progress-track"><span style={{ width: `${job?.progress.percent ?? 0}%` }} /></div>
          <p className={`status-line ${message.includes('not reachable') || message.includes('Original error') ? 'error-text' : ''}`}>
            {message || 'Connect both systems, select dashboards, then start migration.'}
          </p>
          <div className="action-row">
            <button className="secondary compact" onClick={() => setActiveView('dashboard')}>
              <Database size={17} />
              Edit Connections
            </button>
            <button className="secondary compact" disabled={loading === 'dashboards'} onClick={() => loadDashboards()}>
              <RefreshCw size={17} />
              Retry Metabase
            </button>
            <button className="secondary compact" disabled={loading === 'databases'} onClick={() => loadDatabases()}>
              <RefreshCw size={17} />
              Retry Superset
            </button>
          </div>
        </section>}

        {activeView === 'history' && (
          <section className="panel report-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">History</p>
                <h2>Migration history</h2>
              </div>
              <Activity />
            </div>
            {job ? (
              <div className="result-table">
                <div className="result-row">
                  <span>{job.summary?.dashboard_names?.join(', ') || 'Current migration job'}</span>
                  <strong>{job.status}</strong>
                  <small>{job.progress.percent}%</small>
                </div>
              </div>
            ) : (
              <div className="empty-state">No migration has been started in this browser session.</div>
            )}
          </section>
        )}

        {activeView === 'settings' && (
          <section className="panel report-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Settings</p>
                <h2>Connection settings</h2>
              </div>
              <Settings />
            </div>
            <div className="settings-grid">
              <div><span>API backend</span><strong>{API_BASE_URL}</strong></div>
              <div><span>Metabase URL</span><strong>{credentials.metabase_url}</strong></div>
              <div><span>Superset URL</span><strong>{credentials.superset_url}</strong></div>
            </div>
          </section>
        )}

        {activeView === 'migration' && !message && (
          <section className="panel helper-panel">
            <AlertCircle />
            <p>Metabase must be running at `http://localhost:3000` and Superset must be running at `http://localhost:8088`, or you must change the URLs to the correct running services.</p>
          </section>
        )}

        {activeView === 'migration' && job?.summary && (
          <section className="panel report-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Final report</p>
                <h2>{job.summary.overall_status.replace(/_/g, ' ')}</h2>
              </div>
              <strong>{job.summary.duration_seconds}s</strong>
            </div>
            <div className="report-grid">
              <Report label="Dashboards migrated" value={job.summary.dashboards_migrated} />
              <Report label="Charts migrated" value={job.summary.charts_migrated} />
              <Report label="Failed charts" value={job.summary.failed_charts} />
              <Report label="Skipped charts" value={job.summary.skipped_charts} />
            </div>
            <div className="result-table">
              {job.results.map(result => (
                <div className="result-row" key={String(result.superset_dashboard_id ?? result.dashboard_name)}>
                  <span>{result.dashboard_name}</span>
                  <strong>{result.charts_imported} charts</strong>
                  <small>Superset #{result.superset_dashboard_id}</small>
                </div>
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  )
}

function Field(props: { label: string; value: string; onChange: (value: string) => void; type?: string }) {
  return (
    <label className="field">
      <span>{props.label}</span>
      <input required type={props.type ?? 'text'} value={props.value} onChange={event => props.onChange(event.target.value)} />
    </label>
  )
}

function Report(props: { label: string; value: number }) {
  return (
    <div className="report-item">
      <span>{props.label}</span>
      <strong>{props.value}</strong>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<App />)
