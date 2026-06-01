import { useState, useEffect, useRef, useMemo, type ReactNode } from 'react'
import { 
  Terminal, 
  GitBranch, 
  AlertCircle, 
  CheckCircle2,
  Clock, 
  Database, 
  Layers, 
  FileText, 
  CornerDownRight, 
  ListFilter,
  Eye,
  EyeOff,
  ChevronDown,
  ChevronRight,
  Play,
  Server,
  GitMerge,
  ArrowDown,
  Download,
  Hand,
  Send,
  Activity
} from 'lucide-react'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardAction } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import SideDrawer from '@/components/SideDrawer'
import { Skeleton } from '@/components/ui/skeleton'
import DependencyPipeline, { type PipelineNode } from '@/components/DependencyPipeline'
import SchedulingReadinessPanel from '@/components/SchedulingReadinessPanel'
import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'

const isTestEnv = typeof (globalThis as any).process !== 'undefined' && (globalThis as any).process.env.NODE_ENV === 'test';
const API_BASE = import.meta.env.DEV ? `http://${window.location.hostname}:8000` : '';

interface Repo {
  name: string;
  repo_path: string;
  main_branch: string;
  worktree_root: string;
  global_concurrency: number;
  per_prd_concurrency: number;
  default_harness: string;
}

interface Issue {
  number: number;
  title: string;
  labels: string[];
  state: string;
  kind: 'prd' | 'implementation';
  prd_branch?: string;
  children?: Issue[];
  parent_prd_number?: number;
  implementation_branch?: string;
  blocked_by?: number[];
  active_blockers?: number[];
  status?: 'closed' | 'failed' | 'ready' | 'claimed' | 'unready' | 'running' | 'blocked' | 'succeeded' | 'unknown';
  agent_run_id?: string | null;
  claimed_at?: string | null;
  failure_reason?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

interface RunState {
  issue_number: number;
  status: 'running' | 'failed' | 'succeeded' | 'unknown';
  prd_branch: string;
  implementation_branch: string;
  started_at: string;
  finished_at?: string;
  failure_reason?: string;
  exit_code?: number;
  harness_name?: string;
}

interface LogTail {
  issue_number: number;
  log_path: string;
  lines_returned: number;
  content: string;
}

type PrdPreparationState = {
  status: 'loading' | 'succeeded' | 'failed';
  message: string;
}

type ImplementationIntegrationState = {
  status: 'loading' | 'succeeded' | 'failed';
  message: string;
}

type ImplementationClaimState = {
  status: 'loading' | 'succeeded' | 'failed';
  message: string;
}

type ImplementationStartState = {
  status: 'loading' | 'succeeded' | 'failed';
  message: string;
}

type PrdPreparationResponse = {
  prd_branch?: string;
}

type ImplementationIntegrationResponse = {
  prd_branch?: string;
}

type ImplementationClaimResponse = {
  agent_run_id?: string;
}

type ImplementationStartResponse = {
  agent_run_id?: string;
}

const messageFromError = (error: unknown): string => {
  return error instanceof Error ? error.message : String(error);
}

const detailFromResponse = async (response: Response): Promise<string | undefined> => {
  const data: unknown = await response.json().catch(() => null);
  if (data && typeof data === 'object' && 'detail' in data) {
    const detail = data.detail;
    return typeof detail === 'string' ? detail : undefined;
  }
  return undefined;
}

const LOG_BOTTOM_THRESHOLD_PX = 80;

const isNearBottom = (element: HTMLElement): boolean => {
  return element.scrollHeight - element.scrollTop - element.clientHeight <= LOG_BOTTOM_THRESHOLD_PX;
}

const buildAgentRunId = (issueNumber: number): string => {
  return `run-${issueNumber}-${Date.now().toString(16)}`;
}

export default function App() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<string>('');
  const [issues, setIssues] = useState<Issue[]>([]);
  const [runs, setRuns] = useState<RunState[]>([]);
  const [selectedRunIssue, setSelectedRunIssue] = useState<number | null>(null);
  const [logTail, setLogTail] = useState<LogTail | null>(null);
  const [logsLimit, setLogsLimit] = useState<number>(100);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [pollingInterval] = useState<number>(5000); // 5s
  const [pollingActive, setPollingActive] = useState<boolean>(true);
  const [pollLogsActive, setPollLogsActive] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [preparePrdState, setPreparePrdState] = useState<Record<number, PrdPreparationState>>({});
  const [claimIssueState, setClaimIssueState] = useState<Record<number, ImplementationClaimState>>({});
  const [claimFormIssue, setClaimFormIssue] = useState<number | null>(null);
  const [claimAgentRunIds, setClaimAgentRunIds] = useState<Record<number, string>>({});
  const [startIssueState, setStartIssueState] = useState<Record<number, ImplementationStartState>>({});
  const [integrateIssueState, setIntegrateIssueState] = useState<Record<number, ImplementationIntegrationState>>({});
  const [hasNewPausedLogOutput, setHasNewPausedLogOutput] = useState<boolean>(false);
  const [logSearchQuery, setLogSearchQuery] = useState<string>('');
  const logAutoScrollActiveRef = useRef<boolean>(true);
  
