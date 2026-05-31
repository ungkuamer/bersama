import { useState } from 'react'
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
  GitBranch,
  AlertCircle,
  CheckCircle2,
  GitMerge,
  Hand,
  Send,
  Eye,
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

type TabId = 'overview' | 'execution' | 'branch';

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: 'overview', label: 'Overview', icon: <Info className="size-3.5" /> },
  { id: 'execution', label: 'Execution', icon: <Play className="size-3.5" /> },
  { id: 'branch', label: 'Branch', icon: <GitBranch className="size-3.5" /> },
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
          {TABS.map((tab) => (
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

          {/* ---- Execution Tab ---- */}
          {activeTab === 'execution' && (
            <div className="space-y-4">
              {/* Run Metrics */}
              <section>
                <h4 className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-2">Run Metrics</h4>
                {isImplementation && (issue.status === 'running' || issue.status === 'succeeded' || issue.status === 'failed') ? (
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
                    {issue.agent_run_id && (
                      <div className="flex justify-between">
                        <span className="text-zinc-500">Agent Run:</span>
                        <span className="text-zinc-300 font-mono">{issue.agent_run_id}</span>
                      </div>
                    )}
                  </div>
                ) : issue.status === 'running' ? (
                  <ShimmerCard />
                ) : (
                  <div className="dashboard-glass-surface rounded border p-4 text-center">
                    <Play className="size-5 text-zinc-700 mx-auto mb-1.5" />
                    <p className="text-[10px] text-zinc-500">No active run for this issue.</p>
                    <p className="text-[9px] text-zinc-600 mt-0.5">Start an agent run to see execution metrics.</p>
                  </div>
                )}
              </section>

              {/* Logs Quick View */}
              {isImplementation && (issue.status === 'running' || issue.status === 'succeeded' || issue.status === 'failed') && (
                <section>
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
                </section>
              )}
            </div>
          )}

          {/* ---- Branch Control Deck ---- */}
          {activeTab === 'branch' && (
            <div className="space-y-4">
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
                          ? 'Agent run is active. Monitor in Execution tab.'
                          : issue.status === 'failed'
                          ? 'Run failed. Check Execution tab for details.'
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
