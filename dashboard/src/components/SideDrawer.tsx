import { useState, useEffect } from 'react'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ShimmerCard } from '@/components/Shimmer'
import {
  Info,
  Play,
  AlertCircle,
  CheckCircle2,
  GitMerge,
  Hand,
  Send,
  Eye,
  Clock,
} from 'lucide-react'

export interface Issue {
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

export interface SideDrawerProps {
  issue: Issue | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  readOnly?: boolean;
  // Action handlers
  onClaim?: (issueNumber: number) => void;
  onStart?: (issueNumber: number) => void;
  onIntegrate?: (issueNumber: number) => void;
  onViewLog?: (issueNumber: number) => void;
  // Action states
  claimState?: { status: 'loading' | 'succeeded' | 'failed'; message: string };
  startState?: { status: 'loading' | 'succeeded' | 'failed'; message: string };
  integrateState?: { status: 'loading' | 'succeeded' | 'failed'; message: string };
  // Claim form state
  claimAgentRunId?: string;
  onClaimAgentRunIdChange?: (value: string) => void;
  // Selected run
  selectedRunIssue?: number | null;
}

type TabId = 'overview' | 'timeline' | 'operations';

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: 'overview', label: 'Overview', icon: <Info className="size-3.5" /> },
  { id: 'timeline', label: 'Readiness Timeline', icon: <Clock className="size-3.5" /> },
  { id: 'operations', label: 'Operations', icon: <Play className="size-3.5" /> },
];

function getStatusBadge(status?: string) {
  const defaultClasses = "font-mono font-semibold uppercase tracking-wider text-[10px] px-2 py-0.5 rounded border";
  switch (status) {
    case 'closed':
    case 'succeeded':
      return <Badge className={`${defaultClasses} bg-emerald-950/40 text-emerald-400 border-emerald-800`}>SUCCEEDED</Badge>;
    case 'running':
      return <Badge className={`${defaultClasses} bg-amber-950/40 text-amber-400 border-amber-800`}>RUNNING</Badge>;
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
}

function formatDate(dateStr?: string | null) {
  if (!dateStr) return 'N/A';
  try {
    const d = new Date(dateStr);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) + ' ' + d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  } catch {
    return dateStr;
  }
}

function formatElapsed(started?: string | null, finished?: string | null) {
  if (!started || !finished) return null;
  try {
    const elapsed = Math.round((new Date(finished).getTime() - new Date(started).getTime()) / 1000);
    if (elapsed < 60) return `${elapsed}s`;
    if (elapsed < 3600) return `${Math.round(elapsed / 60)}m ${elapsed % 60}s`;
    return `${Math.round(elapsed / 3600)}h ${Math.round((elapsed % 3600) / 60)}m`;
  } catch {
    return null;
  }
}