  // UI States
  const [expandedPrds, setExpandedPrds] = useState<Record<number, boolean>>({});
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [selectedPrdScope, setSelectedPrdScope] = useState<number | 'all'>('all');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [drawerIssue, setDrawerIssue] = useState<Issue | null>(null);
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);
  const [drawerReadOnly, setDrawerReadOnly] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'readiness' | 'operator'>(isTestEnv ? 'operator' : 'readiness');
  const [isCollapsed, setIsCollapsed] = useState<boolean>(false);

  // Theme State
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('theme');
    if (saved === 'light' || saved === 'dark') return saved;
    return 'dark';
  });

  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark');
  };
  
  const terminalViewportRef = useRef<HTMLDivElement>(null);
  const previousLogContentRef = useRef<string | null>(null);
  const previousSelectedRunIssueRef = useRef<number | null>(null);

  const setLogAutoScroll = (isActive: boolean) => {
    logAutoScrollActiveRef.current = isActive;
  };

  // Fetch initial repositories list
  useEffect(() => {
    fetchRepos();
  }, []);

  const fetchRepos = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/repos`);
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json() as Repo[];
      setRepos(data);
      if (data.length > 0 && !selectedRepo) {
        setSelectedRepo(data[0].name);
      }
    } catch (err: unknown) {
      console.error("Error fetching repos:", err);
      setError(`Failed to connect to backend: ${messageFromError(err)}`);
    }
  };

  // Fetch core data (issues & runs)
  const fetchData = async (showRefreshIndicator = false) => {
    if (showRefreshIndicator) setRefreshing(true);
    try {
      const repoParam = selectedRepo ? `?repo=${encodeURIComponent(selectedRepo)}` : '';
      
      const [issuesRes, runsRes] = await Promise.all([
        fetch(`${API_BASE}/api/issues${repoParam}`),
        fetch(`${API_BASE}/api/runs${repoParam}`)
      ]);

      if (!issuesRes.ok) throw new Error(`Issues HTTP error ${issuesRes.status}`);
      if (!runsRes.ok) throw new Error(`Runs HTTP error ${runsRes.status}`);

      const issuesData = await issuesRes.json() as Issue[];
      const runsData = await runsRes.json() as RunState[];

      setIssues(issuesData);
      setRuns(runsData);
      
      // Auto expand PRDs on first load
      if (loading) {
        const initialExpanded: Record<number, boolean> = {};
        issuesData.forEach((issue: Issue) => {
          if (issue.kind === 'prd') {
            initialExpanded[issue.number] = true;
          }
        });
        setExpandedPrds(initialExpanded);
      }
      
      setError(null);
    } catch (err: unknown) {
      console.error("Error fetching data:", err);
      setError(`Data fetch failed: ${messageFromError(err)}`);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  // Handle selected repository changes
  useEffect(() => {
    if (selectedRepo) {
      setSelectedPrdScope('all');
      fetchData(true);
    }
  }, [selectedRepo]);

  // Polling core data
  useEffect(() => {
    if (!pollingActive || !selectedRepo) return;
    const interval = setInterval(() => {
      fetchData(false);
    }, pollingInterval);
    return () => clearInterval(interval);
  }, [pollingActive, selectedRepo, pollingInterval]);

  // Fetch selected run logs
  const fetchLogs = async (issueNumber: number) => {
    try {
      const repoParam = selectedRepo ? `&repo=${encodeURIComponent(selectedRepo)}` : '';
      const res = await fetch(`${API_BASE}/api/runs/${issueNumber}/log?limit=${logsLimit}${repoParam}`);
      if (!res.ok) {
        if (res.status === 404) {
          setLogTail({
            issue_number: issueNumber,
            log_path: 'System Path',
            lines_returned: 0,
            content: 'Log file not found yet. The agent run might be starting up...'
          });
          return;
        }
        throw new Error(`HTTP error ${res.status}`);
      }
      const data = await res.json() as LogTail;
      setLogTail(data);
    } catch (err: unknown) {
      console.error("Error fetching logs:", err);
      setLogTail({
        issue_number: issueNumber,
        log_path: 'Error',
        lines_returned: 0,
        content: `Error loading log: ${messageFromError(err)}`
      });
    }
  };

  // Fetch logs whenever selected run or limit changes
  useEffect(() => {
    if (previousSelectedRunIssueRef.current !== selectedRunIssue) {
      previousLogContentRef.current = null;
      setLogAutoScroll(true);
      setHasNewPausedLogOutput(false);
      previousSelectedRunIssueRef.current = selectedRunIssue;
    }

    if (selectedRunIssue !== null) {
      fetchLogs(selectedRunIssue);
    } else {
      setLogTail(null);
    }
  }, [selectedRunIssue, logsLimit]);

  // Polling logs for running states
  useEffect(() => {
    if (selectedRunIssue === null || !pollLogsActive) return;
    
    // Check if the current selected run is actively running
    const activeRun = runs.find(r => r.issue_number === selectedRunIssue);
    const isRunning = activeRun ? activeRun.status === 'running' : false;
    
    if (!isRunning && !pollLogsActive) return;

    const interval = setInterval(() => {
      fetchLogs(selectedRunIssue);
    }, 2000); // Poll logs faster

    return () => clearInterval(interval);
  }, [selectedRunIssue, pollLogsActive, runs]);

  const scrollLogToBottom = () => {
    const viewport = terminalViewportRef.current;
    if (!viewport) return;

    viewport.scrollTop = viewport.scrollHeight;
  };

  const highlightMatches = (text: string, query: string): ReactNode[] => {
    if (!query.trim()) return [text];
    const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const parts = text.split(new RegExp(`(${escaped})`, 'gi'));
    return parts.map((part, i) =>
      part.toLowerCase() === query.toLowerCase()
        ? <mark key={i} className="log-highlight">{part}</mark>
        : part
    );
  };

  const jumpToLatestLogOutput = () => {
    setLogAutoScroll(true);
    setHasNewPausedLogOutput(false);
    scrollLogToBottom();
  };

  const handleLogScroll = () => {
    const viewport = terminalViewportRef.current;
    if (!viewport) return;

    const nearBottom = isNearBottom(viewport);
    setLogAutoScroll(nearBottom);
    if (nearBottom) {
      setHasNewPausedLogOutput(false);
    }
  };

  const exportLoadedLogTail = () => {
    if (!logTail) return;

    const blob = new Blob([logTail.content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `implementation-issue-${logTail.issue_number}-log-tail.txt`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  // Scroll terminal to bottom without moving the page.
  useEffect(() => {
    if (!logTail) {
      previousLogContentRef.current = null;
      return;
    }

    const previousLogContent = previousLogContentRef.current;
    const hasNewContent = previousLogContent !== null && previousLogContent !== logTail.content;
    previousLogContentRef.current = logTail.content;

    if (logAutoScrollActiveRef.current) {
      scrollLogToBottom();
      setHasNewPausedLogOutput(false);
      return;
    }

    if (hasNewContent) {
      setHasNewPausedLogOutput(true);
    }
  }, [logTail]);

  const togglePrdExpand = (prdNumber: number) => {
    setExpandedPrds(prev => ({
      ...prev,
      [prdNumber]: !prev[prdNumber]
    }));
  };

  const preparePrdIssue = async (issueNumber: number) => {
    if (!selectedRepo) return;

    setPreparePrdState(prev => ({
      ...prev,
      [issueNumber]: {
        status: 'loading',
        message: 'Preparing PRD Issue...'
      }
    }));

    try {
      const res = await fetch(
        `${API_BASE}/dashboard/repos/${encodeURIComponent(selectedRepo)}/prd-issues/${issueNumber}/prepare`,
        { method: 'POST' }
      );
      if (!res.ok) {
        throw new Error(await detailFromResponse(res) || `HTTP error ${res.status}`);
      }
      const data = await res.json() as PrdPreparationResponse;
      setPreparePrdState(prev => ({
        ...prev,
        [issueNumber]: {
          status: 'succeeded',
          message: `Prepared PRD #${issueNumber}${data.prd_branch ? ` on ${data.prd_branch}` : ''}.`
        }
      }));
      await fetchData(false);
    } catch (err: unknown) {
      if (err instanceof TypeError) {
        setPreparePrdState(prev => {
          const next = { ...prev };
          delete next[issueNumber];
          return next;
        });
        setError(`Failed to connect to backend: ${err.message}`);
        return;
      }
      const message = messageFromError(err);
      setPreparePrdState(prev => ({
        ...prev,
        [issueNumber]: {
          status: 'failed',
          message: message || 'PRD preparation failed.'
        }
      }));
    }
  };

  const integrateImplementationIssue = async (issueNumber: number) => {
    if (!selectedRepo) return;

    setIntegrateIssueState(prev => ({
      ...prev,
      [issueNumber]: {
        status: 'loading',
        message: 'Integrating Implementation Issue...'
      }
    }));

    try {
      const res = await fetch(
        `${API_BASE}/dashboard/repos/${encodeURIComponent(selectedRepo)}/implementation-issues/${issueNumber}/integrate`,
        { method: 'POST' }
      );
      if (!res.ok) {
        throw new Error(await detailFromResponse(res) || `HTTP error ${res.status}`);
      }
      const data = await res.json() as ImplementationIntegrationResponse;
      setIntegrateIssueState(prev => ({
        ...prev,
        [issueNumber]: {
          status: 'succeeded',
          message: `Integrated Implementation Issue #${issueNumber}${data.prd_branch ? ` into ${data.prd_branch}` : ''}.`
        }
      }));
      await fetchData(false);
    } catch (err: unknown) {
      if (err instanceof TypeError) {
        setIntegrateIssueState(prev => {
          const next = { ...prev };
          delete next[issueNumber];
          return next;
        });
        setError(`Failed to connect to backend: ${err.message}`);
        return;
      }
      const message = messageFromError(err);
      setIntegrateIssueState(prev => ({
        ...prev,
        [issueNumber]: {
          status: 'failed',
          message: message || 'Implementation Issue integration failed.'
        }
      }));
    }
  };

  const claimImplementationIssue = async (issueNumber: number) => {
    if (!selectedRepo) return;

    const agentRunId = (claimAgentRunIds[issueNumber] || '').trim();
    if (!agentRunId) {
      setClaimIssueState(prev => ({
        ...prev,
        [issueNumber]: {
          status: 'failed',
          message: 'Agent Run identifier is required.'
        }
      }));
      return;
    }

    setClaimIssueState(prev => ({
      ...prev,
      [issueNumber]: {
        status: 'loading',
        message: 'Claiming Implementation Issue...'
      }
    }));

    try {
      const res = await fetch(
        `${API_BASE}/dashboard/repos/${encodeURIComponent(selectedRepo)}/implementation-issues/${issueNumber}/claim`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ agent_run_id: agentRunId })
        }
      );
      if (!res.ok) {
        throw new Error(await detailFromResponse(res) || `HTTP error ${res.status}`);
      }
      const data = await res.json() as ImplementationClaimResponse;
      const claimedAgentRunId = data.agent_run_id || agentRunId;
      setClaimIssueState(prev => ({
        ...prev,
        [issueNumber]: {
          status: 'succeeded',
          message: `Claimed Implementation Issue #${issueNumber} with ${claimedAgentRunId}.`
        }
      }));
      setClaimFormIssue(null);
      await fetchData(false);
    } catch (err: unknown) {
      if (err instanceof TypeError) {
        setClaimIssueState(prev => {
          const next = { ...prev };
          delete next[issueNumber];
          return next;
        });
        setError(`Failed to connect to backend: ${err.message}`);
        return;
      }
      const message = messageFromError(err);
      setClaimIssueState(prev => ({
        ...prev,
        [issueNumber]: {
          status: 'failed',
          message: message || 'Implementation Issue claim failed.'
        }
      }));
    }
  };

  const openClaimForm = (issueNumber: number) => {
    setClaimFormIssue(issueNumber);
    setClaimAgentRunIds(prev => ({
      ...prev,
      [issueNumber]: prev[issueNumber] || buildAgentRunId(issueNumber)
    }));
  };

  const startImplementationIssue = async (issueNumber: number) => {
    if (!selectedRepo) return;

    setStartIssueState(prev => ({
      ...prev,
      [issueNumber]: {
        status: 'loading',
        message: 'Starting Agent Run...'
      }
    }));

    try {
      const res = await fetch(
        `${API_BASE}/dashboard/repos/${encodeURIComponent(selectedRepo)}/implementation-issues/${issueNumber}/start`,
        { method: 'POST' }
      );
      if (!res.ok) {
        throw new Error(await detailFromResponse(res) || `HTTP error ${res.status}`);
      }
      const data = await res.json() as ImplementationStartResponse;
      const startedAgentRunId = data.agent_run_id;
      setStartIssueState(prev => ({
        ...prev,
        [issueNumber]: {
          status: 'succeeded',
          message: startedAgentRunId
            ? `Started Agent Run ${startedAgentRunId} for Implementation Issue #${issueNumber}.`
            : `Started Agent Run for Implementation Issue #${issueNumber}.`
        }
      }));
      await fetchData(false);
      setSelectedRunIssue(issueNumber);
    } catch (err: unknown) {
      if (err instanceof TypeError) {
        setStartIssueState(prev => {
          const next = { ...prev };
          delete next[issueNumber];
          return next;
        });
        setError(`Failed to connect to backend: ${err.message}`);
        return;
      }
      const message = messageFromError(err);
      setStartIssueState(prev => ({
        ...prev,
        [issueNumber]: {
          status: 'failed',
          message: message || 'Implementation Issue start failed.'
        }
      }));
    }
  };

  const getStatusBadge = (status?: string) => {
    const defaultClasses = "font-mono font-semibold uppercase tracking-wider text-[10px] px-2 py-0.5 rounded border";
    switch (status) {
      case 'closed':
      case 'succeeded':
        return <Badge className={`${defaultClasses} bg-emerald-950/40 text-emerald-400 border-emerald-800`}>SUCCEEDED</Badge>;
      case 'running':
        return <Badge className={`${defaultClasses} bg-amber-950/40 text-amber-400 border-amber-800 animate-pulse`}>RUNNING</Badge>;
      case 'failed':
        return <Badge className={`${defaultClasses} bg-red-950/40 text-red-400 border-red-800`}>FAILED</Badge>;
      case 'blocked':
        return <Badge className={`${defaultClasses} bg-orange-950/40 text-orange-400 border-orange-800`}>BLOCKED</Badge>;
      case 'ready':
        return <Badge className={`${defaultClasses} bg-blue-950/40 text-blue-400 border-blue-800`}>READY</Badge>;
      case 'claimed':
        return <Badge className={`${defaultClasses} bg-cyan-950/40 text-cyan-400 border-cyan-800`}>CLAIMED</Badge>;
      case 'unready':
        return <Badge className={`${defaultClasses} bg-zinc-900 text-zinc-400 border-zinc-700`}>UNREADY</Badge>;
      default:
        return <Badge className={`${defaultClasses} bg-zinc-900 text-zinc-400 border-zinc-700`}>{status || 'UNKNOWN'}</Badge>;
    }
  };

  const formatDate = (dateStr?: string | null) => {
    if (!dateStr) return 'N/A';
    try {
      const d = new Date(dateStr);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) + ' ' + d.toLocaleDateString([], { month: 'short', day: 'numeric' });
    } catch {
      return dateStr;
    }
  };

  // Filter issues based on UI controls
  const prdIssues = issues.filter(i => i.kind === 'prd');
  const topologyNodes = useMemo(() => {
    const nodes: PipelineNode[] = [];
    if (selectedPrdScope === 'all') {
      prdIssues.forEach(prd => {
        if (prd.children) {
          nodes.push(...prd.children.map(c => ({
            number: c.number,
            status: c.status,
            blocked_by: c.blocked_by,
            active_blockers: c.active_blockers
          })));
        }
      });
    } else {
      const prd = prdIssues.find(i => i.number === selectedPrdScope);
      if (prd && prd.children) {
        nodes.push(...prd.children.map(c => ({
          number: c.number,
          status: c.status,
          blocked_by: c.blocked_by,
          active_blockers: c.active_blockers
        })));
      }
    }
    return nodes;
  }, [selectedPrdScope, prdIssues]);
  const filteredPrds = prdIssues.filter(prd => {
    const matchesSearch = prd.title.toLowerCase().includes(searchTerm.toLowerCase()) || 
                          prd.number.toString().includes(searchTerm);
    if (!matchesSearch) return false;

    if (filterStatus === 'all') return true;
    
    // Check if any child matches the filter status
    const children = prd.children || [];
    return children.some(c => c.status === filterStatus);
  });

  const getActiveRunsCount = () => runs.filter(r => r.status === 'running').length;
  const getFailedRunsCount = () => runs.filter(r => r.status === 'failed').length;
  const getReadyIssuesCount = () => issues.filter(i => i.kind === 'implementation' && i.status === 'ready').length;

  const currentRepo = repos.find(r => r.name === selectedRepo);
  const capacity = currentRepo?.global_concurrency || 0;
  const activeRunsCount = getActiveRunsCount();
  const capacityUtilization = capacity > 0 ? Math.round((activeRunsCount / capacity) * 100) : 0;

  return (
    <div className="dashboard-shell relative min-h-screen text-foreground flex antialiased">
      {/* Premium Collapsible Left Sidebar */}
      <Sidebar 
        repos={repos}
        selectedRepo={selectedRepo}
        setSelectedRepo={setSelectedRepo}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        isCollapsed={isCollapsed}
        setIsCollapsed={setIsCollapsed}
      />

      {/* Main Panel Content Area */}
      <div className="flex-1 flex flex-col min-h-screen min-w-0 overflow-y-auto bg-background">
        {/* Top Banner Status Bar & Connection Alerts */}
        <Header 
          isCollapsed={isCollapsed}
          setIsCollapsed={setIsCollapsed}
          activeTab={activeTab}
          refreshing={refreshing}
          pollingActive={pollingActive}
          setPollingActive={setPollingActive}
          fetchData={fetchData}
          error={error}
          onRetryConnection={() => { fetchRepos(); if(selectedRepo) fetchData(true); }}
          theme={theme}
          toggleTheme={toggleTheme}
        />

        {/* Premium Grid of Stat Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 px-6 pt-6 select-none animate-fade-in shrink-0">
          {/* Card 1: Active Runs */}
          <Card className="dashboard-glass-panel border border-zinc-200 dark:border-zinc-800 bg-white/85 dark:bg-[#0d0d0f]/85 flex flex-col justify-between shadow-[0_4px_20px_rgba(0,0,0,0.05)] dark:shadow-[0_4px_20px_rgba(0,0,0,0.4)]">
            <CardHeader className="py-3 px-4 flex flex-row items-center justify-between">
              <div className="flex items-center gap-2">
                <Activity className="size-4 text-amber-500 shrink-0" />
                <CardTitle className="text-xs font-bold uppercase tracking-wider text-zinc-700 dark:text-zinc-200">Active Runs</CardTitle>
              </div>
              <CardAction>
                <Badge variant="outline" className="font-mono text-[9px] text-zinc-500 dark:text-zinc-400 bg-zinc-50 dark:bg-zinc-950 border-zinc-200 dark:border-zinc-800 px-1.5 py-0">
                  {capacityUtilization}% util
                </Badge>
              </CardAction>
            </CardHeader>
            <CardContent className="px-4 pb-4.5 pt-1">
              <div className="flex items-baseline gap-1.5">
                <span className="text-3xl font-bold font-mono tracking-tight text-zinc-900 dark:text-white">{activeRunsCount}</span>
                <span className="text-xs font-mono text-zinc-555 dark:text-zinc-500">/ {capacity} capacity</span>
              </div>
              <CardDescription className="text-[10px] text-zinc-500 mt-2 font-sans">
                Active runner execution slots currently occupied
              </CardDescription>
            </CardContent>
          </Card>

          {/* Card 2: Ready Issues */}
          <Card className="dashboard-glass-panel border border-zinc-200 dark:border-zinc-800 bg-white/85 dark:bg-[#0d0d0f]/85 flex flex-col justify-between shadow-[0_4px_20px_rgba(0,0,0,0.05)] dark:shadow-[0_4px_20px_rgba(0,0,0,0.4)]">
            <CardHeader className="py-3 px-4 flex flex-row items-center justify-between">
              <div className="flex items-center gap-2">
                <Layers className="size-4 text-blue-500 shrink-0" />
                <CardTitle className="text-xs font-bold uppercase tracking-wider text-zinc-700 dark:text-zinc-200">Ready Issues</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="px-4 pb-4.5 pt-1">
              <div className="text-3xl font-bold font-mono tracking-tight text-zinc-900 dark:text-white">
                {getReadyIssuesCount()}
              </div>
              <CardDescription className="text-[10px] text-zinc-500 mt-2 font-sans">
                Eligible ready implementation issues awaiting claims
              </CardDescription>
            </CardContent>
          </Card>

          {/* Card 3: Failed Runs */}
          <Card className="dashboard-glass-panel border border-red-200 dark:border-[#ff0000]/15 bg-white/85 dark:bg-[#0d0d0f]/85 flex flex-col justify-between shadow-[0_4px_20px_rgba(0,0,0,0.05)] dark:shadow-[0_4px_20px_rgba(0,0,0,0.4)]">
            <CardHeader className="py-3 px-4 flex flex-row items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertCircle className="size-4 text-red-500 shrink-0" />
                <CardTitle className="text-xs font-bold uppercase tracking-wider text-zinc-700 dark:text-zinc-200">Failed Runs</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="px-4 pb-4.5 pt-1">
              <div className={`text-3xl font-bold font-mono tracking-tight ${getFailedRunsCount() > 0 ? 'text-red-500 dark:text-red-400 animate-pulse' : 'text-zinc-900 dark:text-white'}`}>
                {getFailedRunsCount()}
              </div>
              <CardDescription className="text-[10px] text-zinc-500 mt-2 font-sans">
                Failed agent runs requiring manual intervention
              </CardDescription>
            </CardContent>
          </Card>

          {/* Card 4: Registered Repos */}
          <Card className="dashboard-glass-panel border border-zinc-200 dark:border-zinc-800 bg-white/85 dark:bg-[#0d0d0f]/85 flex flex-col justify-between shadow-[0_4px_20px_rgba(0,0,0,0.05)] dark:shadow-[0_4px_20px_rgba(0,0,0,0.4)]">
            <CardHeader className="py-3 px-4 flex flex-row items-center justify-between">
              <div className="flex items-center gap-2">
                <Database className="size-4 text-emerald-500 shrink-0" />
                <CardTitle className="text-xs font-bold uppercase tracking-wider text-zinc-700 dark:text-zinc-200">Registered Repos</CardTitle>
              </div>
              <CardAction>
                <div className="flex items-center gap-1.5">
                  <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse shrink-0"></span>
                  <span className="text-[9px] font-mono text-emerald-600 dark:text-emerald-450 uppercase tracking-wider font-semibold">Active</span>
                </div>
              </CardAction>
            </CardHeader>
            <CardContent className="px-4 pb-4.5 pt-1">
              <div className="text-3xl font-bold font-mono tracking-tight text-zinc-900 dark:text-white">
                {repos.length}
              </div>
              <CardDescription className="text-[10px] text-zinc-500 mt-2 font-sans">
                Total connected codebases and workspaces
              </CardDescription>
            </CardContent>
          </Card>
        </div>

      {/* Main Content Layout */}
      {activeTab === 'readiness' ? (
        selectedRepo ? (
          <SchedulingReadinessPanel 
            repoName={selectedRepo} 
            apiBase={API_BASE} 
            onIssueClick={(issueNumber) => {
              let found = issues.find(i => i.number === issueNumber);
              if (!found) {
                for (const prd of issues) {
                  if (prd.children) {
                    const child = prd.children.find(c => c.number === issueNumber);
                    if (child) {
                      found = child;
                      break;
                    }
                  }
                }
              }
              if (found) {
                setDrawerIssue(found);
                setDrawerReadOnly(true);
                setDrawerOpen(true);
              }
            }}
          />
        ) : (
          <div className="grow p-6 flex items-center justify-center">
            <div className="flex flex-col gap-2 w-full max-w-md">
              <Skeleton className="h-4 w-full animate-shimmer" />
              <Skeleton className="h-4 w-5/6 animate-shimmer" />
              <Skeleton className="h-4 w-4/5 animate-shimmer" />
              <Skeleton className="h-4 w-2/3 animate-shimmer" />
            </div>
          </div>
        )
      ) : (
        <main className="grow p-6 grid grid-cols-1 xl:grid-cols-3 gap-6 overflow-hidden">
        
        {/* LEFT COLUMN: RUNS & LOCAL LOGS */}
        <section className="xl:col-span-1 flex flex-col gap-6 h-full min-h-[500px]">
          
          {/* Agent Runs List Panel */}
          <Card className="dashboard-glass-panel flex flex-col grow shrink overflow-hidden max-h-[380px]">
            <CardHeader className="py-3.5 border-b border-zinc-800 px-4 flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-xs tracking-wider font-bold uppercase text-white flex items-center gap-2">
                  <Layers className="size-3.5 text-zinc-500" />
                  Recent Agent Runs
                </CardTitle>
                <CardDescription className="text-[10px] text-zinc-500">Agent execution history</CardDescription>
              </div>
              <Badge variant="outline" className="font-mono text-[9px] border-zinc-800 text-zinc-400">
                {runs.length} Runs
              </Badge>
            </CardHeader>
            <CardContent className="p-0 grow overflow-hidden">
              {loading ? (
                <div className="h-full flex items-center justify-center p-6">
                  <div className="flex flex-col gap-2 w-full max-w-[200px]">
                    <Skeleton className="h-3 w-full animate-shimmer" />
                    <Skeleton className="h-3 w-5/6 animate-shimmer" />
                    <Skeleton className="h-3 w-2/3 animate-shimmer" />
                  </div>
                </div>
              ) : runs.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center p-8 text-center">
                  <Server className="size-6 text-zinc-700 mb-2" />
                  <p className="text-xs text-zinc-500">No active worktrees or runs registered</p>
                  <p className="text-[9px] text-zinc-600 mt-1 max-w-[200px]">Runs are initialized when implementation issues are claimed.</p>
                </div>
              ) : (
                <ScrollArea className="h-[280px]">
                  <div className="divide-y divide-zinc-900">
                    {[...runs].reverse().map((run) => {
                      const isSelected = selectedRunIssue === run.issue_number;
                      return (
                        <div 
                          key={run.issue_number}
                          onClick={() => setSelectedRunIssue(isSelected ? null : run.issue_number)}
                          role="button"
                          tabIndex={0}
                          aria-pressed={isSelected}
                          aria-label={`${isSelected ? 'Hide' : 'Show'} log for Agent Run issue #${run.issue_number}`}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault();
                              setSelectedRunIssue(isSelected ? null : run.issue_number);
                            }
                          }}
                          className={`dashboard-row p-3 font-mono cursor-pointer flex flex-col gap-2 ${
                            isSelected 
                              ? 'bg-zinc-900/80 border-l-2 border-teal-300'
                              : 'bg-transparent border-l-2 border-transparent'
                          }`}
                        >
                          <div className="flex items-start justify-between">
                            <span className="text-xs font-bold text-white">
                              ISSUE #{run.issue_number}
                            </span>
                            {getStatusBadge(run.status)}
                          </div>
                          
                          <div className="flex items-center gap-1.5 text-[10px] text-zinc-500">
                            <GitBranch className="size-3 shrink-0 text-zinc-600" />
                            <span className="truncate max-w-[240px]" title={run.implementation_branch}>
                              {run.implementation_branch}
                            </span>
                          </div>

                          <div className="flex items-center justify-between text-[9px] text-zinc-500">
                            <div className="flex items-center gap-1">
                              <Clock className="size-2.5 text-zinc-600" />
                              <span>{formatDate(run.started_at)}</span>
                            </div>
                            {run.finished_at && (
                              <span className="text-zinc-600">
                                elapsed: {Math.round((new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000)}s
                              </span>
                            )}
                          </div>

                          {run.failure_reason && (
                            <div className="bg-red-950/20 border border-red-950 rounded p-1.5 text-[9.5px] text-red-400 font-mono mt-1 whitespace-pre-wrap max-h-16 overflow-y-auto">
                              <strong>Fail Reason:</strong> {run.failure_reason}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>

          {/* Local Log Tails Console */}
          <Card className="dashboard-glass-panel flex flex-col grow shrink overflow-hidden min-h-[220px]">
            <CardHeader className="py-2.5 border-b border-zinc-800/80 px-4 flex flex-row items-center justify-between bg-black select-none gap-4">
              <div className="flex items-center gap-3">
                {/* macOS Window Controls */}
                <div className="flex items-center gap-1.5 mr-1">
                  <span className="size-2.5 rounded-full bg-[#ef4444]/90 hover:bg-[#ef4444] transition-colors cursor-pointer" title="Close" />
                  <span className="size-2.5 rounded-full bg-[#f59e0b]/90 hover:bg-[#f59e0b] transition-colors cursor-pointer" title="Minimize" />
                  <span className="size-2.5 rounded-full bg-[#10b981]/90 hover:bg-[#10b981] transition-colors cursor-pointer" title="Maximize" />
                </div>
                
                <span className="text-zinc-850 font-mono text-sm">/</span>

                {/* Tab Container */}
                <div className="flex items-center gap-2 bg-black border border-zinc-900 px-3 py-1 rounded text-[11px] font-mono text-zinc-300 shadow-inner">
                  <Terminal className="size-3.5 text-emerald-400" />
                  <span className="font-semibold tracking-tight">harness.log</span>
                  {selectedRunIssue && (
                    <span className="text-[9px] bg-emerald-950/60 border border-emerald-900/60 text-emerald-400 px-1 rounded-sm uppercase font-bold">
                      #{selectedRunIssue}
                    </span>
                  )}
                </div>

                {/* Status / Description */}
                <span className="hidden md:inline text-[10px] text-zinc-500 font-mono font-medium tracking-tight">
                  {selectedRunIssue ? `Tailing active runner for Issue #${selectedRunIssue}` : 'Idle — No active run selected'}
                </span>
              </div>
              {selectedRunIssue !== null && (
                <div className="flex items-center gap-2 text-[10px] font-mono">
                  {/* Log search */}
                  <input
                    type="text"
                    placeholder="Search log…"
                    aria-label="Search log content"
                    value={logSearchQuery}
                    onChange={(e) => setLogSearchQuery(e.target.value)}
                    className="dashboard-control w-[120px] text-zinc-300 rounded px-1.5 py-0.5 focus:outline-none placeholder-zinc-700 text-[10px]"
                  />

                  <span className="text-zinc-800">|</span>

                  {/* Lines Limit */}
                  <select 
                    aria-label="Log tail limit"
                    value={logsLimit} 
                    onChange={(e) => setLogsLimit(Number(e.target.value))}
                    className="dashboard-control text-zinc-400 rounded px-1.5 py-0.5 focus:outline-none"
                  >
                    <option value={20}>20 lines</option>
                    <option value={50}>50 lines</option>
                    <option value={100}>100 lines</option>
                    <option value={300}>300 lines</option>
                  </select>

                  <span className="text-zinc-800">|</span>

                  {/* Polling Switch */}
                  <button
                    onClick={() => setPollLogsActive(!pollLogsActive)}
                    className={`dashboard-control px-1.5 py-0.5 rounded border font-semibold tracking-wider text-[9px] flex items-center gap-1.5 ${
                      pollLogsActive 
                        ? 'bg-emerald-950/40 text-emerald-400 border-emerald-900' 
                        : 'bg-black text-zinc-500'
                    }`}
                  >
                    {pollLogsActive && (
                      <span
                        title="Streaming active"
                        className="stream-indicator"
                        aria-label="Streaming active"
                      />
                    )}
                    {pollLogsActive ? 'STREAM ON' : 'STREAM OFF'}
                  </button>

                  {logTail && (
                    <Button
                      type="button"
                      size="icon-xs"
                      variant="outline"
                      onClick={exportLoadedLogTail}
                      aria-label={`Export loaded tail for Implementation Issue #${logTail.issue_number}`}
                      title="Export loaded tail"
                      className="dashboard-control text-zinc-400 hover:text-white"
                    >
                      <Download data-icon="inline-start" />
                    </Button>
                  )}
                </div>
              )}
            </CardHeader>
            <CardContent className="p-0 grow bg-black flex flex-col font-mono overflow-hidden">
              {selectedRunIssue === null ? (
                <div className="grow flex flex-col items-center justify-center p-6 text-zinc-600 text-center font-mono">
                  <Terminal className="size-8 text-zinc-800 mb-2" />
                  <p className="text-xs">Console is offline.</p>
                  <p className="text-[9px] text-zinc-700 mt-1">Pick a claimed/active run from the list to display active logs.</p>
                </div>
              ) : !logTail ? (
                <div className="grow flex items-center justify-center p-6">
                  <div className="flex flex-col gap-2 w-full max-w-[180px]">
                    <Skeleton className="h-3 w-full animate-shimmer" />
                    <Skeleton className="h-3 w-3/4 animate-shimmer" />
                  </div>
                </div>
              ) : (
                <div className="grow flex flex-col overflow-hidden text-[10px]">
                  <div className="bg-black px-4 py-1.5 border-b border-zinc-900 text-zinc-500 text-[9px] flex items-center justify-between shrink-0 font-mono">
                    <span className="truncate pr-4">PATH: {logTail.log_path}</span>
                    <span className="shrink-0">{logTail.lines_returned} lines</span>
                  </div>
                  
                  <div
                    ref={terminalViewportRef}
                    role="log"
                    aria-label={`Issue #${logTail.issue_number} harness log tail`}
                    aria-live="polite"
                    onScroll={handleLogScroll}
                    className="terminal-scrollbar dashboard-focus relative grow p-4 bg-black overflow-y-auto"
                  >
                    <div className="space-y-1 font-mono text-zinc-300 whitespace-pre-wrap leading-relaxed select-text">
                      {logTail.content ? (
                        logTail.content.split('\n').map((line, idx) => (
                          <div key={idx} className="table-row">
                            <span className="table-cell text-muted-foreground/30 select-none pr-3 text-right w-8 font-mono">{idx + 1}</span>
                            <span className="table-cell text-[#f4f4f5]">{highlightMatches(line, logSearchQuery)}</span>
                          </div>
                        ))
                      ) : (
                        <div className="text-zinc-600 text-center py-4">
                          Log is empty. No outputs written by harness.
                        </div>
                      )}
                    </div>
                    {hasNewPausedLogOutput && (
                      <Button
                        type="button"
                        size="xs"
                        variant="outline"
                        onClick={jumpToLatestLogOutput}
                        aria-label="Jump to latest log output"
                        className="dashboard-control sticky bottom-2 ml-auto text-zinc-100 font-mono text-[9px] uppercase tracking-wider"
                      >
                        <ArrowDown data-icon="inline-start" />
                        Latest output
                      </Button>
                    )}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </section>

        {/* RIGHT COLUMN: PRDS & CHILD IMPLEMENTATION ISSUES */}
        <section className="xl:col-span-2 flex flex-col gap-6 h-full overflow-hidden">
          {/* Central Topology Card: System Dependency Topology */}
          <Card className="dashboard-glass-panel border border-zinc-800 bg-[#0d0d0f]/85 flex flex-col shadow-[0_4px_20px_rgba(0,0,0,0.4)] overflow-hidden shrink-0">
            <CardHeader className="py-4 border-b border-zinc-800 px-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4 select-none">
              <div>
                <CardTitle className="text-xs tracking-wider font-bold uppercase text-white flex items-center gap-2">
                  <GitMerge className="size-3.5 text-emerald-400 rotate-90" />
                  System Dependency Topology
                </CardTitle>
                <CardDescription className="text-[10px] text-zinc-500">
                  Interactive sorted execution dependency pipeline map
                </CardDescription>
              </div>

              {/* PRD Scope Filters (matching time filters in design.png) */}
              <div className="flex flex-wrap items-center gap-1.5 bg-black/40 p-1 rounded-lg border border-zinc-800/80">
                <button
                  onClick={() => setSelectedPrdScope('all')}
                  className={`px-3 py-1 rounded-md text-[10px] font-mono font-bold tracking-wider transition-all uppercase cursor-pointer ${
                    selectedPrdScope === 'all'
                      ? 'bg-zinc-800 text-white shadow-sm border border-zinc-700'
                      : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/40 border border-transparent'
                  }`}
                >
                  All
                </button>
                {prdIssues.map(prd => (
                  <button
                    key={prd.number}
                    onClick={() => setSelectedPrdScope(prd.number)}
                    className={`px-3 py-1 rounded-md text-[10px] font-mono font-bold tracking-wider transition-all uppercase cursor-pointer ${
                      selectedPrdScope === prd.number
                        ? 'bg-zinc-800 text-white shadow-sm border border-zinc-700'
                        : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/40 border border-transparent'
                    }`}
                  >
                    PRD #{prd.number}
                  </button>
                ))}
              </div>
            </CardHeader>
            <CardContent className="px-6 py-4 flex flex-col justify-center min-h-[110px]">
              {loading ? (
                <div className="h-[80px] flex items-center justify-center">
                  <Skeleton className="h-3 w-full max-w-[200px] animate-shimmer" />
                </div>
              ) : topologyNodes.length === 0 ? (
                <div className="h-[80px] flex flex-col items-center justify-center text-center font-mono">
                  <GitMerge className="size-6 text-zinc-800 mb-1" />
                  <p className="text-[10px] text-zinc-500">No active dependency nodes observed in this scope</p>
                </div>
              ) : (
                <DependencyPipeline children={topologyNodes} />
              )}
            </CardContent>
          </Card>

          <Card className="dashboard-glass-panel flex flex-col grow h-full overflow-hidden">
            {/* Header Controls for filtering */}
            <CardHeader className="py-4 border-b border-zinc-800 px-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <CardTitle className="text-sm text-white flex items-center gap-2 uppercase tracking-wider">
                  <Database className="size-4 text-zinc-500" />
                  Product Roadmap & Implementation Lifecycle
                </CardTitle>
                <CardDescription className="text-xs text-zinc-500">
                  PRD issues hierarchy derived from GitHub Issues state
                </CardDescription>
              </div>

              {/* Filtering / Search Controls */}
              <div className="flex items-center gap-2 text-xs">
                {/* Search */}
                <input 
                  type="text" 
                  placeholder="SEARCH ISSUE..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="dashboard-control text-zinc-300 rounded px-2.5 py-1.5 focus:outline-none placeholder-zinc-700 w-[140px] text-xs"
                />

                {/* Filter */}
                <div className="dashboard-control flex items-center gap-1.5 border rounded px-2 py-1">
                  <ListFilter className="size-3 text-zinc-500" />
                  <select
                    value={filterStatus}
                    onChange={(e) => setFilterStatus(e.target.value)}
                    className="dashboard-focus bg-transparent text-zinc-300 focus:outline-none cursor-pointer text-xs font-semibold pr-1 rounded"
                  >
                    <option value="all" className="bg-[#09090b]">ALL STATUS</option>
                    <option value="ready" className="bg-[#09090b]">READY</option>
                    <option value="claimed" className="bg-[#09090b]">CLAIMED</option>
                    <option value="running" className="bg-[#09090b]">RUNNING</option>
                    <option value="succeeded" className="bg-[#09090b]">SUCCEEDED</option>
                    <option value="failed" className="bg-[#09090b]">FAILED</option>
                    <option value="blocked" className="bg-[#09090b]">BLOCKED</option>
                    <option value="unready" className="bg-[#09090b]">UNREADY</option>
                  </select>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-0 grow overflow-hidden">
              {loading ? (
                <div className="h-full flex items-center justify-center p-8">
                  <div className="flex flex-col gap-2 w-full max-w-[220px]">
                    <Skeleton className="h-3 w-full animate-shimmer" />
                    <Skeleton className="h-3 w-5/6 animate-shimmer" />
                    <Skeleton className="h-3 w-4/5 animate-shimmer" />
                    <Skeleton className="h-3 w-2/3 animate-shimmer" />
                  </div>
                </div>
              ) : filteredPrds.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center p-12 text-center">
                  <FileText className="size-8 text-zinc-700 mb-2" />
                  <p className="text-xs text-zinc-500">No PRD Issues found matching search criteria</p>
                  <p className="text-[10px] text-zinc-600 mt-1 max-w-[340px]">
                    Configure issue gateways and ensure issues carry labels such as 'prd' or 'implementation'.
                  </p>
                </div>
              ) : (
                <ScrollArea className="h-[600px] px-6 py-4">
                  <div className="space-y-6">
                    {filteredPrds.map((prd) => {
                      const isExpanded = expandedPrds[prd.number];
                      const children = prd.children || [];
                      const canPreparePrd = prd.state === 'open' && !prd.prd_branch;
                      const prepareState = preparePrdState[prd.number];
                      const isPreparingPrd = prepareState?.status === 'loading';
                      
                      return (
                        <div 
                          key={prd.number}
                          className="dashboard-glass-surface border rounded overflow-hidden transition-all duration-200 hover:border-zinc-600"
                        >
                          {/* PRD Main Bar */}
                          <div 
                            onClick={() => togglePrdExpand(prd.number)}
                            className="dashboard-row bg-[#0d0d0f]/80 px-4 py-3.5 cursor-pointer flex items-center justify-between border-b border-zinc-800 transition"
                          >
                            <div className="flex items-center gap-3">
                              <span className="font-mono text-xs font-extrabold text-zinc-400 bg-zinc-900 border border-zinc-800 px-1.5 py-0.5 rounded">
                                PRD #{prd.number}
                              </span>
                              <div>
                                <h3
                                  className="text-xs font-bold text-white tracking-wide leading-none mb-1.5 cursor-pointer hover:text-teal-400 transition-colors"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    setDrawerIssue(prd);
                                    setDrawerReadOnly(false);
                                    setDrawerOpen(true);
                                  }}
                                >
                                  {prd.title}
                                </h3>
                                {prd.prd_branch && (
                                  <div className="flex items-center gap-1 text-[9px] text-zinc-500 font-mono">
                                    <GitBranch className="size-2.5 text-zinc-600" />
                                    <span>BRANCH: {prd.prd_branch}</span>
                                  </div>
                                )}
                              </div>
                            </div>
                            
                            <div className="flex items-center gap-4">
                              {canPreparePrd && (
                                <Button
                                  type="button"
                                  size="xs"
                                  variant="outline"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    preparePrdIssue(prd.number);
                                  }}
                                  disabled={isPreparingPrd}
                                  className="dashboard-control text-[9px] uppercase tracking-wider text-zinc-200"
                                >
                                  <GitBranch data-icon="inline-start" className={isPreparingPrd ? 'animate-pulse' : ''} />
                                  {isPreparingPrd ? 'Preparing' : 'Prepare'} PRD #{prd.number}
                                </Button>
                              )}
                              <Badge variant="outline" className="font-mono text-[9px] border-zinc-800 text-zinc-500 bg-zinc-900 px-2 py-0.5">
                                {children.length} Slices
                              </Badge>
                              {isExpanded ? (
                                <ChevronDown className="size-4 text-zinc-500" />
                              ) : (
                                <ChevronRight className="size-4 text-zinc-500" />
                              )}
                            </div>
                          </div>

                          {prepareState && prepareState.status !== 'loading' && (
                            <div
                              className={`px-4 py-2 border-b text-[10px] font-mono ${
                                prepareState.status === 'succeeded'
                                  ? 'bg-emerald-950/20 border-emerald-950/60 text-emerald-300'
                                  : 'bg-red-950/25 border-red-950/70 text-red-300'
                              }`}
                              role={prepareState.status === 'failed' ? 'alert' : 'status'}
                            >
                              {prepareState.message}
                            </div>
                          )}

                          {/* Dependency Pipeline Map */}
                          {isExpanded && children.length > 0 && (
                            <DependencyPipeline children={children} />
                          )}

                          {/* PRD Children (Implementation Issues) */}
                          {isExpanded && (
                            <div className="p-4 bg-[#050506] divide-y divide-zinc-900">
                              {children.length === 0 ? (
                                <div className="text-center py-4 text-[10px] text-zinc-600">
                                  No implementation issue slices declared for this PRD.
                                </div>
                              ) : (
                                children.map((c) => {
                                  const isSelectedLog = selectedRunIssue === c.number;
                                  const canClaimIssue = c.state !== 'closed' && c.status === 'ready';
                                  const isClaimFormOpen = claimFormIssue === c.number;
                                  const claimAgentRunId = claimAgentRunIds[c.number] || '';
                                  const claimState = claimIssueState[c.number];
                                  const isClaimingIssue = claimState?.status === 'loading';
                                  const canIntegrateIssue = c.state !== 'closed' && c.status === 'succeeded';
                                  const integrateState = integrateIssueState[c.number];
                                  const isIntegratingIssue = integrateState?.status === 'loading';
                                  const canStartIssue = c.state !== 'closed' && c.status === 'claimed';
                                  const startState = startIssueState[c.number];
                                  const isStartingIssue = startState?.status === 'loading';

                                  return (
                                    <div 
                                      key={c.number}
                                      className={`dashboard-row py-3.5 flex flex-col md:flex-row md:items-start justify-between gap-4 font-mono ${
                                        isSelectedLog ? 'bg-zinc-900/40 px-2 -mx-2 rounded border border-zinc-800' : ''
                                      }`}
                                    >
                                      {/* Issue Title / Kind */}
                                      <div className="flex items-start gap-2.5 grow">
                                        <CornerDownRight className="size-4 text-zinc-700 shrink-0 mt-0.5" />
                                        <div className="space-y-1.5 max-w-[480px]">
                                          <div className="flex flex-wrap items-center gap-2">
                                            <span className="text-[10px] font-bold text-white hover:underline cursor-pointer">
                                              #{c.number}
                                            </span>
                                            <span
                                              className="text-[11px] text-zinc-300 font-semibold leading-tight font-sans cursor-pointer hover:text-teal-400 transition-colors"
                                              onClick={() => {
                                                setDrawerIssue(c);
                                                setDrawerReadOnly(false);
                                                setDrawerOpen(true);
                                              }}
                                            >
                                              {c.title}
                                            </span>
                                          </div>
                                          
                                          {/* Branch & Dates */}
                                          <div className="flex flex-col gap-1 text-[9.5px] text-zinc-500">
                                            {c.implementation_branch && (
                                              <span className="flex items-center gap-1.5">
                                                <GitBranch className="size-3 text-zinc-700 shrink-0" />
                                                <span className="truncate max-w-[380px] text-zinc-400">
                                                  {c.implementation_branch}
                                                </span>
                                              </span>
                                            )}
                                            
                                            {c.started_at && (
                                              <span className="flex items-center gap-1.5">
                                                <Clock className="size-3 text-zinc-700 shrink-0" />
                                                <span>
                                                  Started: {formatDate(c.started_at)}
                                                  {c.finished_at && ` | Done: ${formatDate(c.finished_at)}`}
                                                </span>
                                              </span>
                                            )}
                                            {c.claimed_at && (
                                              <span className="flex items-center gap-1.5">
                                                <Clock className="size-3 text-zinc-700 shrink-0" />
                                                <span>
                                                  Claimed: {formatDate(c.claimed_at)}
                                                  {c.agent_run_id && ` | ${c.agent_run_id}`}
                                                </span>
                                              </span>
                                            )}
                                          </div>

                                          {/* Blocking Dependency rail */}
                                          {c.blocked_by && c.blocked_by.length > 0 && (
                                            <div
                                              role="group"
                                              aria-label={`Blocking Dependency rail for Implementation Issue #${c.number}`}
                                              className="dashboard-glass-surface flex flex-wrap items-center gap-2 rounded border px-2 py-1.5"
                                            >
                                              <span className="text-[9px] text-zinc-500 font-bold uppercase tracking-wider">
                                                Blocking Dependency
                                              </span>
                                              <div className="relative flex flex-wrap items-center gap-1.5 pl-1 before:absolute before:left-1 before:right-1 before:top-1/2 before:h-px before:-translate-y-1/2 before:bg-zinc-800">
                                                {c.blocked_by.map(num => {
                                                  const isOpenBlockingDependency = c.active_blockers?.includes(num) ?? false;

                                                  return (
                                                    <span
                                                      key={num}
                                                      aria-label={`${isOpenBlockingDependency ? 'Open' : 'Resolved'} Blocking Dependency #${num}`}
                                                      className={`relative z-10 inline-flex h-5 items-center gap-1 rounded-full border px-1.5 text-[9px] font-bold uppercase tracking-wider ${
                                                        isOpenBlockingDependency
                                                          ? 'border-orange-800 bg-orange-950/60 text-orange-300'
                                                          : 'border-zinc-800 bg-[#050506] text-zinc-600'
                                                      }`}
                                                    >
                                                      {isOpenBlockingDependency ? (
                                                        <AlertCircle className="size-2.5" aria-hidden="true" />
                                                      ) : (
                                                        <CheckCircle2 className="size-2.5" aria-hidden="true" />
                                                      )}
                                                      <span>{isOpenBlockingDependency ? 'Open' : 'Resolved'} #{num}</span>
                                                    </span>
                                                  );
                                                })}
                                              </div>
                                            </div>
                                          )}

                                          {integrateState && integrateState.status !== 'loading' && (
                                            <div
                                              className={`rounded border px-2 py-1 text-[9.5px] font-mono ${
                                                integrateState.status === 'succeeded'
                                                  ? 'bg-emerald-950/20 border-emerald-950/60 text-emerald-300'
                                                  : 'bg-red-950/25 border-red-950/70 text-red-300'
                                              }`}
                                              role={integrateState.status === 'failed' ? 'alert' : 'status'}
                                            >
                                              {integrateState.message}
                                            </div>
                                          )}

                                          {startState && startState.status !== 'loading' && (
                                            <div
                                              className={`rounded border px-2 py-1 text-[9.5px] font-mono ${
                                                startState.status === 'succeeded'
                                                  ? 'bg-emerald-950/20 border-emerald-950/60 text-emerald-300'
                                                  : 'bg-red-950/25 border-red-950/70 text-red-300'
                                              }`}
                                              role={startState.status === 'failed' ? 'alert' : 'status'}
                                            >
                                              {startState.message}
                                            </div>
                                          )}

                                          {isClaimFormOpen && (
                                            <form
                                              className="rounded border border-zinc-900 bg-zinc-950/70 px-2 py-2 flex flex-col gap-2"
                                              aria-label={`Claim Implementation Issue #${c.number}`}
                                              onSubmit={(event) => {
                                                event.preventDefault();
                                                claimImplementationIssue(c.number);
                                              }}
                                            >
                                              <label
                                                htmlFor={`claim-agent-run-${c.number}`}
                                                className="text-[9px] text-zinc-500 font-bold uppercase tracking-wider"
                                              >
                                                Agent Run identifier for Implementation Issue #{c.number}
                                              </label>
                                              <div className="flex flex-col sm:flex-row gap-2">
                                                <input
                                                  id={`claim-agent-run-${c.number}`}
                                                  value={claimAgentRunId}
                                                  disabled={isClaimingIssue}
                                                  onChange={(event) => setClaimAgentRunIds(prev => ({
                                                    ...prev,
                                                    [c.number]: event.target.value
                                                  }))}
                                                  className="dashboard-control min-w-0 w-full sm:w-[260px] rounded px-2 py-1 text-[10px] text-zinc-200 focus:outline-none font-mono"
                                                />
                                                <Button
                                                  type="submit"
                                                  size="xs"
                                                  variant="outline"
                                                  aria-label={
                                                    isClaimingIssue
                                                      ? `Claiming #${c.number}`
                                                      : `Submit claim for Implementation Issue #${c.number}`
                                                  }
                                                  disabled={isClaimingIssue}
                                                  className="dashboard-control text-[9px] uppercase tracking-wider text-zinc-200"
                                                >
                                                  <Send data-icon="inline-start" className={isClaimingIssue ? 'animate-pulse' : ''} />
                                                  {isClaimingIssue ? 'Claiming' : 'Submit'} #{c.number}
                                                </Button>
                                              </div>
                                            </form>
                                          )}

                                          {claimState && claimState.status !== 'loading' && (
                                            <div
                                              className={`rounded border px-2 py-1 text-[9.5px] font-mono ${
                                                claimState.status === 'succeeded'
                                                  ? 'bg-emerald-950/20 border-emerald-950/60 text-emerald-300'
                                                  : 'bg-red-950/25 border-red-950/70 text-red-300'
                                              }`}
                                              role={claimState.status === 'failed' ? 'alert' : 'status'}
                                            >
                                              {claimState.message}
                                            </div>
                                          )}
                                        </div>
                                      </div>

                                      {/* Status / Actions */}
                                      <div className="flex flex-row md:flex-col items-center md:items-end justify-between md:justify-start gap-2 shrink-0 self-center md:self-start">
                                        {getStatusBadge(c.status)}

                                        {/* Action: Open logs */}
                                        {(c.status === 'running' || c.status === 'succeeded' || c.status === 'failed') && (
                                          <button
                                            onClick={() => setSelectedRunIssue(isSelectedLog ? null : c.number)}
                                            className="dashboard-control text-[9.5px] uppercase font-bold tracking-wider px-2 py-0.5 rounded flex items-center gap-1"
                                          >
                                            {isSelectedLog ? (
                                              <>
                                                <EyeOff className="size-3 text-zinc-500" />
                                                Hide Log
                                              </>
                                            ) : (
                                              <>
                                                <Eye className="size-3 text-emerald-400" />
                                                View Log
                                              </>
                                            )}
                                          </button>
                                        )}

                                        {canIntegrateIssue && (
                                          <Button
                                            type="button"
                                            size="xs"
                                            variant="outline"
                                            onClick={() => integrateImplementationIssue(c.number)}
                                            disabled={isIntegratingIssue}
                                            className="dashboard-control text-[9px] uppercase tracking-wider text-zinc-200"
                                          >
                                            <GitMerge data-icon="inline-start" className={isIntegratingIssue ? 'animate-pulse' : ''} />
                                            {isIntegratingIssue ? 'Integrating' : 'Integrate'} #{c.number}
                                          </Button>
                                        )}

                                        {canStartIssue && (
                                          <Button
                                            type="button"
                                            size="xs"
                                            variant="outline"
                                            aria-label={
                                              isStartingIssue
                                                ? `Starting Agent Run for Implementation Issue #${c.number}`
                                                : `Start Agent Run for Implementation Issue #${c.number}`
                                            }
                                            onClick={() => startImplementationIssue(c.number)}
                                            disabled={isStartingIssue}
                                            className="dashboard-control text-[9px] uppercase tracking-wider text-zinc-200"
                                          >
                                            <Play data-icon="inline-start" className={isStartingIssue ? 'animate-pulse' : ''} />
                                            {isStartingIssue ? 'Starting' : 'Start'} #{c.number}
                                          </Button>
                                        )}

                                        {canClaimIssue && (
                                          <Button
                                            type="button"
                                            size="xs"
                                            variant="outline"
                                            onClick={() => openClaimForm(c.number)}
                                            className="dashboard-control text-[9px] uppercase tracking-wider text-zinc-200"
                                          >
                                            <Hand data-icon="inline-start" />
                                            Claim #{c.number}
                                          </Button>
                                        )}
                                      </div>
                                    </div>
                                  );
                                })
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>
        </section>
      </main>
      )}

      {/* Side Drawer Inspector */}
      <SideDrawer
        issue={drawerIssue}
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        readOnly={drawerReadOnly}
        onClaim={openClaimForm}
        onStart={startImplementationIssue}
        onIntegrate={integrateImplementationIssue}
        onViewLog={(num) => setSelectedRunIssue(selectedRunIssue === num ? null : num)}
        claimState={drawerIssue ? claimIssueState[drawerIssue.number] : undefined}
        startState={drawerIssue ? startIssueState[drawerIssue.number] : undefined}
        integrateState={drawerIssue ? integrateIssueState[drawerIssue.number] : undefined}
        claimAgentRunId={drawerIssue ? claimAgentRunIds[drawerIssue.number] : ''}
        onClaimAgentRunIdChange={(val) => {
          if (drawerIssue) {
            setClaimAgentRunIds(prev => ({ ...prev, [drawerIssue.number]: val }));
          }
        }}
        selectedRunIssue={selectedRunIssue}
      />

      {/* Footer Info Box */}
      <footer className="dashboard-glass-panel border-t px-6 py-3 flex items-center justify-between text-[10px] text-zinc-500 mt-auto shrink-0">
        <div className="flex items-center gap-2">
          <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
          <span>Engine Connected</span>
        </div>
        <div>
          <span>Antigravity Orchestration Scaffold v1.0.0</span>
        </div>
      </footer>
      </div>
    </div>
  )
}
