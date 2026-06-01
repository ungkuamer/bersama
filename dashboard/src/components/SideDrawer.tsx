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
import { Skeleton } from '@/components/ui/skeleton'
import { Separator } from '@/components/ui/separator'
import {
  Table,
  TableBody,
  TableCell,
  TableRow,
} from '@/components/ui/table'
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
  const baseClass = "inline-flex items-center gap-1 font-mono text-[9px] uppercase font-bold tracking-wider px-2 py-0.5 rounded border";
  const normalizedStatus = status?.toLowerCase() || 'unknown';
  const statusStyle = (() => {
    switch (normalizedStatus) {
      case 'ready':
        return {
          toneClass: "border-blue-200 bg-blue-50 text-blue-900 dark:border-blue-500/35 dark:bg-blue-500/15 dark:text-blue-300",
          dotColor: "bg-blue-600 dark:bg-blue-400",
          isPulse: false,
        };
      case 'claimed':
        return {
          toneClass: "border-cyan-200 bg-cyan-50 text-cyan-900 dark:border-cyan-500/35 dark:bg-cyan-500/15 dark:text-cyan-300",
          dotColor: "bg-cyan-700 dark:bg-cyan-300",
          isPulse: false,
        };
      case 'running':
        return {
          toneClass: "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-500/35 dark:bg-amber-500/15 dark:text-amber-300",
          dotColor: "bg-amber-600 animate-pulse dark:bg-amber-400",
          isPulse: true,
        };
      case 'succeeded':
      case 'closed':
        return {
          toneClass: "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-500/35 dark:bg-emerald-500/15 dark:text-emerald-300",
          dotColor: "bg-emerald-600 dark:bg-emerald-400",
          isPulse: false,
        };
      case 'failed':
        return {
          toneClass: "border-red-200 bg-red-50 text-red-900 dark:border-red-500/35 dark:bg-red-500/15 dark:text-red-300",
          dotColor: "bg-red-600 dark:bg-red-400",
          isPulse: false,
        };
      case 'blocked':
        return {
          toneClass: "border-orange-200 bg-orange-50 text-orange-900 dark:border-orange-500/35 dark:bg-orange-500/15 dark:text-orange-300",
          dotColor: "bg-orange-600 dark:bg-orange-400",
          isPulse: false,
        };
      default:
        return {
          toneClass: "border-border bg-muted text-foreground",
          dotColor: "bg-muted-foreground",
          isPulse: false,
        };
    }
  })();

  return (
    <Badge className={`${baseClass} ${statusStyle.toneClass} ${statusStyle.isPulse ? 'animate-pulse' : ''}`} variant="outline">
      <span className={`size-1.5 rounded-full ${statusStyle.dotColor}`} />
      {normalizedStatus}
    </Badge>
  );
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
        className="dashboard-glass-panel w-full sm:max-w-lg border-l border-border p-0 gap-0 flex flex-col h-full bg-background"
        showCloseButton={true}
      >
        {/* Drawer Header */}
        <SheetHeader className="border-b border-border px-5 py-4 shrink-0 bg-card">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-extrabold text-muted-foreground bg-muted border border-border px-1.5 py-0.5 rounded">
              {issue.kind === 'prd' ? 'PRD' : 'ISSUE'} #{issue.number}
            </span>
            {getStatusBadge(issue.status)}
          </div>
          <SheetTitle className="text-sm font-bold text-foreground mt-1.5 tracking-tight">
            {issue.title}
          </SheetTitle>
          <SheetDescription className="text-[10px] text-muted-foreground">
            {issue.kind === 'prd' ? 'Product Requirements Document' : 'Implementation Issue'}
            {issue.parent_prd_number && ` · Parent PRD #${issue.parent_prd_number}`}
          </SheetDescription>
        </SheetHeader>

        {/* Tab Bar */}
        <div className="flex border-b border-border shrink-0 bg-card">
          {visibleTabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider transition-all duration-150 border-b-2 -mb-px ${
                activeTab === tab.id
                  ? 'border-primary text-primary bg-primary/5'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="grow overflow-y-auto px-5 py-4 flex flex-col gap-4">
          {/* ---- Overview Tab ---- */}
          {activeTab === 'overview' && (
            <div className="flex flex-col gap-4">
              <section>
                <h4 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Status &amp; Metadata</h4>
                <Table className="border rounded-md border-border">
                  <TableBody>
                    <TableRow className="border-b border-border hover:bg-transparent">
                      <TableCell className="text-muted-foreground text-[10px] font-medium py-2">State</TableCell>
                      <TableCell className="text-foreground text-[10px] capitalize text-right py-2">{issue.state}</TableCell>
                    </TableRow>
                    <TableRow className="border-b border-border hover:bg-transparent">
                      <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Kind</TableCell>
                      <TableCell className="text-foreground text-[10px] capitalize text-right py-2">{issue.kind}</TableCell>
                    </TableRow>
                    {issue.labels.length > 0 && (
                      <TableRow className="border-0 hover:bg-transparent">
                        <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Labels</TableCell>
                        <TableCell className="text-foreground text-[10px] text-right py-2">
                          <div className="flex flex-wrap gap-1 justify-end max-w-[240px]">
                            {issue.labels.map((label) => (
                              <Badge key={label} variant="outline" className="text-[9px] font-mono border-border bg-muted">
                                {label}
                              </Badge>
                            ))}
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </section>

              <Separator className="bg-border" />

              {/* Blocking Dependencies */}
              {issue.blocked_by && issue.blocked_by.length > 0 && (
                <>
                  <section>
                    <h4 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Blocking Dependencies</h4>
                    <div className="flex flex-wrap items-center gap-2">
                      {issue.blocked_by.map((num) => {
                        const isOpen = issue.active_blockers?.includes(num) ?? false;
                        return (
                          <Badge
                            key={num}
                            variant={isOpen ? "destructive" : "outline"}
                            className={`text-[9px] font-bold uppercase tracking-wider h-5 flex items-center gap-1 rounded-full ${
                              isOpen
                                ? 'border-destructive/30 bg-destructive/10 text-destructive'
                                : 'border-border bg-muted text-muted-foreground'
                            }`}
                          >
                            {isOpen ? <AlertCircle className="size-2.5" /> : <CheckCircle2 className="size-2.5" />}
                            <span>{isOpen ? 'Open' : 'Resolved'} #{num}</span>
                          </Badge>
                        );
                      })}
                    </div>
                  </section>
                  <Separator className="bg-border" />
                </>
              )}

              {/* Agent Run Info */}
              {issue.agent_run_id && (
                <>
                  <section>
                    <h4 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Agent Run</h4>
                    <Table className="border rounded-md border-border">
                      <TableBody>
                        <TableRow className="border-b border-border hover:bg-transparent">
                          <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Run ID</TableCell>
                          <TableCell className="text-foreground text-[10px] font-mono text-right py-2">{issue.agent_run_id}</TableCell>
                        </TableRow>
                        {issue.claimed_at && (
                          <TableRow className="border-0 hover:bg-transparent">
                            <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Claimed</TableCell>
                            <TableCell className="text-foreground text-[10px] text-right py-2">{formatDate(issue.claimed_at)}</TableCell>
                          </TableRow>
                        )}
                      </TableBody>
                    </Table>
                  </section>
                  <Separator className="bg-border" />
                </>
              )}

              {/* Failure Reason */}
              {issue.failure_reason && (
                <>
                  <section>
                    <h4 className="text-[10px] font-bold uppercase tracking-wider text-destructive mb-2">Failure Reason</h4>
                    <div className="bg-destructive/10 border border-destructive/20 rounded p-3 text-[9.5px] text-destructive font-mono whitespace-pre-wrap max-h-32 overflow-y-auto">
                      {issue.failure_reason}
                    </div>
                  </section>
                  <Separator className="bg-border" />
                </>
              )}

              {/* PRD-specific: Children overview */}
              {issue.kind === 'prd' && issue.children && issue.children.length > 0 && (
                <section>
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Implementation Slices ({issue.children.length})</h4>
                  <Table className="border rounded-md border-border">
                    <TableBody>
                      {issue.children.map((c, index, array) => (
                        <TableRow key={c.number} className={`${index === array.length - 1 ? 'border-0' : 'border-b border-border'} hover:bg-transparent`}>
                          <TableCell className="font-mono text-[10px] text-muted-foreground py-2">#{c.number}</TableCell>
                          <TableCell className="text-[10px] text-foreground py-2 truncate max-w-[220px]">{c.title}</TableCell>
                          <TableCell className="py-2 text-right">{getStatusBadge(c.status)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </section>
              )}
            </div>
          )}

          {/* ---- Readiness Timeline Tab ---- */}
          {activeTab === 'timeline' && (
            <div className="space-y-6 py-2 px-1">
              <div className="relative border-l border-border ml-3.5 pl-6 space-y-6">
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
                  let dotBg = 'bg-muted border-border text-muted-foreground';
                  let dotIcon = <span className="size-1.5 rounded-full bg-muted-foreground/60" />;
                  let titleColor = 'text-muted-foreground';

                  if (step.status === 'completed') {
                    dotBg = 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/35 dark:bg-emerald-500/15 dark:text-emerald-300';
                    dotIcon = <CheckCircle2 className="size-3.5" />;
                    titleColor = 'text-foreground font-semibold';
                  } else if (step.status === 'active') {
                    dotBg = 'bg-primary/10 border-primary text-primary animate-pulse';
                    dotIcon = <span className="size-2 rounded-full bg-primary animate-pulse" />;
                    titleColor = 'text-foreground font-bold';
                  } else if (step.status === 'failed') {
                    dotBg = 'border-red-200 bg-red-50 text-red-800 dark:border-red-500/35 dark:bg-red-500/15 dark:text-red-300';
                    dotIcon = <AlertCircle className="size-3.5" />;
                    titleColor = 'text-destructive font-semibold';
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
                          <span className="font-mono text-[9px] text-muted-foreground shrink-0">
                            {step.timestamp}
                          </span>
                        )}
                      </div>

                      {/* Description */}
                      <p className="text-[10px] text-muted-foreground leading-relaxed mt-1 font-sans">
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
            <div className="flex flex-col gap-4">
              {/* Git Parameters & Remote Path */}
              <section>
                <h4 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Git Parameters</h4>
                <Table className="border rounded-md border-border">
                  <TableBody>
                    {issue.prd_branch && (
                      <TableRow className={`${issue.implementation_branch ? "border-b border-border" : "border-0"} hover:bg-transparent`}>
                        <TableCell className="text-muted-foreground text-[10px] font-medium py-2">PRD Branch</TableCell>
                        <TableCell className="text-foreground text-[10px] font-mono break-all text-right py-2">{issue.prd_branch}</TableCell>
                      </TableRow>
                    )}
                    {issue.implementation_branch && (
                      <TableRow className="border-0 hover:bg-transparent">
                        <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Impl Branch</TableCell>
                        <TableCell className="text-foreground text-[10px] font-mono break-all text-right py-2">{issue.implementation_branch}</TableCell>
                      </TableRow>
                    )}
                    {!issue.prd_branch && !issue.implementation_branch && (
                      <TableRow className="border-0 hover:bg-transparent">
                        <TableCell colSpan={2} className="text-muted-foreground italic text-[10px] text-center py-2">No branch information available.</TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </section>

              <Separator className="bg-border" />

              {/* Remote / Origin summary */}
              <section>
                <h4 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Remote Path</h4>
                <Table className="border rounded-md border-border">
                  <TableBody>
                    <TableRow className="border-0 hover:bg-transparent">
                      <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Remote Origin</TableCell>
                      <TableCell className="text-foreground text-[10px] font-mono break-all text-right py-2">
                        {issue.prd_branch ? `origin/${issue.prd_branch}` : 'No remote path resolved'}
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </section>

              <Separator className="bg-border" />

              {/* Run Metrics */}
              {isImplementation && (issue.status === 'running' || issue.status === 'succeeded' || issue.status === 'failed') ? (
                <>
                  <section className="space-y-4">
                    <div>
                      <h4 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Run Metrics</h4>
                      <Table className="border rounded-md border-border">
                        <TableBody>
                          <TableRow className="border-b border-border hover:bg-transparent">
                            <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Status</TableCell>
                            <TableCell className="text-foreground text-[10px] text-right py-2 capitalize">{issue.status}</TableCell>
                          </TableRow>
                          {issue.started_at && (
                            <TableRow className={`${issue.finished_at ? "border-b border-border" : "border-0"} hover:bg-transparent`}>
                              <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Started</TableCell>
                              <TableCell className="text-foreground text-[10px] font-mono text-right py-2">{formatDate(issue.started_at)}</TableCell>
                            </TableRow>
                          )}
                          {issue.finished_at && (
                            <TableRow className={`${formatElapsed(issue.started_at, issue.finished_at) ? "border-b border-border" : "border-0"} hover:bg-transparent`}>
                              <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Finished</TableCell>
                              <TableCell className="text-foreground text-[10px] font-mono text-right py-2">{formatDate(issue.finished_at)}</TableCell>
                            </TableRow>
                          )}
                          {formatElapsed(issue.started_at, issue.finished_at) && (
                            <TableRow className="border-0 hover:bg-transparent">
                              <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Elapsed</TableCell>
                              <TableCell className="text-amber-500 text-[10px] font-mono text-right py-2">{formatElapsed(issue.started_at, issue.finished_at)}</TableCell>
                            </TableRow>
                          )}
                        </TableBody>
                      </Table>
                    </div>

                    {/* Logs Quick View */}
                    <div>
                      <h4 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Agent Logs</h4>
                      <Button
                        type="button"
                        size="xs"
                        variant="outline"
                        onClick={() => onViewLog?.(issue.number)}
                        className={`text-[9px] uppercase tracking-wider w-full ${
                          isSelectedLog ? 'text-emerald-500 border-emerald-500' : 'text-foreground border-border'
                        }`}
                      >
                        <Eye className="size-3" data-icon="inline-start" />
                        {isSelectedLog ? 'Log Selected' : 'View Terminal Log'}
                      </Button>
                    </div>
                  </section>
                  <Separator className="bg-border" />
                </>
              ) : isImplementation && issue.status === 'running' ? (
                <>
                  <section>
                    <h4 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Run Metrics</h4>
                    <div className="flex flex-col gap-2 p-3 border border-border rounded-md animate-shimmer animate-pulse">
                      <Skeleton className="h-3 w-1/3" />
                      <Skeleton className="h-3 w-full" />
                      <Skeleton className="h-3 w-5/6" />
                    </div>
                  </section>
                  <Separator className="bg-border" />
                </>
              ) : null}

              {/* Action Controls */}
              {isImplementation && (
                <section>
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Action Controls</h4>
                  <div className="space-y-2">
                    {/* Claim */}
                    {canClaimIssue && (
                      <div className="p-3 border border-border rounded-md">
                        {!claimFormOpen ? (
                          <Button
                            type="button"
                            size="xs"
                            variant="outline"
                            onClick={() => setClaimFormOpen(true)}
                            className="text-[9px] uppercase tracking-wider w-full border-border"
                          >
                            <Hand className="size-3" data-icon="inline-start" />
                            Claim #{issue.number}
                          </Button>
                        ) : (
                          <form onSubmit={handleClaimSubmit} className="space-y-2" aria-label={`Claim Implementation Issue #${issue.number}`}>
                            <label className="text-[9px] text-muted-foreground font-bold uppercase tracking-wider block">
                              Agent Run ID
                            </label>
                            <div className="flex gap-2">
                              <input
                                value={claimAgentRunId || ''}
                                disabled={isClaiming}
                                onChange={(e) => onClaimAgentRunIdChange?.(e.target.value)}
                                className="flex h-8 w-full rounded-md border border-input bg-transparent px-3 py-1 text-xs shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 font-mono"
                                placeholder={`run-${issue.number}-...`}
                              />
                              <Button
                                type="submit"
                                size="xs"
                                variant="outline"
                                disabled={isClaiming}
                                className="text-[9px] uppercase tracking-wider shrink-0 border-border"
                              >
                                <Send className={`size-3 ${isClaiming ? 'animate-pulse' : ''}`} data-icon="inline-start" />
                                {isClaiming ? 'Claiming' : 'Submit'}
                              </Button>
                            </div>
                          </form>
                        )}
                        {claimState && claimState.status !== 'loading' && (
                          <div className={`mt-2 rounded border px-2 py-1 text-[9px] font-mono ${
                            claimState.status === 'succeeded'
                              ? 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-500/35 dark:bg-emerald-500/10 dark:text-emerald-300'
                              : 'border-red-200 bg-red-50 text-red-900 dark:border-red-500/35 dark:bg-red-500/10 dark:text-red-300'
                          }`}>
                            {claimState.message}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Start */}
                    {canStartIssue && (
                      <div className="p-3 border border-border rounded-md">
                        <Button
                          type="button"
                          size="xs"
                          variant="outline"
                          onClick={() => onStart?.(issue.number)}
                          disabled={isStarting}
                          className="text-[9px] uppercase tracking-wider w-full border-border"
                          aria-label={isStarting ? `Starting Agent Run for Implementation Issue #${issue.number}` : `Start Agent Run for Implementation Issue #${issue.number}`}
                        >
                          <Play className={`size-3 ${isStarting ? 'animate-pulse' : ''}`} data-icon="inline-start" />
                          {isStarting ? 'Starting' : 'Start'} Agent Run
                        </Button>
                        {startState && startState.status !== 'loading' && (
                          <div className={`mt-2 rounded border px-2 py-1 text-[9px] font-mono ${
                            startState.status === 'succeeded'
                              ? 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-500/35 dark:bg-emerald-500/10 dark:text-emerald-300'
                              : 'border-red-200 bg-red-50 text-red-900 dark:border-red-500/35 dark:bg-red-500/10 dark:text-red-300'
                          }`}>
                            {startState.message}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Integrate */}
                    {canIntegrateIssue && (
                      <div className="p-3 border border-border rounded-md">
                        <Button
                          type="button"
                          size="xs"
                          variant="outline"
                          onClick={() => onIntegrate?.(issue.number)}
                          disabled={isIntegrating}
                          className="text-[9px] uppercase tracking-wider w-full border-border"
                        >
                          <GitMerge className={`size-3 ${isIntegrating ? 'animate-pulse' : ''}`} data-icon="inline-start" />
                          {isIntegrating ? 'Integrating' : 'Integrate'} #{issue.number}
                        </Button>
                        {integrateState && integrateState.status !== 'loading' && (
                          <div className={`mt-2 rounded border px-2 py-1 text-[9px] font-mono ${
                            integrateState.status === 'succeeded'
                              ? 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-500/35 dark:bg-emerald-500/10 dark:text-emerald-300'
                              : 'border-red-200 bg-red-50 text-red-900 dark:border-red-500/35 dark:bg-red-500/10 dark:text-red-300'
                          }`}>
                            {integrateState.message}
                          </div>
                        )}
                      </div>
                    )}

                    {/* No actions available message */}
                    {!canClaimIssue && !canStartIssue && !canIntegrateIssue && (
                      <p className="text-[10px] text-muted-foreground italic text-center py-3">
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
