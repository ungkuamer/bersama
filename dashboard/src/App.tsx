import { useEffect, useState } from 'react'
import { AlertCircle, Clock3, FolderGit2, GitBranch, ShieldCheck, TerminalSquare } from 'lucide-react'
import './App.css'

const API_BASE = import.meta.env.DEV ? `http://${window.location.hostname}:8000` : ''

interface Repo {
  name: string
  repo_path: string
  main_branch: string
  worktree_root: string
  global_concurrency: number
  per_prd_concurrency: number
  default_harness: string
}

interface SchedulingReadinessSnapshot {
  repo: {
    name: string
    path: string
    main_branch: string
    worktree_root: string
  }
  snapshot: {
    observed_at: string
    config_provenance: {
      source: string
      default_harness: {
        name: string
        timeout_seconds: number | null
      }
    }
    harness_summary: {
      default_harness: string
      timeout_seconds: number | null
    }
    readiness_checks: Array<{
      id: string
      label: string
      status: string
      detail?: string
    }>
    implementation_issue_state: {
      items: Array<{
        issue_number: number
        title: string
        status: string
      }>
      summary: Record<string, number>
    }
  }
}

const messageFromError = (error: unknown): string => {
  return error instanceof Error ? error.message : String(error)
}

const detailFromResponse = async (response: Response): Promise<string | undefined> => {
  const data: unknown = await response.json().catch(() => null)
  if (data && typeof data === 'object' && 'detail' in data) {
    const detail = data.detail
    return typeof detail === 'string' ? detail : undefined
  }
  return undefined
}

