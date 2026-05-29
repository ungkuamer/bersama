import { useState, useEffect, useRef } from 'react'
import { 
  Terminal, 
  RefreshCw, 
  GitBranch, 
  AlertCircle, 
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
  Pause,
  Server
} from 'lucide-react'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'

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
  status?: 'closed' | 'failed' | 'ready' | 'unready' | 'running' | 'blocked' | 'succeeded' | 'unknown';
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
  
  // UI States
  const [expandedPrds, setExpandedPrds] = useState<Record<number, boolean>>({});
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState<string>('');
  
  const terminalEndRef = useRef<HTMLDivElement>(null);

  // Fetch initial repositories list
  useEffect(() => {
    fetchRepos();
  }, []);

  const fetchRepos = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/repos`);
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();
      setRepos(data);
      if (data.length > 0 && !selectedRepo) {
        setSelectedRepo(data[0].name);
      }
    } catch (err: any) {
      console.error("Error fetching repos:", err);
      setError(`Failed to connect to backend: ${err.message}`);
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

      const issuesData = await issuesRes.json();
      const runsData = await runsRes.json();

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
    } catch (err: any) {
      console.error("Error fetching data:", err);
      setError(`Data fetch failed: ${err.message}`);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  // Handle selected repository changes
  useEffect(() => {
    if (selectedRepo) {
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
      const data = await res.json();
      setLogTail(data);
    } catch (err: any) {
      console.error("Error fetching logs:", err);
      setLogTail({
        issue_number: issueNumber,
        log_path: 'Error',
        lines_returned: 0,
        content: `Error loading log: ${err.message}`
      });
    }
  };

  // Fetch logs whenever selected run or limit changes
  useEffect(() => {
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

  // Scroll terminal to bottom without moving the page
  useEffect(() => {
    if (terminalEndRef.current) {
      terminalEndRef.current.scrollTop = terminalEndRef.current.scrollHeight;
    }
  }, [logTail]);

  const togglePrdExpand = (prdNumber: number) => {
    setExpandedPrds(prev => ({
      ...prev,
      [prdNumber]: !prev[prdNumber]
    }));
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

  return (
    <div className="min-h-screen bg-[#09090b] text-[#d4d4d8] flex flex-col antialiased">
      {/* Top Banner Status Bar */}
      <header className="border-b border-[#27272a] bg-[#09090b] px-6 py-4 flex flex-col md:flex-row md:items-center md:justify-between gap-4 sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <div className="size-8 rounded border border-zinc-700 flex items-center justify-center bg-zinc-900 text-emerald-400 font-bold">
            B
          </div>
          <div>
            <h1 className="text-sm font-bold text-white tracking-widest uppercase flex items-center gap-2">
              Bersama <span className="text-zinc-600">//</span> Agent Orchestration
            </h1>
            <p className="text-[10px] text-zinc-500 font-mono tracking-tight">Standalone Scaffold Dashboard</p>
          </div>
        </div>

        {/* Global Statistics Panel */}
        <div className="flex flex-wrap items-center gap-4 text-xs font-mono">
          {/* Active Repo Selector */}
          {repos.length > 0 && (
            <div className="flex items-center gap-2 border border-zinc-800 rounded bg-zinc-950 px-2 py-1">
              <Database className="size-3 text-zinc-500" />
              <span className="text-[11px] text-zinc-400">REPO:</span>
              <select 
                value={selectedRepo} 
                onChange={(e) => setSelectedRepo(e.target.value)}
                className="bg-transparent text-white focus:outline-none text-[11px] font-bold cursor-pointer pr-1"
              >
                {repos.map(r => (
                  <option key={r.name} value={r.name} className="bg-zinc-950 text-white">{r.name}</option>
                ))}
              </select>
            </div>
          )}

          {/* Quick Metrics */}
          <div className="flex items-center gap-3 bg-zinc-950 border border-zinc-800 rounded px-3 py-1 text-[11px]">
            <div className="flex items-center gap-1.5 border-r border-zinc-800 pr-3">
              <span className="size-1.5 rounded-full bg-amber-500 animate-pulse"></span>
              <span className="text-zinc-400">ACTIVE RUNS:</span>
              <span className="text-white font-bold">{getActiveRunsCount()}</span>
            </div>
            <div className="flex items-center gap-1.5 border-r border-zinc-800 pr-3">
              <span className="size-1.5 rounded-full bg-blue-500"></span>
              <span className="text-zinc-400">READY ISSUES:</span>
              <span className="text-white font-bold">{getReadyIssuesCount()}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="size-1.5 rounded-full bg-red-500"></span>
              <span className="text-zinc-400">FAILED RUNS:</span>
              <span className="text-white font-bold">{getFailedRunsCount()}</span>
            </div>
          </div>

          {/* Refresh / Polling controls */}
          <div className="flex items-center gap-2 border border-zinc-800 rounded bg-zinc-950 px-2 py-1">
            <button 
              onClick={() => fetchData(true)} 
              disabled={refreshing}
              className="text-zinc-400 hover:text-white transition disabled:opacity-50"
              title="Manual Sync"
            >
              <RefreshCw className={`size-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            </button>
            <span className="text-[10px] text-zinc-600">|</span>
            <button
              onClick={() => setPollingActive(!pollingActive)}
              className="flex items-center gap-1 hover:text-white transition"
            >
              {pollingActive ? (
                <>
                  <Pause className="size-3 text-emerald-400" />
                  <span className="text-[10px] text-zinc-400">AUTO SYNC ON</span>
                </>
              ) : (
                <>
                  <Play className="size-3 text-zinc-500" />
                  <span className="text-[10px] text-zinc-500">AUTO SYNC OFF</span>
                </>
              )}
            </button>
          </div>
        </div>
      </header>

      {/* Connection Failure banner */}
      {error && (
        <div className="bg-red-950/50 border-b border-red-900 text-red-300 px-6 py-2.5 flex items-center gap-3 text-xs font-mono">
          <AlertCircle className="size-4 shrink-0 text-red-400" />
          <div className="grow">
            <strong>SYSTEM FAULT:</strong> {error}
          </div>
          <button 
            onClick={() => { fetchRepos(); if(selectedRepo) fetchData(true); }}
            className="px-2.5 py-1 bg-red-900/60 hover:bg-red-800 rounded border border-red-700 text-red-200 uppercase tracking-wider text-[10px]"
          >
            Retry Connection
          </button>
        </div>
      )}

      {/* Main Content Layout */}
      <main className="grow p-6 grid grid-cols-1 xl:grid-cols-3 gap-6 overflow-hidden">
        
        {/* LEFT COLUMN: RUNS & LOCAL LOGS */}
        <section className="xl:col-span-1 flex flex-col gap-6 h-full min-h-[500px]">
          
          {/* Agent Runs List Panel */}
          <Card className="bg-[#0c0c0e] border-[#27272a] shadow-none flex flex-col grow shrink overflow-hidden max-h-[380px]">
            <CardHeader className="py-3.5 border-b border-zinc-800 px-4 flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-xs tracking-wider font-bold uppercase text-white font-mono flex items-center gap-2">
                  <Layers className="size-3.5 text-zinc-500" />
                  Recent Agent Runs
                </CardTitle>
                <CardDescription className="text-[10px] text-zinc-500 font-mono">Agent execution history</CardDescription>
              </div>
              <Badge variant="outline" className="font-mono text-[9px] border-zinc-800 text-zinc-400">
                {runs.length} Runs
              </Badge>
            </CardHeader>
            <CardContent className="p-0 grow overflow-hidden">
              {loading ? (
                <div className="h-full flex items-center justify-center p-6 text-xs text-zinc-500 font-mono">
                  Loading runs...
                </div>
              ) : runs.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center p-8 text-center font-mono">
                  <Server className="size-6 text-zinc-700 mb-2" />
                  <p className="text-xs text-zinc-500">No active worktrees or runs registered</p>
                  <p className="text-[9px] text-zinc-600 mt-1 max-w-[200px]">Runs are initialized when implementation issues are claimed.</p>
                </div>
              ) : (
                <ScrollArea className="h-[280px]">
                  <div className="divide-y divide-zinc-900">
                    {runs.map((run) => {
                      const isSelected = selectedRunIssue === run.issue_number;
                      return (
                        <div 
                          key={run.issue_number}
                          onClick={() => setSelectedRunIssue(isSelected ? null : run.issue_number)}
                          className={`p-3 font-mono cursor-pointer transition flex flex-col gap-2 ${
                            isSelected 
                              ? 'bg-zinc-900 border-l-2 border-white' 
                              : 'hover:bg-zinc-950 bg-transparent border-l-2 border-transparent'
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
          <Card className="bg-[#09090b] border-[#27272a] shadow-none flex flex-col grow shrink overflow-hidden min-h-[220px]">
            <CardHeader className="py-3.5 border-b border-zinc-800 px-4 flex flex-row items-center justify-between bg-zinc-950">
              <div className="flex items-center gap-2">
                <Terminal className="size-4 text-emerald-400" />
                <div>
                  <CardTitle className="text-xs tracking-wider font-bold uppercase text-white font-mono flex items-center gap-1.5">
                    Terminal Console
                  </CardTitle>
                  <CardDescription className="text-[10px] text-zinc-500 font-mono">
                    {selectedRunIssue ? `Issue #${selectedRunIssue} Harness Log` : 'Select an agent run to read harness logs'}
                  </CardDescription>
                </div>
              </div>
              {selectedRunIssue !== null && (
                <div className="flex items-center gap-2 text-[10px] font-mono">
                  {/* Lines Limit */}
                  <select 
                    value={logsLimit} 
                    onChange={(e) => setLogsLimit(Number(e.target.value))}
                    className="bg-zinc-900 text-zinc-400 border border-zinc-800 rounded px-1.5 py-0.5 focus:outline-none"
                  >
                    <option value={20}>20 lines</option>
                    <option value={50}>50 lines</option>
                    <option value={100}>100 lines</option>
                    <option value={300}>300 lines</option>
                  </select>

                  <span className="text-zinc-700">|</span>

                  {/* Polling Switch */}
                  <button
                    onClick={() => setPollLogsActive(!pollLogsActive)}
                    className={`px-1.5 py-0.5 rounded border border-zinc-800 font-semibold tracking-wider text-[9px] transition ${
                      pollLogsActive 
                        ? 'bg-emerald-950/40 text-emerald-400 border-emerald-900 animate-pulse' 
                        : 'bg-zinc-900 text-zinc-500'
                    }`}
                  >
                    {pollLogsActive ? 'STREAM ON' : 'STREAM OFF'}
                  </button>
                </div>
              )}
            </CardHeader>
            <CardContent className="p-0 grow bg-[#050506] flex flex-col font-mono overflow-hidden">
              {selectedRunIssue === null ? (
                <div className="grow flex flex-col items-center justify-center p-6 text-zinc-600 text-center font-mono">
                  <Terminal className="size-8 text-zinc-800 mb-2" />
                  <p className="text-xs">Console is offline.</p>
                  <p className="text-[9px] text-zinc-700 mt-1">Pick a claimed/active run from the list to display active logs.</p>
                </div>
              ) : !logTail ? (
                <div className="grow flex items-center justify-center p-6 text-zinc-500 text-xs font-mono">
                  Fetching logs from worktree...
                </div>
              ) : (
                <div className="grow flex flex-col overflow-hidden text-[10px]">
                  <div className="bg-[#0c0c0e] px-4 py-1.5 border-b border-zinc-900 text-zinc-500 text-[9px] flex items-center justify-between shrink-0 font-mono">
                    <span className="truncate pr-4">PATH: {logTail.log_path}</span>
                    <span className="shrink-0">{logTail.lines_returned} lines</span>
                  </div>
                  
                  <div ref={terminalEndRef} className="grow p-4 bg-[#030304] overflow-y-auto">
                    <div className="space-y-1 font-mono text-zinc-300 whitespace-pre-wrap leading-relaxed select-text">
                      {logTail.content ? (
                        logTail.content.split('\n').map((line, idx) => (
                          <div key={idx} className="table-row">
                            <span className="table-cell text-zinc-700 select-none pr-3 text-right w-8">{idx + 1}</span>
                            <span className="table-cell text-[#f4f4f5]">{line}</span>
                          </div>
                        ))
                      ) : (
                        <div className="text-zinc-600 text-center py-4">
                          Log is empty. No outputs written by harness.
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </section>

        {/* RIGHT COLUMN: PRDS & CHILD IMPLEMENTATION ISSUES */}
        <section className="xl:col-span-2 flex flex-col gap-6 h-full overflow-hidden">
          <Card className="bg-[#0c0c0e] border-[#27272a] shadow-none flex flex-col grow h-full overflow-hidden">
            {/* Header Controls for filtering */}
            <CardHeader className="py-4 border-b border-zinc-800 px-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <CardTitle className="text-sm font-mono text-white flex items-center gap-2 uppercase tracking-wider">
                  <Database className="size-4 text-zinc-500" />
                  Product Roadmap & Implementation Lifecycle
                </CardTitle>
                <CardDescription className="text-xs text-zinc-500 font-mono">
                  PRD issues hierarchy derived from GitHub Issues state
                </CardDescription>
              </div>

              {/* Filtering / Search Controls */}
              <div className="flex items-center gap-2 font-mono text-xs">
                {/* Search */}
                <input 
                  type="text" 
                  placeholder="SEARCH ISSUE..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="bg-[#09090b] border border-zinc-800 text-zinc-300 rounded px-2.5 py-1.5 focus:outline-none placeholder-zinc-700 focus:border-zinc-500 w-[140px] text-xs"
                />

                {/* Filter */}
                <div className="flex items-center gap-1.5 border border-zinc-800 rounded bg-[#09090b] px-2 py-1">
                  <ListFilter className="size-3 text-zinc-500" />
                  <select
                    value={filterStatus}
                    onChange={(e) => setFilterStatus(e.target.value)}
                    className="bg-transparent text-zinc-300 focus:outline-none cursor-pointer text-xs font-semibold pr-1"
                  >
                    <option value="all" className="bg-[#09090b]">ALL STATUS</option>
                    <option value="ready" className="bg-[#09090b]">READY</option>
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
                <div className="h-full flex items-center justify-center p-8 text-xs text-zinc-500 font-mono">
                  Syncing with GitHub issues...
                </div>
              ) : filteredPrds.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center p-12 text-center font-mono">
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
                      
                      return (
                        <div 
                          key={prd.number}
                          className="border border-zinc-800 rounded bg-[#09090b] overflow-hidden transition-all duration-200 hover:border-zinc-700"
                        >
                          {/* PRD Main Bar */}
                          <div 
                            onClick={() => togglePrdExpand(prd.number)}
                            className="bg-[#0d0d0f] px-4 py-3.5 cursor-pointer flex items-center justify-between border-b border-zinc-800 hover:bg-zinc-900/60 transition"
                          >
                            <div className="flex items-center gap-3">
                              <span className="font-mono text-xs font-extrabold text-zinc-400 bg-zinc-900 border border-zinc-800 px-1.5 py-0.5 rounded">
                                PRD #{prd.number}
                              </span>
                              <div>
                                <h3 className="text-xs font-mono font-bold text-white tracking-wide leading-none mb-1.5">
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

                          {/* PRD Children (Implementation Issues) */}
                          {isExpanded && (
                            <div className="p-4 bg-[#050506] divide-y divide-zinc-900">
                              {children.length === 0 ? (
                                <div className="text-center py-4 font-mono text-[10px] text-zinc-600">
                                  No implementation issue slices declared for this PRD.
                                </div>
                              ) : (
                                children.map((c) => {
                                  const isSelectedLog = selectedRunIssue === c.number;

                                  return (
                                    <div 
                                      key={c.number}
                                      className={`py-3.5 flex flex-col md:flex-row md:items-start justify-between gap-4 font-mono ${
                                        isSelectedLog ? 'bg-zinc-900/20 px-2 -mx-2 rounded border border-zinc-900' : ''
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
                                            <span className="text-[11px] text-zinc-300 font-semibold leading-tight">
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
                                          </div>

                                          {/* Dependencies details */}
                                          {c.blocked_by && c.blocked_by.length > 0 && (
                                            <div className="flex items-center gap-1.5 flex-wrap">
                                              <span className="text-[9px] text-zinc-600 font-bold uppercase">Blocked By:</span>
                                              {c.blocked_by.map(num => (
                                                <Badge 
                                                  key={num} 
                                                  variant="outline" 
                                                  className={`font-mono text-[9px] py-0 px-1 border-zinc-800 ${
                                                    c.active_blockers?.includes(num)
                                                      ? 'text-orange-500 bg-orange-950/20' 
                                                      : 'text-zinc-600 line-through bg-zinc-950'
                                                  }`}
                                                >
                                                  #{num}
                                                </Badge>
                                              ))}
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
                                            className="text-[9.5px] uppercase font-bold tracking-wider px-2 py-0.5 bg-zinc-900 border border-zinc-800 hover:border-zinc-700 hover:text-white rounded transition flex items-center gap-1"
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

      {/* Footer Info Box */}
      <footer className="border-t border-[#27272a] bg-[#09090b] px-6 py-3 flex items-center justify-between text-[10px] text-zinc-500 font-mono mt-auto shrink-0">
        <div className="flex items-center gap-2">
          <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
          <span>Engine Connected</span>
        </div>
        <div>
          <span>Antigravity Orchestration Scaffold v1.0.0</span>
        </div>
      </footer>
    </div>
  )
}
