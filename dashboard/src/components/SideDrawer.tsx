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
  AlertTriangle,
  CheckCircle2,
  GitMerge,
  Hand,
  Send,
  Eye,
  Clock,
  BarChart3,
  Layers,
} from 'lucide-react'

export interface TelemetryDiagnosticItem {
  code: string;
  severity: string;
  message: string;
}

export interface RunMetrics {
  run_id: string;
  diagnostics: TelemetryDiagnosticItem[];
  metrics_available: boolean;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cache_read_tokens?: number | null;
  cache_write_tokens?: number | null;
  total_tokens?: number | null;
  model_cost?: number | null;
  tool_call_count?: number | null;
  tool_error_count?: number | null;
  error_count?: number | null;
  model?: string | null;
  provider?: string | null;
  avg_time_to_first_token_ms?: number | null;
  avg_latency_ms?: number | null;
  avg_output_tokens_per_sec?: number | null;
  latest_time_to_first_token_ms?: number | null;
  latest_latency_ms?: number | null;
  latest_output_tokens_per_sec?: number | null;
  latest_telemetry_at?: string | null;
}

export interface RunAttempt {
  run_id: string;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  has_telemetry_association: boolean;
}

export interface ImplementationIssueMetrics {
  issue_number: number;
  diagnostics: TelemetryDiagnosticItem[];
  metrics_available: boolean;
  run_count: number;
  successful_run_count: number;
  integrated_run_count: number;
  runs_with_telemetry: number;
  runs_without_telemetry: number;
  failure_count: number;
  latest_run_status: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cache_read_tokens?: number | null;
  cache_write_tokens?: number | null;
  total_tokens?: number | null;
  model_cost?: number | null;
  tool_call_count?: number | null;
  tool_error_count?: number | null;
  avg_time_to_first_token_ms?: number | null;
  avg_latency_ms?: number | null;
  avg_output_tokens_per_sec?: number | null;
  runs?: RunAttempt[];
}

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
  telemetry_diagnostics?: TelemetryDiagnosticItem[] | null;
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
  // Run metrics from telemetry
  runMetrics?: RunMetrics | null;
  // Implementation Issue aggregated metrics
  implementationIssueMetrics?: ImplementationIssueMetrics | null;
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
  runMetrics,
  implementationIssueMetrics,
}: SideDrawerProps) {
  const [selectedTab, setSelectedTab] = useState<TabId>(() => readOnly ? 'overview' : 'operations');
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

  const visibleTabs = TABS.filter(tab => !(tab.id === 'operations' && readOnly));
  const activeTab = readOnly && selectedTab === 'operations' ? 'overview' : selectedTab;
  const setActiveTab = (tab: TabId) => setSelectedTab(tab);

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

              {/* Telemetry Metrics */}
              {isImplementation && runMetrics ? (
                runMetrics.metrics_available ? (
                  <>
                    {/* Model Usage Metrics */}
                    <section>
                      <h4 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
                        <BarChart3 className="size-3" />
                        Model Usage
                      </h4>
                      <Table className="border rounded-md border-border">
                        <TableBody>
                          {runMetrics.input_tokens != null && (
                            <TableRow className="border-b border-border hover:bg-transparent">
                              <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Input Tokens</TableCell>
                              <TableCell className="text-foreground text-[10px] font-mono text-right py-2">{runMetrics.input_tokens?.toLocaleString()}</TableCell>
                            </TableRow>
                          )}
                          {runMetrics.output_tokens != null && (
                            <TableRow className="border-b border-border hover:bg-transparent">
                              <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Output Tokens</TableCell>
                              <TableCell className="text-foreground text-[10px] font-mono text-right py-2">{runMetrics.output_tokens?.toLocaleString()}</TableCell>
                            </TableRow>
                          )}
                          {runMetrics.cache_read_tokens != null && (
                            <TableRow className="border-b border-border hover:bg-transparent">
                              <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Cache Read</TableCell>
                              <TableCell className="text-foreground text-[10px] font-mono text-right py-2">{runMetrics.cache_read_tokens?.toLocaleString()}</TableCell>
                            </TableRow>
                          )}
                          {runMetrics.cache_write_tokens != null && (
                            <TableRow className="border-b border-border hover:bg-transparent">
                              <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Cache Write</TableCell>
                              <TableCell className="text-foreground text-[10px] font-mono text-right py-2">{runMetrics.cache_write_tokens?.toLocaleString()}</TableCell>
                            </TableRow>
                          )}
                          {runMetrics.total_tokens != null && (
                            <TableRow className="border-b border-border hover:bg-transparent">
                              <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Total Tokens</TableCell>
                              <TableCell className="text-foreground text-[10px] font-mono text-right py-2">{runMetrics.total_tokens?.toLocaleString()}</TableCell>
                            </TableRow>
                          )}
                          {runMetrics.model_cost != null && (
                            <TableRow className="border-b border-border hover:bg-transparent">
                              <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Model Cost</TableCell>
                              <TableCell className="text-foreground text-[10px] font-mono text-right py-2">${runMetrics.model_cost?.toFixed(4)}</TableCell>
                            </TableRow>
                          )}
                          {runMetrics.error_count != null && (
                            <TableRow className="border-0 hover:bg-transparent">
                              <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Errors</TableCell>
                              <TableCell className="text-foreground text-[10px] font-mono text-right py-2">{runMetrics.error_count?.toLocaleString()}</TableCell>
                            </TableRow>
                          )}
                        </TableBody>
                      </Table>
                    </section>
                    <Separator className="bg-border" />

                    {/* Tool Activity Metrics */}
                    <section>
                      <h4 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Tool Activity</h4>
                      <Table className="border rounded-md border-border">
                        <TableBody>
                          {runMetrics.tool_call_count != null && (
                            <TableRow className="border-b border-border hover:bg-transparent">
                              <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Tool Calls</TableCell>
                              <TableCell className="text-foreground text-[10px] font-mono text-right py-2">{runMetrics.tool_call_count?.toLocaleString()}</TableCell>
                            </TableRow>
                          )}
                          {runMetrics.tool_error_count != null && (
                            <TableRow className="border-0 hover:bg-transparent">
                              <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Tool Errors</TableCell>
                              <TableCell className="text-destructive text-[10px] font-mono text-right py-2">{runMetrics.tool_error_count?.toLocaleString()}</TableCell>
                            </TableRow>
                          )}
                        </TableBody>
                      </Table>
                    </section>
                    <Separator className="bg-border" />

                    {/* Model & Provider */}
                    {(runMetrics.model || runMetrics.provider) && (
                      <>
                        <section>
                          <h4 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Model Info</h4>
                          <Table className="border rounded-md border-border">
                            <TableBody>
                              {runMetrics.model && (
                                <TableRow className={`${runMetrics.provider ? "border-b border-border" : "border-0"} hover:bg-transparent`}>
                                  <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Model</TableCell>
                                  <TableCell className="text-foreground text-[10px] font-mono text-right py-2">{runMetrics.model}</TableCell>
                                </TableRow>
                              )}
                              {runMetrics.provider && (
                                <TableRow className="border-0 hover:bg-transparent">
                                  <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Provider</TableCell>
                                  <TableCell className="text-foreground text-[10px] font-mono text-right py-2">{runMetrics.provider}</TableCell>
                                </TableRow>
                              )}
                            </TableBody>
                          </Table>
                        </section>
                        <Separator className="bg-border" />
                      </>
                    )}

                    {/* Model Responsiveness */}
                    {((runMetrics.avg_time_to_first_token_ms != null) ||
                      (runMetrics.avg_latency_ms != null) ||
                      (runMetrics.avg_output_tokens_per_sec != null) ||
                      (runMetrics.latest_time_to_first_token_ms != null) ||
                      (runMetrics.latest_latency_ms != null) ||
                      (runMetrics.latest_output_tokens_per_sec != null)) && (
                      <>
                        <section>
                          <h4 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Model Responsiveness</h4>
                          <Table className="border rounded-md border-border">
                            <TableBody>
                              {runMetrics.avg_time_to_first_token_ms != null && (
                                <TableRow className="border-b border-border hover:bg-transparent">
                                  <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Avg TTFT</TableCell>
                                  <TableCell className="text-foreground text-[10px] font-mono text-right py-2">{runMetrics.avg_time_to_first_token_ms?.toFixed(1)} ms</TableCell>
                                </TableRow>
                              )}
                              {runMetrics.avg_latency_ms != null && (
                                <TableRow className="border-b border-border hover:bg-transparent">
                                  <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Avg Latency</TableCell>
                                  <TableCell className="text-foreground text-[10px] font-mono text-right py-2">{runMetrics.avg_latency_ms?.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} ms</TableCell>
                                </TableRow>
                              )}
                              {runMetrics.avg_output_tokens_per_sec != null && (
                                <TableRow className="border-b border-border hover:bg-transparent">
                                  <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Avg Tokens/s</TableCell>
                                  <TableCell className="text-foreground text-[10px] font-mono text-right py-2">{runMetrics.avg_output_tokens_per_sec?.toFixed(1)}</TableCell>
                                </TableRow>
                              )}
                              {runMetrics.latest_time_to_first_token_ms != null && (
                                <TableRow className="border-b border-border hover:bg-transparent">
                                  <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Latest TTFT</TableCell>
                                  <TableCell className="text-muted-foreground text-[10px] font-mono text-right py-2">{runMetrics.latest_time_to_first_token_ms?.toFixed(1)} ms</TableCell>
                                </TableRow>
                              )}
                              {runMetrics.latest_latency_ms != null && (
                                <TableRow className="border-b border-border hover:bg-transparent">
                                  <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Latest Latency</TableCell>
                                  <TableCell className="text-muted-foreground text-[10px] font-mono text-right py-2">{runMetrics.latest_latency_ms?.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} ms</TableCell>
                                </TableRow>
                              )}
                              {runMetrics.latest_output_tokens_per_sec != null && (
                                <TableRow className="border-0 hover:bg-transparent">
                                  <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Latest Tokens/s</TableCell>
                                  <TableCell className="text-muted-foreground text-[10px] font-mono text-right py-2">{runMetrics.latest_output_tokens_per_sec?.toFixed(1)}</TableCell>
                                </TableRow>
                              )}
                            </TableBody>
                          </Table>
                        </section>
                        <Separator className="bg-border" />
                      </>
                    )}

                    {/* Latest Telemetry Timestamp */}
                    {runMetrics.latest_telemetry_at && (
                      <>
                        <section>
                          <h4 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Telemetry</h4>
                          <Table className="border rounded-md border-border">
                            <TableBody>
                              <TableRow className="border-0 hover:bg-transparent">
                                <TableCell className="text-muted-foreground text-[10px] font-medium py-2">Latest Telemetry</TableCell>
                                <TableCell className="text-foreground text-[10px] font-mono text-right py-2">{formatDate(runMetrics.latest_telemetry_at)}</TableCell>
                              </TableRow>
                            </TableBody>
                          </Table>
                        </section>
                        <Separator className="bg-border" />
                      </>
                    )}
                  </>
                ) : (
                  <>
                    <section>
                      <h4 className="text-[10px] font-bold uppercase tracking-wider text-amber-600 dark:text-amber-400 mb-2 flex items-center gap-1.5">
                        <AlertTriangle className="size-3" />
                        Run Telemetry
                      </h4>
                      <div className="flex flex-col gap-2">
                        {runMetrics.diagnostics.map((diag, idx) => (
                          <div
                            key={idx}
                            className="border border-amber-200 bg-amber-50 dark:border-amber-500/35 dark:bg-amber-500/10 rounded-md p-3"
                          >
                            <div className="flex items-start gap-2">
                              <BarChart3 className="size-3 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
                              <div className="flex-1 min-w-0">
                                <span className="text-[9px] font-mono font-bold uppercase tracking-wider text-amber-800 dark:text-amber-200">
                                  {diag.code.replace(/_/g, ' ')}
                                </span>
                                <p className="text-[9.5px] text-amber-700 dark:text-amber-300 mt-1 leading-relaxed">
                                  {diag.message}
                                </p>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                      <p className="text-[9px] text-muted-foreground italic mt-2">
                        Metrics are unavailable. This does not affect Agent Run lifecycle status.
                      </p>
                    </section>
                    <Separator className="bg-border" />
                  </>
                )
              ) : (
                <>
                  {/* Run Telemetry Diagnostics (from issue, when no fetched metrics) */}
                  {isImplementation && issue.telemetry_diagnostics && issue.telemetry_diagnostics.length > 0 && (
                    <>
                      <section>
                        <h4 className="text-[10px] font-bold uppercase tracking-wider text-amber-600 dark:text-amber-400 mb-2 flex items-center gap-1.5">
                          <AlertTriangle className="size-3" />
                          Run Telemetry
                        </h4>
                        <div className="flex flex-col gap-2">
                          {issue.telemetry_diagnostics.map((diag, idx) => (
                            <div
                              key={idx}
                              className="border border-amber-200 bg-amber-50 dark:border-amber-500/35 dark:bg-amber-500/10 rounded-md p-3"
                            >
                              <div className="flex items-start gap-2">
                                <BarChart3 className="size-3 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
                                <div className="flex-1 min-w-0">
                                  <span className="text-[9px] font-mono font-bold uppercase tracking-wider text-amber-800 dark:text-amber-200">
                                    {diag.code.replace(/_/g, ' ')}
                                  </span>
                                  <p className="text-[9.5px] text-amber-700 dark:text-amber-300 mt-1 leading-relaxed">
                                    {diag.message}
                                  </p>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                        <p className="text-[9px] text-muted-foreground italic mt-2">
                          Metrics are unavailable. This does not affect Agent Run lifecycle status.
                        </p>
                      </section>
                      <Separator className="bg-border" />
                    </>
                  )}

                  {isImplementation && !issue.telemetry_diagnostics && (issue.status === 'running' || issue.status === 'succeeded' || issue.status === 'failed') && (
                    <>
                      <section>
                        <h4 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
                          <BarChart3 className="size-3" />
                          Run Telemetry
                        </h4>
                        <p className="text-[9.5px] text-muted-foreground italic">
                          Telemetry is available for this Agent Run. Detailed metrics can be viewed in the full metrics panel.
                        </p>
                      </section>
                      <Separator className="bg-border" />
                    </>
                  )}
                </>
              )}

              {/* Implementation Issue Metrics (aggregated across attempts) */}
              {isImplementation && implementationIssueMetrics && (
                <>
                  <section>
                    <h4 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
                      <Layers className="size-3" />
                      Implementation Issue Metrics
                    </h4>

                    {/* Summary Card */}
                    <div className="border border-border rounded-md p-3 mb-3 bg-muted/20">
                      <div className="grid grid-cols-2 gap-2">
                        <div className="flex flex-col">
                          <span className="text-[9px] text-muted-foreground uppercase tracking-wider">Attempts</span>
                          <span className="text-sm font-mono font-bold text-foreground">{implementationIssueMetrics.run_count}</span>
                        </div>
                        <div className="flex flex-col">
                          <span className="text-[9px] text-muted-foreground uppercase tracking-wider">Latest Status</span>
                          <span className="text-sm font-mono font-bold capitalize text-foreground">{implementationIssueMetrics.latest_run_status || 'N/A'}</span>
                        </div>
                        <div className="flex flex-col">
                          <span className="text-[9px] text-muted-foreground uppercase tracking-wider">Failures</span>
                          <span className={`text-sm font-mono font-bold ${implementationIssueMetrics.failure_count > 0 ? 'text-destructive' : 'text-foreground'}`}>{implementationIssueMetrics.failure_count}</span>
                        </div>
                        <div className="flex flex-col">
                          <span className="text-[9px] text-muted-foreground uppercase tracking-wider">With Telemetry</span>
                          <span className="text-sm font-mono font-bold text-foreground">{implementationIssueMetrics.runs_with_telemetry} / {implementationIssueMetrics.run_count}</span>
                        </div>
                        <div className="flex flex-col col-span-2">
                          <span className="text-[9px] text-muted-foreground uppercase tracking-wider">End-to-End Success Rate</span>
                          <span className={`text-sm font-mono font-bold ${implementationIssueMetrics.integrated_run_count > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'}`}>
                            {implementationIssueMetrics.run_count > 0
                              ? `${((implementationIssueMetrics.integrated_run_count / implementationIssueMetrics.run_count) * 100).toFixed(0)}% (${implementationIssueMetrics.integrated_run_count} / ${implementationIssueMetrics.run_count} integrated)`
                              : '—'}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Aggregated Model Usage */}
                    {implementationIssueMetrics.metrics_available && (implementationIssueMetrics.input_tokens != null || implementationIssueMetrics.total_tokens != null) && (
                      <div className="mb-3">
                        <h5 className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground mb-1.5">Aggregated Usage</h5>
                        <Table className="border rounded-md border-border">
                          <TableBody>
                            {implementationIssueMetrics.input_tokens != null && (
                              <TableRow className="border-b border-border hover:bg-transparent">
                                <TableCell className="text-muted-foreground text-[10px] font-medium py-1.5">Input Tokens</TableCell>
                                <TableCell className="text-foreground text-[10px] font-mono text-right py-1.5">{implementationIssueMetrics.input_tokens?.toLocaleString()}</TableCell>
                              </TableRow>
                            )}
                            {implementationIssueMetrics.output_tokens != null && (
                              <TableRow className="border-b border-border hover:bg-transparent">
                                <TableCell className="text-muted-foreground text-[10px] font-medium py-1.5">Output Tokens</TableCell>
                                <TableCell className="text-foreground text-[10px] font-mono text-right py-1.5">{implementationIssueMetrics.output_tokens?.toLocaleString()}</TableCell>
                              </TableRow>
                            )}
                            {implementationIssueMetrics.total_tokens != null && (
                              <TableRow className="border-b border-border hover:bg-transparent">
                                <TableCell className="text-muted-foreground text-[10px] font-medium py-1.5">Total Tokens</TableCell>
                                <TableCell className="text-foreground text-[10px] font-mono text-right py-1.5">{implementationIssueMetrics.total_tokens?.toLocaleString()}</TableCell>
                              </TableRow>
                            )}
                            {implementationIssueMetrics.model_cost != null && (
                              <TableRow className="border-b border-border hover:bg-transparent">
                                <TableCell className="text-muted-foreground text-[10px] font-medium py-1.5">Model Cost</TableCell>
                                <TableCell className="text-foreground text-[10px] font-mono text-right py-1.5">${implementationIssueMetrics.model_cost?.toFixed(4)}</TableCell>
                              </TableRow>
                            )}
                            {implementationIssueMetrics.tool_call_count != null && (
                              <TableRow className="border-b border-border hover:bg-transparent">
                                <TableCell className="text-muted-foreground text-[10px] font-medium py-1.5">Tool Calls</TableCell>
                                <TableCell className="text-foreground text-[10px] font-mono text-right py-1.5">{implementationIssueMetrics.tool_call_count?.toLocaleString()}</TableCell>
                              </TableRow>
                            )}
                            {implementationIssueMetrics.tool_error_count != null && (
                              <TableRow className="border-0 hover:bg-transparent">
                                <TableCell className="text-muted-foreground text-[10px] font-medium py-1.5">Tool Errors</TableCell>
                                <TableCell className="text-destructive text-[10px] font-mono text-right py-1.5">{implementationIssueMetrics.tool_error_count?.toLocaleString()}</TableCell>
                              </TableRow>
                            )}
                          </TableBody>
                        </Table>
                      </div>
                    )}

                    {/* Aggregated Responsiveness */}
                    {implementationIssueMetrics.metrics_available && (
                      (implementationIssueMetrics.avg_time_to_first_token_ms != null ||
                       implementationIssueMetrics.avg_latency_ms != null ||
                       implementationIssueMetrics.avg_output_tokens_per_sec != null) && (
                        <div className="mb-3">
                          <h5 className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground mb-1.5">Avg. Responsiveness</h5>
                          <Table className="border rounded-md border-border">
                            <TableBody>
                              {implementationIssueMetrics.avg_time_to_first_token_ms != null && (
                                <TableRow className="border-b border-border hover:bg-transparent">
                                  <TableCell className="text-muted-foreground text-[10px] font-medium py-1.5">Avg TTFT</TableCell>
                                  <TableCell className="text-foreground text-[10px] font-mono text-right py-1.5">{implementationIssueMetrics.avg_time_to_first_token_ms?.toFixed(1)} ms</TableCell>
                                </TableRow>
                              )}
                              {implementationIssueMetrics.avg_latency_ms != null && (
                                <TableRow className="border-b border-border hover:bg-transparent">
                                  <TableCell className="text-muted-foreground text-[10px] font-medium py-1.5">Avg Latency</TableCell>
                                  <TableCell className="text-foreground text-[10px] font-mono text-right py-1.5">{implementationIssueMetrics.avg_latency_ms?.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} ms</TableCell>
                                </TableRow>
                              )}
                              {implementationIssueMetrics.avg_output_tokens_per_sec != null && (
                                <TableRow className="border-0 hover:bg-transparent">
                                  <TableCell className="text-muted-foreground text-[10px] font-medium py-1.5">Avg Tokens/s</TableCell>
                                  <TableCell className="text-foreground text-[10px] font-mono text-right py-1.5">{implementationIssueMetrics.avg_output_tokens_per_sec?.toFixed(1)}</TableCell>
                                </TableRow>
                              )}
                            </TableBody>
                          </Table>
                        </div>
                      )
                    )}

                    {/* Run Attempt History */}
                    {implementationIssueMetrics.runs && implementationIssueMetrics.runs.length > 0 && (
                      <div>
                        <h5 className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground mb-1.5">Attempt History</h5>
                        <Table className="border rounded-md border-border">
                          <TableBody>
                            {implementationIssueMetrics.runs.map((attempt, idx, array) => (
                              <TableRow key={attempt.run_id} className={`${idx === array.length - 1 ? 'border-0' : 'border-b border-border'} hover:bg-transparent`}>
                                <TableCell className="text-[10px] text-muted-foreground font-mono py-1.5">{attempt.run_id}</TableCell>
                                <TableCell className="text-[10px] py-1.5 text-right">
                                  <div className="flex items-center justify-end gap-1.5">
                                    {attempt.has_telemetry_association ? (
                                      <BarChart3 className="size-3 text-emerald-500" />
                                    ) : (
                                      <AlertTriangle className="size-3 text-amber-500" />
                                    )}
                                    {getStatusBadge(attempt.status)}
                                  </div>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    )}

                    {/* Historical runs without telemetry diagnostics */}
                    {implementationIssueMetrics.diagnostics.length > 0 && (
                      <div className="mt-3">
                        <h5 className="text-[9px] font-bold uppercase tracking-wider text-amber-600 dark:text-amber-400 mb-1.5 flex items-center gap-1">
                          <AlertTriangle className="size-2.5" />
                          Telemetry Diagnostics
                        </h5>
                        <div className="flex flex-col gap-1.5">
                          {implementationIssueMetrics.diagnostics.map((diag, di) => (
                            <div key={di} className="border border-amber-200 bg-amber-50 dark:border-amber-500/35 dark:bg-amber-500/10 rounded p-2">
                              <div className="flex items-start gap-1.5">
                                <AlertTriangle className="size-2.5 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
                                <div className="flex-1 min-w-0">
                                  <span className="text-[8px] font-mono font-bold uppercase tracking-wider text-amber-800 dark:text-amber-200">
                                    {diag.code.replace(/_/g, ' ')}
                                  </span>
                                  <p className="text-[8.5px] text-amber-700 dark:text-amber-300 mt-0.5 leading-relaxed">
                                    {diag.message}
                                  </p>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </section>
                  <Separator className="bg-border" />
                </>
              )}

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