const formatObservedAt = (value: string): string => {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

const formatTimeout = (timeoutSeconds: number | null): string => {
  return timeoutSeconds === null ? 'Not configured' : `${timeoutSeconds}s`
}

function App() {
  const [repos, setRepos] = useState<Repo[]>([])
  const [selectedRepo, setSelectedRepo] = useState('')
  const [snapshot, setSnapshot] = useState<SchedulingReadinessSnapshot | null>(null)
  const [loadingRepos, setLoadingRepos] = useState(true)
  const [loadingSnapshot, setLoadingSnapshot] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true

    const fetchRepos = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/repos`)
        if (!response.ok) {
          throw new Error(await detailFromResponse(response) || `HTTP error ${response.status}`)
        }
        const data = (await response.json()) as Repo[]
        if (!active) return
        setRepos(data)
        setSelectedRepo((current) => current || data[0]?.name || '')
      } catch (err: unknown) {
        if (!active) return
        setError(`Failed to load repos: ${messageFromError(err)}`)
      } finally {
        if (active) {
          setLoadingRepos(false)
        }
      }
    }

    void fetchRepos()

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!selectedRepo) return

    let active = true
    setLoadingSnapshot(true)

    const fetchSnapshot = async () => {
      try {
        const response = await fetch(
          `${API_BASE}/api/scheduling-readiness/${encodeURIComponent(selectedRepo)}`
        )
        if (!response.ok) {
          throw new Error(await detailFromResponse(response) || `HTTP error ${response.status}`)
        }
        const data = (await response.json()) as SchedulingReadinessSnapshot
        if (!active) return
        setSnapshot(data)
        setError(null)
      } catch (err: unknown) {
        if (!active) return
        setSnapshot(null)
        setError(`Failed to load Scheduling Readiness: ${messageFromError(err)}`)
      } finally {
        if (active) {
          setLoadingSnapshot(false)
        }
      }
    }

    void fetchSnapshot()

    return () => {
      active = false
    }
  }, [selectedRepo])

  const summary = snapshot?.snapshot.implementation_issue_state.summary

  return (
    <div className="dashboard-shell">
      <div className="dashboard-backdrop" />
      <main className="dashboard-layout">
        <header className="hero-panel">
          <div className="hero-copy">
            <p className="eyebrow">Bersama</p>
            <h1>Scheduling Readiness</h1>
            <p className="hero-description">
              Read-only landing view for repo snapshot metadata and empty-state readiness structure.
            </p>
          </div>

          <label className="repo-picker">
            <span>REPO:</span>
            <select
              aria-label="Repo"
              value={selectedRepo}
              onChange={(event) => setSelectedRepo(event.target.value)}
              disabled={loadingRepos || repos.length === 0}
            >
              {repos.map((repo) => (
                <option key={repo.name} value={repo.name}>
                  {repo.name}
                </option>
              ))}
            </select>
          </label>
        </header>

        {error ? (
          <section className="error-panel" role="alert">
            <AlertCircle className="panel-icon" />
            <div>
              <h2>Snapshot unavailable</h2>
              <p>{error}</p>
            </div>
          </section>
        ) : null}

        <section className="panel-grid" aria-busy={loadingRepos || loadingSnapshot}>
          <article className="info-panel">
            <div className="panel-heading">
              <Clock3 className="panel-icon" />
              <div>
                <h2>Observed At</h2>
                <p>{snapshot ? formatObservedAt(snapshot.snapshot.observed_at) : 'Loading snapshot...'}</p>
              </div>
            </div>

            <dl className="metadata-list">
              <div>
                <dt>Repo Path</dt>
                <dd>{snapshot?.repo.path ?? 'Loading...'}</dd>
              </div>
              <div>
                <dt>Main Branch</dt>
                <dd>{snapshot?.repo.main_branch ?? 'Loading...'}</dd>
              </div>
              <div>
                <dt>Worktree Root</dt>
                <dd>{snapshot?.repo.worktree_root ?? 'Loading...'}</dd>
              </div>
            </dl>
          </article>

          <article className="info-panel">
            <div className="panel-heading">
              <TerminalSquare className="panel-icon" />
              <div>
                <h2>Harness Summary</h2>
                <p>Compact provenance only. Full prompts and templates stay hidden.</p>
              </div>
            </div>

            <dl className="metadata-list">
              <div>
                <dt>Default Harness</dt>
                <dd>{snapshot?.snapshot.harness_summary.default_harness ?? 'Loading...'}</dd>
              </div>
              <div>
                <dt>Harness Timeout</dt>
                <dd>{snapshot ? formatTimeout(snapshot.snapshot.harness_summary.timeout_seconds) : 'Loading...'}</dd>
              </div>
              <div>
                <dt>Config Provenance</dt>
                <dd>{snapshot?.snapshot.config_provenance.source ?? 'Loading...'}</dd>
              </div>
            </dl>
          </article>

          <article className="info-panel">
            <div className="panel-heading">
              <ShieldCheck className="panel-icon" />
              <div>
                <h2>Readiness Checks</h2>
                <p>Reserved structure for later readiness signals.</p>
              </div>
            </div>

            {snapshot && snapshot.snapshot.readiness_checks.length > 0 ? (
              <ul className="empty-list">
                {snapshot.snapshot.readiness_checks.map((check) => (
                  <li key={check.id}>
                    <strong>{check.label}</strong>
                    <span>{check.status}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-state">No readiness checks yet.</p>
            )}
          </article>

          <article className="info-panel">
            <div className="panel-heading">
              <GitBranch className="panel-icon" />
              <div>
                <h2>Implementation Issue State</h2>
                <p>Read-only issue summary shell for later scheduling detail.</p>
              </div>
            </div>

            <div className="summary-strip">
              <span>Ready {summary?.ready ?? 0}</span>
              <span>Blocked {summary?.blocked ?? 0}</span>
              <span>Claimed {summary?.claimed ?? 0}</span>
              <span>Running {summary?.running ?? 0}</span>
              <span>Failed {summary?.failed ?? 0}</span>
              <span>Succeeded {summary?.succeeded ?? 0}</span>
            </div>

            {snapshot && snapshot.snapshot.implementation_issue_state.items.length > 0 ? (
              <ul className="empty-list">
                {snapshot.snapshot.implementation_issue_state.items.map((item) => (
                  <li key={item.issue_number}>
                    <strong>#{item.issue_number}</strong>
                    <span>{item.title}</span>
                    <span>{item.status}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-state">No implementation issues observed yet.</p>
            )}
          </article>

          <article className="info-panel wide-panel">
            <div className="panel-heading">
              <FolderGit2 className="panel-icon" />
              <div>
                <h2>Landing View Guardrails</h2>
                <p>This landing view is intentionally passive.</p>
              </div>
            </div>

            <ul className="guardrail-list">
              <li>Read-only snapshot only.</li>
              <li>No lifecycle action buttons.</li>
              <li>No automatic refresh after initial page load.</li>
              <li>No simulated Scheduling Pass.</li>
              <li>No Lifecycle Mutations on load.</li>
            </ul>
          </article>
        </section>
      </main>
    </div>
  )
}

export default App