export default function SideDrawer({
  issue,
  open,
  onOpenChange,
  readOnly = false,
  onClaim,
  onStart,
  onIntegrate,
  onViewLog,
  claimState,
  startState,
  integrateState,
  claimAgentRunId,
  onClaimAgentRunIdChange,
  selectedRunIssue,
}: SideDrawerProps) {
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [claimFormOpen, setClaimFormOpen] = useState(false);

  useEffect(() => {
    if (open) {
      setActiveTab(readOnly ? 'overview' : 'operations');
    }
  }, [open, readOnly]);

  useEffect(() => {
    if (readOnly && activeTab === 'operations') {
      setActiveTab('overview');
    }
  }, [readOnly, activeTab]);

  if (!issue) return null;

  const isImplementation = issue.kind === 'implementation';
  const canClaimIssue = isImplementation && issue.state !== 'closed' && issue.status === 'ready';
  const canStartIssue = isImplementation && issue.state !== 'closed' && issue.status === 'claimed';
  const canIntegrateIssue = isImplementation && issue.state !== 'closed' && issue.status === 'succeeded';
  const isClaiming = claimState?.status === 'loading';
  const isStarting = startState?.status === 'loading';
  const isIntegrating = integrateState?.status === 'loading';
  const isSelectedLog = selectedRunIssue === issue.number;

  const handleClaimSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (onClaim) onClaim(issue.number);
  };

  const visibleTabs = TABS.filter(tab => !(tab.id === 'operations' && readOnly));

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        className="dashboard-glass-panel w-full sm:max-w-lg border-l border-zinc-800 bg-black p-0 gap-0"
        showCloseButton={true}
      >
        {/* Drawer Header */}
        <SheetHeader className="dashboard-glass-panel border-b border-zinc-800 px-5 py-4 shrink-0">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-extrabold text-zinc-400 bg-zinc-900 border border-zinc-800 px-1.5 py-0.5 rounded">
              {issue.kind === 'prd' ? 'PRD' : 'ISSUE'} #{issue.number}
            </span>
            {getStatusBadge(issue.status)}
          </div>
          <SheetTitle className="text-sm font-bold text-white mt-1.5 tracking-tight">
            {issue.title}
          </SheetTitle>
          <SheetDescription className="text-[10px] text-zinc-500">
            {issue.kind === 'prd' ? 'Product Requirements Document' : 'Implementation Issue'}
            {issue.parent_prd_number && ` · Parent PRD #${issue.parent_prd_number}`}
          </SheetDescription>
        </SheetHeader>

        {/* Tab Bar */}
        <div className="flex border-b border-zinc-800 shrink-0">
          {visibleTabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider transition-all duration-150 border-b-2 -mb-px ${
                activeTab === tab.id
                  ? 'border-teal-400 text-teal-400 bg-teal-950/20'
                  : 'border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-700'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="grow overflow-y-auto px-5 py-4">
          {/* ---- Overview Tab ---- */}
          {activeTab === 'overview' && (
            <div className="space-y-4">
              <section>
                <h4 className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-2">Status &amp; Metadata</h4>
                <div className="dashboard-glass-surface rounded border p-3 space-y-2 text-[10px]">
                  <div className="flex justify-between">
                    <span className="text-zinc-500">State:</span>
                    <span className="text-zinc-300 capitalize">{issue.state}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Kind:</span>
                    <span className="text-zinc-300 capitalize">{issue.kind}</span>
                  </div>
                  {issue.labels.length > 0 && (
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Labels:</span>
                      <div className="flex flex-wrap gap-1 justify-end max-w-[240px]">
                        {issue.labels.map((label) => (
                          <span key={label} className="bg-zinc-900 border border-zinc-800 rounded px-1.5 py-0.5 text-[9px] text-zinc-400 font-mono">
                            {label}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </section>

              {/* Blocking Dependencies */}
              {issue.blocked_by && issue.blocked_by.length > 0 && (
                <section>
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-2">Blocking Dependencies</h4>
                  <div className="dashboard-glass-surface rounded border p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      {issue.blocked_by.map((num) => {
                        const isOpen = issue.active_blockers?.includes(num) ?? false;
                        return (
                          <span
                            key={num}
                            aria-label={`${isOpen ? 'Open' : 'Resolved'} Blocking Dependency #${num}`}
                            className={`inline-flex h-5 items-center gap-1 rounded-full border px-2 text-[9px] font-bold uppercase tracking-wider ${
                              isOpen
                                ? 'border-orange-800 bg-orange-950/60 text-orange-300'
                                : 'border-zinc-800 bg-[#050506] text-zinc-600'
                            }`}
                          >
                            {isOpen ? <AlertCircle className="size-2.5" /> : <CheckCircle2 className="size-2.5" />}
                            <span>{isOpen ? 'Open' : 'Resolved'} #{num}</span>
                          </span>
                        );
                      })}
                    </div>
                  </div>
                </section>
              )}

              {/* Agent Run Info */}
              {issue.agent_run_id && (
                <section>
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-2">Agent Run</h4>
                  <div className="dashboard-glass-surface rounded border p-3 space-y-2 text-[10px]">
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Run ID:</span>
                      <span className="text-zinc-300 font-mono">{issue.agent_run_id}</span>
                    </div>
                    {issue.claimed_at && (
                      <div className="flex justify-between">
                        <span className="text-zinc-500">Claimed:</span>
                        <span className="text-zinc-300">{formatDate(issue.claimed_at)}</span>
                      </div>
                    )}
                  </div>
                </section>
              )}

              {/* Failure Reason */}
              {issue.failure_reason && (
                <section>
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-red-400/70 mb-2">Failure Reason</h4>
                  <div className="bg-red-950/20 border border-red-950 rounded p-3 text-[9.5px] text-red-400 font-mono whitespace-pre-wrap max-h-32 overflow-y-auto">
                    {issue.failure_reason}
                  </div>
                </section>
              )}

              {/* PRD-specific: Children overview */}
              {issue.kind === 'prd' && issue.children && issue.children.length > 0 && (
                <section>
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-2">Implementation Slices ({issue.children.length})</h4>
                  <div className="space-y-1.5">
                    {issue.children.map((c) => (
                      <div key={c.number} className="dashboard-glass-surface rounded border p-2 flex items-center justify-between text-[10px]">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-zinc-400">#{c.number}</span>
                          <span className="text-zinc-300 truncate max-w-[280px]">{c.title}</span>
                        </div>
                        {getStatusBadge(c.status)}
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </div>
          )}

          {/* ---- Readiness Timeline Tab ---- */}
          {activeTab === 'timeline' && (
            <div className="space-y-6 py-2 px-1">
              <div className="relative border-l border-zinc-800 ml-3.5 pl-6 space-y-6">
                {(() => {
                  const isClosed = issue.state === 'closed' || issue.status === 'closed';

                  if (issue.kind === 'prd') {
                    // PRD Specific Timeline
                    const totalSlices = issue.children?.length ?? 0;
                    const claimedSlices = issue.children?.filter(c => ['claimed', 'running', 'succeeded', 'failed', 'closed'].includes(c.status || '')).length ?? 0;
                    const executedSlices = issue.children?.filter(c => ['succeeded', 'closed'].includes(c.status || '')).length ?? 0;
                    const runningSlices = issue.children?.filter(c => c.status === 'running').length ?? 0;
                    const integratedSlices = issue.children?.filter(c => c.state === 'closed' || c.status === 'closed').length ?? 0;

                    return [
                      {
                        title: 'Prepared PRD',
                        status: 'completed',
                        timestamp: 'Confirmed',
                        description: 'The product requirements document was successfully authored, triaged, and made ready for slicing.'
                      },
                      {
                        title: 'Slices Discovered',
                        status: totalSlices > 0 ? 'completed' : 'pending',
                        timestamp: totalSlices > 0 ? `${totalSlices} slices` : 'Pending',
                        description: totalSlices > 0
                          ? `Successfully compiled ${totalSlices} implementation slices from the core specifications.`
                          : 'No implementation slices discovered yet.'
                      },
                      {
                        title: 'Slices Claimed',
                        status: claimedSlices === totalSlices && totalSlices > 0
                          ? 'completed'
                          : claimedSlices > 0
                          ? 'active'
                          : 'pending',
                        timestamp: `${claimedSlices} / ${totalSlices} claimed`,
                        description: `Agents have claimed ${claimedSlices} of the ${totalSlices} total implementation slices.`
                      },
                      {
                        title: 'Slices Executing',
                        status: runningSlices > 0
                          ? 'active'
                          : executedSlices === totalSlices && totalSlices > 0
                          ? 'completed'
                          : 'pending',
                        timestamp: runningSlices > 0 ? `${runningSlices} running` : `${executedSlices} executed`,
                        description: runningSlices > 0
                          ? `${runningSlices} slice(s) are actively running in agent execution sandboxes.`
                          : `${executedSlices} slices have successfully finished execution.`
                      },
                      {
                        title: 'Slices Integrated',
                        status: integratedSlices === totalSlices && totalSlices > 0
                          ? 'completed'
                          : integratedSlices > 0
                          ? 'active'
                          : 'pending',
                        timestamp: `${integratedSlices} / ${totalSlices} merged`,
                        description: `${integratedSlices} slices have been integrated into the main production branch.`
                      },
                      {
                        title: 'PRD Integrated',
                        status: isClosed ? 'completed' : 'pending',
                        timestamp: isClosed ? 'Closed' : 'Awaiting Slices',
                        description: isClosed
                          ? 'PRD requirement has been completely closed and delivered.'
                          : 'Pending complete integration of all children slices.'
                      }
                    ];
                  }

                  // Implementation Issue Timeline
                  return [
                    {
                      title: 'Prepared PRD',
                      status: 'completed' as const,
                      timestamp: 'Confirmed',
                      description: `The requirement was specified and prepared under parent PRD #${issue.parent_prd_number || 'N/A'}.`
                    },
                    {
                      title: 'Claim Setup',
                      status: issue.claimed_at
                        ? ('completed' as const)
                        : issue.status === 'ready'
                        ? ('active' as const)
                        : ('pending' as const),
                      timestamp: formatDate(issue.claimed_at),
                      description: issue.claimed_at
                        ? `Agent run ID "${issue.agent_run_id || 'N/A'}" registered and workspace provisioned.`
                        : 'Waiting for an agent execution scheduler or operator to claim this issue.'
                    },
                    {
                      title: 'Active Claim',
                      status: issue.started_at
                        ? ('completed' as const)
                        : issue.status === 'claimed'
                        ? ('active' as const)
                        : ('pending' as const),
                      timestamp: formatDate(issue.started_at || issue.claimed_at),
                      description: issue.started_at
                        ? 'Workspace environment execution lock acquired.'
                        : issue.status === 'claimed'
                        ? 'Claim registered. Workspace ready to initiate execution sandbox.'
                        : 'Awaiting claim allocation.'
                    },
                    {
                      title: 'Agent Run',
                      status: ['succeeded', 'closed'].includes(issue.status || '')
                        ? ('completed' as const)
                        : issue.status === 'running'
                        ? ('active' as const)
                        : issue.status === 'failed'
                        ? ('failed' as const)
                        : ('pending' as const),
                      timestamp: formatDate(issue.finished_at || issue.started_at),
                      description: issue.status === 'failed'
                        ? `Agent run execution failed: ${issue.failure_reason || 'Unknown error'}`
                        : ['succeeded', 'closed'].includes(issue.status || '')
                        ? `Agent execution succeeded in ${formatElapsed(issue.started_at, issue.finished_at) || 'a few seconds'}.`
                        : issue.status === 'running'
                        ? 'Agent is actively running inside the sandbox environment...'
                        : 'Pending execution start.'
                    },
                    {
                      title: 'Integration PR',
                      status: isClosed
                        ? ('completed' as const)
                        : issue.status === 'succeeded'
                        ? ('active' as const)
                        : ('pending' as const),
                      timestamp: formatDate(issue.finished_at),
                      description: isClosed
                        ? 'Pull request successfully integrated and merged to main branch.'
                        : issue.status === 'succeeded'
                        ? 'Implementation succeeded. Pull Request is open and awaiting merge validation.'
                        : 'Pending code correctness check & execution success.'
                    },
                    {
                      title: 'Integrated Issue',
                      status: isClosed ? ('completed' as const) : ('pending' as const),
                      timestamp: isClosed ? formatDate(issue.finished_at) : 'Awaiting Merge',
                      description: isClosed
                        ? `Issue #${issue.number} has been closed and successfully shipped.`
                        : 'Awaiting Pull Request merge approval and branch cleanup.'
                    }
                  ];
                })().map((step, idx) => {
                  let dotBg = 'bg-zinc-900 border-zinc-700';
                  let dotIcon = <span className="size-1.5 rounded-full bg-zinc-600" />;
                  let titleColor = 'text-zinc-500';

                  if (step.status === 'completed') {
                    dotBg = 'bg-emerald-950/80 border-emerald-500 text-emerald-400';
                    dotIcon = <CheckCircle2 className="size-3.5" />;
                    titleColor = 'text-zinc-200';
                  } else if (step.status === 'active') {
                    dotBg = 'bg-teal-950/80 border-teal-500 text-teal-400 animate-pulse';
                    dotIcon = <span className="size-2 rounded-full bg-teal-400 shadow-[0_0_8px_rgba(20,184,166,0.5)]" />;
                    titleColor = 'text-white font-bold';
                  } else if (step.status === 'failed') {
                    dotBg = 'bg-red-950/80 border-red-500 text-red-400';
                    dotIcon = <AlertCircle className="size-3.5" />;
                    titleColor = 'text-red-400';
                  }

                  return (
                    <div key={idx} className="relative group">
                      {/* Circle dot marker on the left line */}
                      <div className={`absolute -left-[35px] top-0.5 size-6 rounded-full border flex items-center justify-center transition-all ${dotBg}`}>
                        {dotIcon}
                      </div>

                      {/* Header */}
                      <div className="flex items-baseline justify-between gap-2">
                        <h4 className={`text-xs font-semibold uppercase tracking-wider ${titleColor}`}>
                          {step.title}
                        </h4>
                        {step.timestamp && step.timestamp !== 'N/A' && (
                          <span className="font-mono text-[9px] text-zinc-500 shrink-0">
                            {step.timestamp}
                          </span>
                        )}
                      </div>

                      {/* Description */}
                      <p className="text-[10px] text-zinc-400 leading-relaxed mt-1 font-sans">
                        {step.description}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ---- Operations Tab ---- */}
          {activeTab === 'operations' && !readOnly && (
            <div className="space-y-4">
              {/* Git Parameters & Remote Path */}
              <section>
                <h4 className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-2">Git Parameters</h4>
                <div className="dashboard-glass-surface rounded border p-3 space-y-2 text-[10px]">
                  {issue.prd_branch && (
                    <div className="flex justify-between">
                      <span className="text-zinc-500">PRD Branch:</span>
                      <span className="text-zinc-300 font-mono break-all text-right ml-2">{issue.prd_branch}</span>
                    </div>
                  )}
                  {issue.implementation_branch && (
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Impl Branch:</span>
                      <span className="text-zinc-300 font-mono break-all text-right ml-2">{issue.implementation_branch}</span>
                    </div>
                  )}
                  {!issue.prd_branch && !issue.implementation_branch && (
                    <p className="text-zinc-600 italic text-[10px]">No branch information available.</p>
                  )}
                </div>
              </section>

              {/* Remote / Origin summary */}
              <section>
                <h4 className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-2">Remote Path</h4>
                <div className="dashboard-glass-surface rounded border p-3 text-[10px]">
                  <p className="text-zinc-500 font-mono break-all">
                    {issue.prd_branch
                      ? `origin/${issue.prd_branch}`
                      : 'No remote path resolved'}
                  </p>
                </div>
              </section>

              {/* Run Metrics */}
              {isImplementation && (issue.status === 'running' || issue.status === 'succeeded' || issue.status === 'failed') ? (
                <section className="space-y-4">
                  <div>
                    <h4 className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-2">Run Metrics</h4>
                    <div className="dashboard-glass-surface rounded border p-3 space-y-2 text-[10px]">
                      <div className="flex justify-between">
                        <span className="text-zinc-500">Status:</span>
                        <span className="text-zinc-300">{issue.status}</span>
                      </div>
                      {issue.started_at && (
                        <div className="flex justify-between">
                          <span className="text-zinc-500">Started:</span>
                          <span className="text-zinc-300 font-mono">{formatDate(issue.started_at)}</span>
                        </div>
                      )}
                      {issue.finished_at && (
                        <div className="flex justify-between">
                          <span className="text-zinc-500">Finished:</span>
                          <span className="text-zinc-300 font-mono">{formatDate(issue.finished_at)}</span>
                        </div>
                      )}
                      {formatElapsed(issue.started_at, issue.finished_at) && (
                        <div className="flex justify-between">
                          <span className="text-zinc-500">Elapsed:</span>
                          <span className="text-amber-400 font-mono">{formatElapsed(issue.started_at, issue.finished_at)}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Logs Quick View */}
                  <div>
                    <h4 className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-2">Agent Logs</h4>
                    <div className="dashboard-glass-surface rounded border p-3">
                      <Button
                        type="button"
                        size="xs"
                        variant="outline"
                        onClick={() => onViewLog?.(issue.number)}
                        className={`dashboard-control text-[9px] uppercase tracking-wider ${
                          isSelectedLog ? 'text-emerald-400' : 'text-zinc-300'
                        }`}
                      >
                        <Eye className="size-3" />
                        {isSelectedLog ? 'Log Selected' : 'View Terminal Log'}
                      </Button>
                    </div>
                  </div>
                </section>
              ) : isImplementation && issue.status === 'running' ? (
                <section>
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-2">Run Metrics</h4>
                  <ShimmerCard />
                </section>
              ) : null}

              {/* Action Controls */}
              {isImplementation && (
                <section>
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-2">Action Controls</h4>
                  <div className="space-y-2">
                    {/* Claim */}
                    {canClaimIssue && (
                      <div className="dashboard-glass-surface rounded border p-3">
                        {!claimFormOpen ? (
                          <Button
                            type="button"
                            size="xs"
                            variant="outline"
                            onClick={() => setClaimFormOpen(true)}
                            className="dashboard-control text-[9px] uppercase tracking-wider text-zinc-200 w-full"
                          >
                            <Hand className="size-3" />
                            Claim #{issue.number}
                          </Button>
                        ) : (
                          <form onSubmit={handleClaimSubmit} className="space-y-2" aria-label={`Claim Implementation Issue #${issue.number}`}>
                            <label className="text-[9px] text-zinc-500 font-bold uppercase tracking-wider block">
                              Agent Run ID
                            </label>
                            <div className="flex gap-2">
                              <input
                                value={claimAgentRunId || ''}
                                disabled={isClaiming}
                                onChange={(e) => onClaimAgentRunIdChange?.(e.target.value)}
                                className="dashboard-control min-w-0 w-full rounded px-2 py-1 text-[10px] text-zinc-200 focus:outline-none font-mono"
                                placeholder={`run-${issue.number}-...`}
                              />
                              <Button
                                type="submit"
                                size="xs"
                                variant="outline"
                                disabled={isClaiming}
                                className="dashboard-control text-[9px] uppercase tracking-wider text-zinc-200 shrink-0"
                              >
                                <Send className={`size-3 ${isClaiming ? 'animate-pulse' : ''}`} />
                                {isClaiming ? 'Claiming' : 'Submit'}
                              </Button>
                            </div>
                          </form>
                        )}
                        {claimState && claimState.status !== 'loading' && (
                          <div className={`mt-2 rounded border px-2 py-1 text-[9px] font-mono ${
                            claimState.status === 'succeeded'
                              ? 'bg-emerald-950/20 border-emerald-950/60 text-emerald-300'
                              : 'bg-red-950/25 border-red-950/70 text-red-300'
                          }`}>
                            {claimState.message}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Start */}
                    {canStartIssue && (
                      <div className="dashboard-glass-surface rounded border p-3">
                        <Button
                          type="button"
                          size="xs"
                          variant="outline"
                          onClick={() => onStart?.(issue.number)}
                          disabled={isStarting}
                          className="dashboard-control text-[9px] uppercase tracking-wider text-zinc-200 w-full"
                          aria-label={isStarting ? `Starting Agent Run for Implementation Issue #${issue.number}` : `Start Agent Run for Implementation Issue #${issue.number}`}
                        >
                          <Play className={`size-3 ${isStarting ? 'animate-pulse' : ''}`} />
                          {isStarting ? 'Starting' : 'Start'} Agent Run
                        </Button>
                        {startState && startState.status !== 'loading' && (
                          <div className={`mt-2 rounded border px-2 py-1 text-[9px] font-mono ${
                            startState.status === 'succeeded'
                              ? 'bg-emerald-950/20 border-emerald-950/60 text-emerald-300'
                              : 'bg-red-950/25 border-red-950/70 text-red-300'
                          }`}>
                            {startState.message}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Integrate */}
                    {canIntegrateIssue && (
                      <div className="dashboard-glass-surface rounded border p-3">
                        <Button
                          type="button"
                          size="xs"
                          variant="outline"
                          onClick={() => onIntegrate?.(issue.number)}
                          disabled={isIntegrating}
                          className="dashboard-control text-[9px] uppercase tracking-wider text-zinc-200 w-full"
                        >
                          <GitMerge className={`size-3 ${isIntegrating ? 'animate-pulse' : ''}`} />
                          {isIntegrating ? 'Integrating' : 'Integrate'} #{issue.number}
                        </Button>
                        {integrateState && integrateState.status !== 'loading' && (
                          <div className={`mt-2 rounded border px-2 py-1 text-[9px] font-mono ${
                            integrateState.status === 'succeeded'
                              ? 'bg-emerald-950/20 border-emerald-950/60 text-emerald-300'
                              : 'bg-red-950/25 border-red-950/70 text-red-300'
                          }`}>
                            {integrateState.message}
                          </div>
                        )}
                      </div>
                    )}

                    {/* No actions available message */}
                    {!canClaimIssue && !canStartIssue && !canIntegrateIssue && (
                      <p className="text-[10px] text-zinc-600 italic text-center py-3">
                        {issue.status === 'running'
                          ? 'Agent run is active. Monitor in Operations tab.'
                          : issue.status === 'failed'
                          ? 'Run failed. Check Operations tab for details.'
                          : issue.status === 'unready' || issue.status === 'blocked'
                          ? 'Resolve blocking dependencies to enable actions.'
                          : issue.status === 'succeeded' && issue.state !== 'open'
                          ? 'Already integrated.'
                          : 'No actions available for current status.'}
                      </p>
                    )}
                  </div>
                </section>
              )}
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
