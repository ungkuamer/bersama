import { useState, useEffect, useRef, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
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
  Activity,
  BarChart3,
  Zap,
  Cpu
} from 'lucide-react'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import SideDrawer from '@/components/SideDrawer'
import { Skeleton } from '@/components/ui/skeleton'
import DependencyPipeline from '@/components/DependencyPipeline'
import SchedulingReadinessPanel from '@/components/SchedulingReadinessPanel'
import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import { useReposQuery } from '@/hooks/useReposQuery'
import { useIssuesQuery } from '@/hooks/useIssuesQuery'
import { useRunsQuery } from '@/hooks/useRunsQuery'
import { useSSE } from '@/hooks/useSSE'
import { useLogStream } from '@/hooks/useLogStream'
import { useRunMetricsQuery } from '@/hooks/useRunMetricsQuery'
import { useImplementationIssueMetricsQuery } from '@/hooks/useImplementationIssueMetricsQuery'
import { usePrdMetricsQuery } from '@/hooks/usePrdMetricsQuery'
import { formatCompactTokens, formatCompactCost, formatCompactMs, formatCompactTokensPerSec } from '@/lib/metrics'

interface ProcessGlobal {
  process?: {
    env: {
      NODE_ENV?: string;
    };
  };
}

const isTestEnv = typeof (globalThis as ProcessGlobal).process !== 'undefined' &&
                  (globalThis as ProcessGlobal).process?.env.NODE_ENV === 'test';
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

interface TelemetryDiagnosticItem {
  code: string;
  severity: string;
  message: string;
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
  telemetry_diagnostics?: TelemetryDiagnosticItem[] | null;
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

function SSEStatus({ isConnected }: { isConnected: boolean }) {
  return (
    <div className="flex items-center gap-2" aria-label={`SSE ${isConnected ? 'Live' : 'Disconnected'}`}>
      <span
        className={`size-1.5 rounded-full ${isConnected ? 'animate-pulse bg-emerald-500' : 'bg-red-500'}`}
        aria-hidden="true"
      />
      <span>{isConnected ? 'Live' : 'Disconnected'}</span>
    </div>
  );
}

export default function App() {
  const queryClient = useQueryClient();

  const [selectedRepo, setSelectedRepo] = useState<string>('');
  const [selectedRunIssue, setSelectedRunIssue] = useState<number | null>(null);
  const [logsLimit, setLogsLimit] = useState<number>(100);
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
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [drawerIssue, setDrawerIssue] = useState<Issue | null>(null);
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);
  const [drawerReadOnly, setDrawerReadOnly] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'readiness' | 'operator'>(isTestEnv ? 'operator' : 'readiness');
  const [isCollapsed, setIsCollapsed] = useState<boolean>(true);

  // Theme State
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('theme');
    if (saved === 'light' || saved === 'dark') return saved;
    return 'light';
  });

  // TanStack Query hooks
  const reposQuery = useReposQuery();
  const repos: Repo[] = reposQuery.data || [];
  const effectiveSelectedRepo = selectedRepo || (repos.length > 0 ? repos[0].name : '');

  const sseState = useSSE(effectiveSelectedRepo);
  const issuesQuery = useIssuesQuery(effectiveSelectedRepo, sseState.isPollingFallback);
  const runsQuery = useRunsQuery(effectiveSelectedRepo, sseState.isPollingFallback);
  const logStream = useLogStream({
    repo: effectiveSelectedRepo,
    issueNumber: selectedRunIssue,
    limit: logsLimit,
    latestEvent: sseState.latestMessage,
    enablePollingFallback: sseState.isPollingFallback,
  });

  // Fetch run metrics when viewing an implementation issue in the drawer
  const drawerRunIssueNumber = (drawerOpen && drawerIssue?.kind === 'implementation')
    ? drawerIssue.number
    : null;
  const runMetricsQuery = useRunMetricsQuery(effectiveSelectedRepo, drawerRunIssueNumber);

  // Fetch implementation issue aggregated metrics when viewing an implementation issue in the drawer
  const implIssueMetricsQuery = useImplementationIssueMetricsQuery(effectiveSelectedRepo, drawerRunIssueNumber);

  // Derive data from queries
  const issues: Issue[] = issuesQuery.data || [];
  const runs: RunState[] = runsQuery.data || [];
  const logTail = logStream.logTail || null;
  const loading = reposQuery.isPending || Boolean(effectiveSelectedRepo && (issuesQuery.isPending || runsQuery.isPending));
  const queryError = reposQuery.error ?? issuesQuery.error ?? runsQuery.error;
  const connectionError = queryError ? `Data fetch failed: ${messageFromError(queryError)}` : error;

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

  // Handle selected run issue changes
  useEffect(() => {
    if (previousSelectedRunIssueRef.current !== selectedRunIssue) {
      previousLogContentRef.current = null;
      setLogAutoScroll(true);
      setHasNewPausedLogOutput(false);
      previousSelectedRunIssueRef.current = selectedRunIssue;
    }
  }, [selectedRunIssue]);

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
    if (!effectiveSelectedRepo) return;

    setPreparePrdState(prev => ({
      ...prev,
      [issueNumber]: {
        status: 'loading',
        message: 'Preparing PRD Issue...'
      }
    }));

    try {
      const res = await fetch(
        `${API_BASE}/dashboard/repos/${encodeURIComponent(effectiveSelectedRepo)}/prd-issues/${issueNumber}/prepare`,
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
      queryClient.invalidateQueries({ queryKey: ['issues', effectiveSelectedRepo] });
      queryClient.invalidateQueries({ queryKey: ['runs', effectiveSelectedRepo] });
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
    if (!effectiveSelectedRepo) return;

    setIntegrateIssueState(prev => ({
      ...prev,
      [issueNumber]: {
        status: 'loading',
        message: 'Integrating Implementation Issue...'
      }
    }));

    try {
      const res = await fetch(
        `${API_BASE}/dashboard/repos/${encodeURIComponent(effectiveSelectedRepo)}/implementation-issues/${issueNumber}/integrate`,
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
      queryClient.invalidateQueries({ queryKey: ['issues', effectiveSelectedRepo] });
      queryClient.invalidateQueries({ queryKey: ['runs', effectiveSelectedRepo] });
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
    if (!effectiveSelectedRepo) return;

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
        `${API_BASE}/dashboard/repos/${encodeURIComponent(effectiveSelectedRepo)}/implementation-issues/${issueNumber}/claim`,
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
      queryClient.invalidateQueries({ queryKey: ['issues', effectiveSelectedRepo] });
      queryClient.invalidateQueries({ queryKey: ['runs', effectiveSelectedRepo] });
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
    if (!effectiveSelectedRepo) return;

    setStartIssueState(prev => ({
      ...prev,
      [issueNumber]: {
        status: 'loading',
        message: 'Starting Agent Run...'
      }
    }));

    try {
      const res = await fetch(
        `${API_BASE}/dashboard/repos/${encodeURIComponent(effectiveSelectedRepo)}/implementation-issues/${issueNumber}/start`,
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
      queryClient.invalidateQueries({ queryKey: ['issues', effectiveSelectedRepo] });
      queryClient.invalidateQueries({ queryKey: ['runs', effectiveSelectedRepo] });
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
    const defaultClasses = "font-medium capitalize text-xs border";
    switch (status) {
      case 'closed':
      case 'succeeded':
        return <Badge variant="outline" className={`${defaultClasses} border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-500/30 dark:bg-emerald-500/15 dark:text-emerald-300`}><span className="size-1.5 rounded-full bg-emerald-600 dark:bg-emerald-400" />Succeeded</Badge>;
      case 'running':
        return <Badge variant="outline" className={`${defaultClasses} animate-pulse border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-500/35 dark:bg-amber-500/15 dark:text-amber-300`}><span className="size-1.5 rounded-full bg-amber-600 dark:bg-amber-400" />Running</Badge>;
      case 'failed':
        return <Badge variant="outline" className={`${defaultClasses} border-red-200 bg-red-50 text-red-900 dark:border-red-500/35 dark:bg-red-500/15 dark:text-red-300`}><span className="size-1.5 rounded-full bg-red-600 dark:bg-red-400" />Failed</Badge>;
      case 'blocked':
        return <Badge variant="outline" className={`${defaultClasses} border-orange-200 bg-orange-50 text-orange-900 dark:border-orange-500/35 dark:bg-orange-500/15 dark:text-orange-300`}><span className="size-1.5 rounded-full bg-orange-600 dark:bg-orange-400" />Blocked</Badge>;
      case 'ready':
        return <Badge variant="outline" className={`${defaultClasses} border-blue-200 bg-blue-50 text-blue-900 dark:border-blue-500/35 dark:bg-blue-500/15 dark:text-blue-300`}><span className="size-1.5 rounded-full bg-blue-600 dark:bg-blue-400" />Ready</Badge>;
      case 'claimed':
        return <Badge variant="outline" className={`${defaultClasses} border-cyan-200 bg-cyan-50 text-cyan-900 dark:border-cyan-500/35 dark:bg-cyan-500/15 dark:text-cyan-300`}><span className="size-1.5 rounded-full bg-cyan-700 dark:bg-cyan-300" />Claimed</Badge>;
      case 'unready':
        return <Badge variant="outline" className={`${defaultClasses} border-border bg-muted text-foreground`}>Unready</Badge>;
      default:
        return <Badge variant="outline" className={`${defaultClasses} border-border bg-muted text-foreground`}>{status || 'Unknown'}</Badge>;
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



  const PrdMetricsRow = ({ prdNumber }: { prdNumber: number }) => {
    const { data, isPending } = usePrdMetricsQuery(effectiveSelectedRepo, prdNumber);

    if (isPending) {
      return (
        <div className="px-4 py-2 border-b border-border">
          <div className="flex items-center gap-2">
            <Skeleton className="h-3 w-16 animate-shimmer" />
            <Skeleton className="h-3 w-12 animate-shimmer" />
          </div>
        </div>
      );
    }

    if (!data) return null;

    const metrics = data;
    const hasChildren = metrics.implementation_issue_count > 0;
    if (!hasChildren && !metrics.metrics_available) {
      return null;
    }

    return (
      <div
        className="px-4 py-2 border-b border-border bg-muted/10"
        role="region"
        aria-label={`PRD #${prdNumber} delivery metrics`}
      >
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] font-mono text-muted-foreground">
          {/* Child issue status counts */}
          <span className="flex items-center gap-1">
            <Layers className="size-3 shrink-0" />
            <span className="font-semibold text-foreground">{metrics.implementation_issue_count}</span> children
          </span>

          {/* Run count */}
          <span className="flex items-center gap-1">
            <Activity className="size-3 shrink-0" />
            <span className="font-semibold text-foreground">{metrics.total_run_count}</span> runs
          </span>

          {/* Success / failure */}
          <span className="flex items-center gap-1">
            <CheckCircle2 className="size-3 shrink-0 text-emerald-500" />
            <span className="font-semibold text-emerald-600 dark:text-emerald-400">{metrics.successful_run_count}</span>
          </span>
          <span className="flex items-center gap-1">
            <AlertCircle className="size-3 shrink-0 text-red-500" />
            <span className={`font-semibold ${(metrics.total_run_count - metrics.successful_run_count) > 0 ? 'text-red-600 dark:text-red-400' : ''}`}>{metrics.total_run_count - metrics.successful_run_count}</span>
          </span>

          {/* Integrated (end-to-end) success rate */}
          {metrics.total_run_count > 0 && (
            <span className="flex items-center gap-1">
              <GitMerge className="size-3 shrink-0 text-purple-500" />
              <span className={`font-semibold ${metrics.integrated_run_count > 0 ? 'text-purple-600 dark:text-purple-400' : 'text-muted-foreground'}`}>
                {((metrics.integrated_run_count / metrics.total_run_count) * 100).toFixed(0)}% e2e
              </span>
            </span>
          )}

          <span className="text-border select-none">|</span>

          {/* Model usage */}
          <span className="flex items-center gap-1">
            <Cpu className="size-3 shrink-0" />
            <span className="font-semibold text-foreground">{formatCompactTokens(metrics.total_tokens)}</span> tokens
          </span>
          <span className="flex items-center gap-1">
            <span className="font-semibold text-foreground">{formatCompactCost(metrics.model_cost)}</span>
          </span>

          <span className="text-border select-none">|</span>

          {/* Responsiveness */}
          <span className="flex items-center gap-1">
            <Zap className="size-3 shrink-0" />
            TTF <span className="font-semibold text-foreground">{formatCompactMs(metrics.avg_time_to_first_token_ms)}</span>
          </span>
          <span className="flex items-center gap-1">
            <Clock className="size-3 shrink-0" />
            <span className="font-semibold text-foreground">{formatCompactMs(metrics.avg_latency_ms)}</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="font-semibold text-foreground">{formatCompactTokensPerSec(metrics.avg_output_tokens_per_sec)}</span>
          </span>

          {/* Telemetry diagnostics */}
          {(metrics.runs_without_telemetry > 0 || (metrics.diagnostics && metrics.diagnostics.length > 0)) && (
            <>
              <span className="text-border select-none">|</span>
              <span
                className="flex items-center gap-1 text-amber-600 dark:text-amber-400"
                aria-label={`${metrics.runs_without_telemetry} runs missing telemetry`}
              >
                <BarChart3 className="size-3 shrink-0" />
                <span className="font-semibold">{metrics.runs_without_telemetry}</span> missing telemetry
                {metrics.diagnostics && metrics.diagnostics.length > 0 && (
                  <span
                    className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-1 py-0 text-[8px] dark:border-amber-500/30 dark:bg-amber-500/10"
                    title={metrics.diagnostics.map((d: { message: string }) => d.message).join('; ')}
                  >
                    {metrics.diagnostics.length} diag
                  </span>
                )}
              </span>
            </>
          )}
        </div>
      </div>
    );
  };

  // Filter issues based on UI controls
  const prdIssues = issues.filter(i => i.kind === 'prd');
  const defaultExpandedPrds = prdIssues.reduce<Record<number, boolean>>((acc, prd) => {
    acc[prd.number] = false;
    return acc;
  }, {});
  const visibleExpandedPrds = { ...defaultExpandedPrds, ...expandedPrds };

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

  const currentRepo = repos.find(r => r.name === effectiveSelectedRepo);
  const capacity = currentRepo?.global_concurrency || 0;
  const activeRunsCount = getActiveRunsCount();

  return (
    <div className="dashboard-shell relative min-h-screen text-foreground flex antialiased">
      {/* Premium Collapsible Left Sidebar */}
      <Sidebar
        repos={repos}
        selectedRepo={effectiveSelectedRepo}
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
          error={connectionError}
          onRetryConnection={() => {
            queryClient.invalidateQueries({ queryKey: ['repos'] });
            if (effectiveSelectedRepo) {
              queryClient.invalidateQueries({ queryKey: ['issues', effectiveSelectedRepo] });
              queryClient.invalidateQueries({ queryKey: ['runs', effectiveSelectedRepo] });
            }
          }}
          theme={theme}
          toggleTheme={toggleTheme}
          activeRunsCount={activeRunsCount}
          capacity={capacity}
          readyIssuesCount={getReadyIssuesCount()}
          failedRunsCount={getFailedRunsCount()}
          reposCount={repos.length}
        />

      {/* Main Content Layout */}
      {activeTab === 'readiness' ? (
        effectiveSelectedRepo ? (
          <SchedulingReadinessPanel
            repoName={effectiveSelectedRepo}
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
        <main className="grid min-h-0 grow grid-cols-1 gap-6 overflow-hidden p-6 xl:grid-cols-3">

        {/* LEFT COLUMN: RUNS & LOCAL LOGS */}
        <section className="xl:col-span-1 flex h-full min-h-0 flex-col gap-6">

          {/* Agent Runs List Panel */}
          <Card className="dashboard-glass-panel border border-border bg-card text-card-foreground flex flex-col grow shrink overflow-hidden max-h-[380px]">
            <CardHeader className="py-3.5 border-b border-border px-4 flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-xs tracking-wider font-bold uppercase text-foreground flex items-center gap-2">
                  <Layers className="size-3.5 text-muted-foreground" />
                  Recent Agent Runs
                </CardTitle>
                <CardDescription className="text-[10px] text-muted-foreground">Agent execution history</CardDescription>
              </div>
              <Badge variant="outline" className="font-mono text-[9px] border-border text-muted-foreground bg-muted">
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
                  <Server className="mb-2 size-6 text-muted-foreground" />
                  <p className="text-xs text-muted-foreground">No active worktrees or runs registered</p>
                  <p className="mt-1 max-w-[200px] text-[9px] text-muted-foreground">Runs are initialized when implementation issues are claimed.</p>
                </div>
              ) : (
                <ScrollArea className="h-[280px]">
                  <div className="divide-y divide-border">
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
                          className={`dashboard-row p-3 font-mono cursor-pointer flex flex-col gap-2 transition hover:bg-muted/30 ${
                            isSelected
                              ? 'bg-muted border-l-2 border-primary'
                              : 'bg-transparent border-l-2 border-transparent'
                          }`}
                        >
                          <div className="flex items-start justify-between">
                            <span className="text-xs font-bold text-foreground">
                              ISSUE #{run.issue_number}
                            </span>
                            {getStatusBadge(run.status)}
                          </div>

                          <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                            <GitBranch className="size-3 shrink-0" />
                            <span className="truncate max-w-[240px]" title={run.implementation_branch}>
                              {run.implementation_branch}
                            </span>
                          </div>

                          <div className="flex items-center justify-between text-[9px] text-muted-foreground">
                            <div className="flex items-center gap-1">
                              <Clock className="size-2.5" />
                              <span>{formatDate(run.started_at)}</span>
                            </div>
                            {run.finished_at && (
                              <span>
                                elapsed: {Math.round((new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000)}s
                              </span>
                            )}
                          </div>

                          {run.failure_reason && (
                            <div className="mt-1 max-h-16 overflow-y-auto rounded border border-red-200 bg-red-50 p-1.5 font-mono text-[9.5px] text-red-900 whitespace-pre-wrap dark:border-red-500/35 dark:bg-red-500/10 dark:text-red-300">
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
          <Card className="dashboard-glass-panel flex min-h-0 grow shrink flex-col overflow-hidden">
            <CardHeader className="flex flex-col gap-3 border-b border-border px-4 py-3.5 select-none sm:flex-row sm:items-center sm:justify-between">
              <div>
                <CardTitle className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-foreground">
                  <Terminal className="size-3.5 text-muted-foreground" />
                  Harness Log
                  {selectedRunIssue && (
                    <Badge variant="outline" className="ml-1 h-5 rounded border-border bg-muted px-1.5 font-mono text-[9px] text-muted-foreground">
                      #{selectedRunIssue}
                    </Badge>
                  )}
                </CardTitle>
                <CardDescription className="text-[10px] text-muted-foreground">
                  {selectedRunIssue ? `Tailing active runner for Issue #${selectedRunIssue}` : 'Idle - no active run selected'}
                </CardDescription>
              </div>
              {selectedRunIssue !== null && (
                <div className="flex items-center gap-2 text-[10px] font-mono">
                  <input
                    type="text"
                    placeholder="Search log..."
                    aria-label="Search log content"
                    value={logSearchQuery}
                    onChange={(e) => setLogSearchQuery(e.target.value)}
                    className="dashboard-control w-[120px] rounded px-1.5 py-0.5 text-[10px] focus:outline-none placeholder:text-muted-foreground"
                  />

                  <span className="text-border">|</span>

                  <select
                    aria-label="Log tail limit"
                    value={logsLimit}
                    onChange={(e) => setLogsLimit(Number(e.target.value))}
                    className="dashboard-control rounded px-1.5 py-0.5 focus:outline-none"
                  >
                    <option value={20}>20 lines</option>
                    <option value={50}>50 lines</option>
                    <option value={100}>100 lines</option>
                    <option value={300}>300 lines</option>
                  </select>

                  {logTail && (
                    <Button
                      type="button"
                      size="icon-xs"
                      variant="outline"
                      onClick={exportLoadedLogTail}
                      aria-label={`Export loaded tail for Implementation Issue #${logTail.issue_number}`}
                      title="Export loaded tail"
                      className="dashboard-control text-muted-foreground hover:text-foreground"
                    >
                      <Download data-icon="inline-start" />
                    </Button>
                  )}
                </div>
              )}
            </CardHeader>
            <CardContent className="flex min-h-0 grow flex-col overflow-hidden bg-card p-0 font-mono">
              {selectedRunIssue === null ? (
                <div className="flex grow flex-col items-center justify-center p-6 text-center font-mono text-muted-foreground">
                  <Terminal className="mb-2 size-8 text-muted-foreground/45" />
                  <p className="text-xs">Console is offline.</p>
                  <p className="mt-1 text-[9px] text-muted-foreground">Pick a claimed/active run from the list to display active logs.</p>
                </div>
              ) : !logTail ? (
                <div className="grow flex items-center justify-center p-6">
                  <div className="flex flex-col gap-2 w-full max-w-[180px]">
                    <Skeleton className="h-3 w-full animate-shimmer" />
                    <Skeleton className="h-3 w-3/4 animate-shimmer" />
                  </div>
                </div>
              ) : (
                <div className="flex min-h-0 grow flex-col overflow-hidden text-[10px]">
                  <div className="flex shrink-0 items-center justify-between border-b border-border bg-muted/20 px-4 py-1.5 text-[9px] font-mono text-muted-foreground">
                    <span className="truncate pr-4">PATH: {logTail.log_path}</span>
                    <span className="shrink-0">{logTail.lines_returned} lines</span>
                  </div>

                  <div
                    ref={terminalViewportRef}
                    role="log"
                    aria-label={`Issue #${logTail.issue_number} harness log tail`}
                    aria-live="polite"
                    onScroll={handleLogScroll}
                    className="terminal-scrollbar dashboard-focus relative min-h-0 grow overflow-y-auto bg-background p-4"
                  >
                    <div className="space-y-1 font-mono text-foreground whitespace-pre-wrap leading-relaxed select-text">
                      {logTail.content ? (
                        logTail.content.split('\n').map((line, idx) => (
                          <div key={idx} className="table-row">
                            <span className="table-cell w-8 select-none pr-3 text-right font-mono text-muted-foreground/55">{idx + 1}</span>
                            <span className="table-cell text-foreground">{highlightMatches(line, logSearchQuery)}</span>
                          </div>
                        ))
                      ) : (
                        <div className="py-4 text-center text-muted-foreground">
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
                        className="dashboard-control sticky bottom-2 ml-auto font-mono text-[9px] uppercase tracking-wider text-foreground"
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
        <section className="flex h-full min-h-0 flex-col gap-6 overflow-hidden xl:col-span-2">
          <Card className="dashboard-glass-panel flex h-full min-h-0 grow flex-col overflow-hidden border border-border bg-card text-card-foreground">
            {/* Header Controls for filtering */}
            <CardHeader className="py-4 border-b border-border px-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <CardTitle className="text-sm text-foreground flex items-center gap-2 uppercase tracking-wider">
                  <Database className="size-4 text-muted-foreground" />
                  Product Roadmap & Implementation Operations
                </CardTitle>
                <CardDescription className="text-xs text-muted-foreground">
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
                  className="dashboard-control bg-transparent border border-border text-foreground rounded px-2.5 py-1.5 focus:outline-none placeholder:text-muted-foreground w-[140px] text-xs"
                />

                {/* Filter */}
                <div className="dashboard-control flex items-center gap-1.5 border border-border rounded px-2 py-1">
                  <ListFilter className="size-3 text-muted-foreground" />
                  <select
                    value={filterStatus}
                    onChange={(e) => setFilterStatus(e.target.value)}
                    className="dashboard-focus bg-transparent text-foreground focus:outline-none cursor-pointer text-xs font-semibold pr-1 rounded"
                  >
                    <option value="all" className="bg-background text-foreground">ALL STATUS</option>
                    <option value="ready" className="bg-background text-foreground">READY</option>
                    <option value="claimed" className="bg-background text-foreground">CLAIMED</option>
                    <option value="running" className="bg-background text-foreground">RUNNING</option>
                    <option value="succeeded" className="bg-background text-foreground">SUCCEEDED</option>
                    <option value="failed" className="bg-background text-foreground">FAILED</option>
                    <option value="blocked" className="bg-background text-foreground">BLOCKED</option>
                    <option value="unready" className="bg-background text-foreground">UNREADY</option>
                  </select>
                </div>
              </div>
            </CardHeader>
            <CardContent className="min-h-0 grow overflow-hidden p-0">
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
                  <FileText className="mb-2 size-8 text-muted-foreground" />
                  <p className="text-xs text-muted-foreground">No PRD Issues found matching search criteria</p>
                  <p className="mt-1 max-w-[340px] text-[10px] text-muted-foreground">
                    Configure issue gateways and ensure issues carry labels such as 'prd' or 'implementation'.
                  </p>
                </div>
              ) : (
                <ScrollArea className="h-full px-6 py-4">
                  <div className="space-y-6">
                    {filteredPrds.map((prd) => {
                      const isExpanded = visibleExpandedPrds[prd.number];
                      const children = prd.children || [];
                      const canPreparePrd = prd.state === 'open' && !prd.prd_branch;
                      const prepareState = preparePrdState[prd.number];
                      const isPreparingPrd = prepareState?.status === 'loading';

                      return (
                        <div
                          key={prd.number}
                          className="dashboard-glass-surface border border-border rounded overflow-hidden transition-all duration-200 hover:border-border"
                        >
                          {/* PRD Main Bar */}
                          <div
                            onClick={() => togglePrdExpand(prd.number)}
                            role="button"
                            tabIndex={0}
                            aria-expanded={isExpanded}
                            aria-label={`${isExpanded ? 'Collapse' : 'Expand'} PRD #${prd.number}`}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter' || event.key === ' ') {
                                event.preventDefault();
                                togglePrdExpand(prd.number);
                              }
                            }}
                            className="dashboard-row bg-card hover:bg-muted/40 px-4 py-3.5 cursor-pointer flex items-center justify-between border-b border-border transition"
                          >
                            <div className="flex items-center gap-3">
                              <span className="font-mono text-xs font-extrabold text-muted-foreground bg-muted border border-border px-1.5 py-0.5 rounded">
                                PRD #{prd.number}
                              </span>
                              <div>
                                <h3
                                  className="text-xs font-bold text-foreground tracking-wide leading-none mb-1.5 cursor-pointer hover:text-primary transition-colors"
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
                                  <div className="flex items-center gap-1 text-[9px] text-muted-foreground font-mono">
                                    <GitBranch className="size-2.5 text-muted-foreground" />
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
                                  className="dashboard-control text-[9px] uppercase tracking-wider text-muted-foreground"
                                >
                                  <GitBranch data-icon="inline-start" className={isPreparingPrd ? 'animate-pulse' : ''} />
                                  {isPreparingPrd ? 'Preparing' : 'Prepare'} PRD #{prd.number}
                                </Button>
                              )}
                              <Badge variant="outline" className="font-mono text-[9px] border-border text-muted-foreground bg-muted px-2 py-0.5">
                                {children.length} Slices
                              </Badge>
                              {isExpanded ? (
                                <ChevronDown className="size-4 text-muted-foreground" />
                              ) : (
                                <ChevronRight className="size-4 text-muted-foreground" />
                              )}
                            </div>
                          </div>

                          {prepareState && prepareState.status !== 'loading' && (
                            <div
                              className={`px-4 py-2 border-b text-[10px] font-mono ${
                                prepareState.status === 'succeeded'
                                  ? 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-500/35 dark:bg-emerald-500/10 dark:text-emerald-300'
                                  : 'border-red-200 bg-red-50 text-red-900 dark:border-red-500/35 dark:bg-red-500/10 dark:text-red-300'
                              }`}
                              role={prepareState.status === 'failed' ? 'alert' : 'status'}
                            >
                              {prepareState.message}
                            </div>
                          )}

                          {/* Compact PRD Metrics */}
                          <PrdMetricsRow prdNumber={prd.number} />

                          {/* Dependency Pipeline Map */}
                          {isExpanded && children.length > 0 && (
                            <DependencyPipeline children={children} />
                          )}

                          {/* PRD Children (Implementation Issues) */}
                          {isExpanded && (
                            <div className="terminal-scrollbar max-h-[min(34rem,calc(100vh-22rem))] overflow-y-auto bg-muted/20 p-4 divide-y divide-border">
                              {children.length === 0 ? (
                                <div className="text-center py-4 text-[10px] text-muted-foreground">
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
                                        isSelectedLog ? 'bg-muted/60 px-2 -mx-2 rounded border border-border' : ''
                                      }`}
                                    >
                                      {/* Issue Title / Kind */}
                                      <div className="flex items-start gap-2.5 grow">
                                        <CornerDownRight className="size-4 text-muted-foreground shrink-0 mt-0.5" />
                                        <div className="space-y-1.5 max-w-[480px]">
                                          <div className="flex flex-wrap items-center gap-2">
                                            <span className="text-[10px] font-bold text-foreground hover:underline cursor-pointer">
                                              #{c.number}
                                            </span>
                                            <span
                                              className="text-[11px] text-muted-foreground font-semibold leading-tight font-sans cursor-pointer hover:text-primary transition-colors"
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
                                          <div className="flex flex-col gap-1 text-[9.5px] text-muted-foreground">
                                            {c.implementation_branch && (
                                              <span className="flex items-center gap-1.5">
                                                <GitBranch className="size-3 text-muted-foreground shrink-0" />
                                                <span className="truncate max-w-[380px] text-muted-foreground/80">
                                                  {c.implementation_branch}
                                                </span>
                                              </span>
                                            )}

                                            {c.started_at && (
                                              <span className="flex items-center gap-1.5">
                                                <Clock className="size-3 text-muted-foreground shrink-0" />
                                                <span>
                                                  Started: {formatDate(c.started_at)}
                                                  {c.finished_at && ` | Done: ${formatDate(c.finished_at)}`}
                                                </span>
                                              </span>
                                            )}
                                            {c.claimed_at && (
                                              <span className="flex items-center gap-1.5">
                                                <Clock className="size-3 text-muted-foreground shrink-0" />
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
                                              <span className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">
                                                Blocking Dependency
                                              </span>
                                              <div className="relative flex flex-wrap items-center gap-1.5 pl-1 before:absolute before:left-1 before:right-1 before:top-1/2 before:h-px before:-translate-y-1/2 before:bg-border">
                                                {c.blocked_by.map(num => {
                                                  const isOpenBlockingDependency = c.active_blockers?.includes(num) ?? false;

                                                  return (
                                                    <span
                                                      key={num}
                                                      aria-label={`${isOpenBlockingDependency ? 'Open' : 'Resolved'} Blocking Dependency #${num}`}
                                                      className={`relative z-10 inline-flex h-5 items-center gap-1 rounded-full border px-1.5 text-[9px] font-bold uppercase tracking-wider ${
                                                        isOpenBlockingDependency
                                                          ? 'border-orange-200 bg-orange-50 text-orange-900 dark:border-orange-500/35 dark:bg-orange-500/15 dark:text-orange-300'
                                                          : 'border-border bg-muted text-muted-foreground'
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
                                                  ? 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-500/35 dark:bg-emerald-500/10 dark:text-emerald-300'
                                                  : 'border-red-200 bg-red-50 text-red-900 dark:border-red-500/35 dark:bg-red-500/10 dark:text-red-300'
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
                                                  ? 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-500/35 dark:bg-emerald-500/10 dark:text-emerald-300'
                                                  : 'border-red-200 bg-red-50 text-red-900 dark:border-red-500/35 dark:bg-red-500/10 dark:text-red-300'
                                              }`}
                                              role={startState.status === 'failed' ? 'alert' : 'status'}
                                            >
                                              {startState.message}
                                            </div>
                                          )}

                                          {isClaimFormOpen && (
                                            <form
                                              className="flex flex-col gap-2 rounded border border-border bg-muted/40 px-2 py-2"
                                              aria-label={`Claim Implementation Issue #${c.number}`}
                                              onSubmit={(event) => {
                                                event.preventDefault();
                                                claimImplementationIssue(c.number);
                                              }}
                                            >
                                              <label
                                                htmlFor={`claim-agent-run-${c.number}`}
                                                className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground"
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
                                                  className="dashboard-control min-w-0 w-full rounded px-2 py-1 font-mono text-[10px] text-foreground focus:outline-none sm:w-[260px]"
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
                                                  className="dashboard-control text-[9px] uppercase tracking-wider text-foreground"
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
                                                  ? 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-500/35 dark:bg-emerald-500/10 dark:text-emerald-300'
                                                  : 'border-red-200 bg-red-50 text-red-900 dark:border-red-500/35 dark:bg-red-500/10 dark:text-red-300'
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
                                                <EyeOff className="size-3 text-muted-foreground" />
                                                Hide Log
                                              </>
                                            ) : (
                                              <>
                                                <Eye className="size-3 text-muted-foreground" />
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
                                            className="dashboard-control text-[9px] uppercase tracking-wider text-foreground"
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
                                            className="dashboard-control text-[9px] uppercase tracking-wider text-foreground"
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
                                            className="dashboard-control text-[9px] uppercase tracking-wider text-foreground"
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
        runMetrics={runMetricsQuery.data ?? null}
        runMetricsLoading={drawerRunIssueNumber !== null && runMetricsQuery.isPending}
        runMetricsError={runMetricsQuery.error ? String(runMetricsQuery.error) : null}
        implementationIssueMetrics={implIssueMetricsQuery.data ?? null}
        implementationIssueMetricsLoading={drawerRunIssueNumber !== null && implIssueMetricsQuery.isPending}
        implementationIssueMetricsError={implIssueMetricsQuery.error ? String(implIssueMetricsQuery.error) : null}
      />

      {/* Footer Info Box */}
      <footer className="mt-auto flex shrink-0 items-center justify-between border-t px-6 py-3 text-[10px] text-muted-foreground">
        <SSEStatus isConnected={sseState.isConnected} />
        <div>
          <span>Rangkai v1.0.0</span>
        </div>
      </footer>
      </div>
    </div>
  )
}
