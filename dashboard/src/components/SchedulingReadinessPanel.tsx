import { useEffect, useState } from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from '@/components/ui/table';
import { 
  AlertCircle, 
  AlertTriangle, 
  CheckCircle2, 
  GitBranch, 
  Server, 
  Layers, 
  HardDrive, 
  Shield,
  Search,
  ChevronRight
} from 'lucide-react';

export interface SchedulingReadinessPanelProps {
  repoName: string;
  apiBase: string;
  onIssueClick?: (issueNumber: number) => void;
}

export default function SchedulingReadinessPanel({ repoName, apiBase, onIssueClick }: SchedulingReadinessPanelProps) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [activeFilterTab, setActiveFilterTab] = useState<string>('all');

  useEffect(() => {
    let active = true;
    const fetchReadiness = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${apiBase}/api/scheduling-readiness/${encodeURIComponent(repoName)}`);
        if (!res.ok) throw new Error(`HTTP error ${res.status}`);
        const result = await res.json();
        if (active) {
          setData(result);
        }
      } catch (err: any) {
        console.error("Error loading readiness snapshot:", err);
        if (active) {
          setError(err.message || 'Failed to fetch scheduling readiness data');
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    
    fetchReadiness();
    
    return () => {
      active = false;
    };
  }, [repoName, apiBase]);

  if (loading) {
    return (
      <div className="grow p-6 grid grid-cols-1 lg:grid-cols-3 gap-6 overflow-hidden">
        <div className="lg:col-span-1 flex flex-col gap-6">
          <div className="flex flex-col gap-3 p-5 border border-border rounded-xl">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-5/6" />
            <Skeleton className="h-3 w-2/3" />
          </div>
          <div className="flex flex-col gap-3 p-5 border border-border rounded-xl">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-5/6" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        </div>
        <div className="lg:col-span-2 flex flex-col gap-6">
          <div className="flex flex-col gap-3 p-5 border border-border rounded-xl">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-5/6" />
            <Skeleton className="h-3 w-2/3" />
          </div>
          <div className="flex flex-col gap-3 p-5 border border-border rounded-xl">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-5/6" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="grow p-6 flex items-center justify-center">
        <div className="max-w-lg rounded-lg border border-red-200 bg-red-50 p-6 text-center dark:border-red-500/35 dark:bg-red-500/10">
          <AlertCircle className="mx-auto mb-4 size-10 text-red-700 dark:text-red-300" />
          <h3 className="text-sm font-bold uppercase tracking-wider text-red-950 dark:text-red-200">Readiness Analysis Fault</h3>
          <p className="mt-4 text-xs font-mono leading-relaxed text-red-900 dark:text-red-300">{error}</p>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const { repo, snapshot } = data;
  const observedAt = snapshot?.observed_at ? new Date(snapshot.observed_at).toLocaleString() : 'N/A';
  const configProvenance = snapshot?.config_provenance;
  const defaultHarness = configProvenance?.default_harness;
  const criticalFailures = snapshot?.readiness_checks?.critical_failures || [];
  const warnings = snapshot?.readiness_checks?.warnings || [];
  const issueState = snapshot?.implementation_issue_state || {};
  const capacity = issueState?.agent_run_capacity || { used: 0, total: 0 };
  const groups = issueState?.groups || [];
  const capacityPercent = capacity.total > 0 ? Math.round((capacity.used / capacity.total) * 100) : 0;

  const getStatusBadge = (status: string) => {
    const baseClass = "inline-flex items-center gap-1 font-mono text-[9px] uppercase font-bold tracking-wider px-2 py-0.5 rounded border";
    const statusStyle = (() => {
      switch (status) {
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
        case 'prepared':
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
        {status}
      </Badge>
    );
  };

  return (
    <main className="grow overflow-y-auto px-6 py-6">
      <section className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        
        <Card className="border bg-card shadow-sm">
          <CardHeader className="grid-cols-[1fr_auto] px-6">
            <div>
              <CardTitle className="text-base font-semibold">Repository Summary</CardTitle>
              <CardDescription>Observed at {observedAt}</CardDescription>
            </div>
            <Shield className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="flex flex-col gap-3 px-6 text-sm">
            <div className="grid gap-1">
              <span className="text-xs text-muted-foreground">Config Source</span>
              <span className="font-medium">{configProvenance?.source || 'N/A'}</span>
            </div>
            <div className="grid gap-1">
              <span className="text-xs text-muted-foreground">Local Repo Path</span>
              <span className="break-all font-mono text-xs font-medium" title={repo?.path}>{repo?.path || 'N/A'}</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <GitBranch className="size-4 text-muted-foreground" />
              <span className="font-medium">Main branch</span>
              <span className="font-mono text-xs text-muted-foreground">
                <span>{repo?.main_branch || 'N/A'}</span>
              </span>
            </div>
          </CardContent>
        </Card>

        <Card className="border bg-card shadow-sm">
          <CardHeader className="grid-cols-[1fr_auto] px-6">
            <div>
              <CardTitle className="text-base font-semibold">Agent Run Capacity</CardTitle>
              <CardDescription>Concurrency limit and active usage</CardDescription>
            </div>
            <Layers className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="space-y-4 px-6">
            <div className="flex items-baseline justify-between font-mono">
              <span className="text-xs text-muted-foreground">Usage Status</span>
              <span className="text-2xl font-semibold">
                {capacity.used}<span className="text-sm text-muted-foreground">/{capacity.total}</span>
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div 
                className="h-full rounded-full bg-primary transition-all duration-300"
                style={{ width: `${capacityPercent}%` }}
              />
            </div>
            <p className="text-sm text-muted-foreground">
              {capacity.used >= capacity.total && capacity.total > 0
                ? 'Maximum concurrency reached. New claims wait for active runs to finish.'
                : 'Capacity is available for ready implementation issues.'}
            </p>
          </CardContent>
        </Card>

        <Card className="border bg-card shadow-sm">
          <CardHeader className="grid-cols-[1fr_auto] px-6">
            <div>
              <CardTitle className="text-base font-semibold">Harness</CardTitle>
              <CardDescription>Default execution parameters</CardDescription>
            </div>
            <Server className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="flex flex-col gap-3 px-6 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Name</span>
              <span className="font-mono text-xs font-medium">{defaultHarness?.name || 'None'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Timeout</span>
              <span className="font-mono text-xs font-medium">
                {defaultHarness?.timeout_seconds ? `${defaultHarness.timeout_seconds}s` : 'Unconfigured'}
              </span>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="flex flex-col gap-6">
        
        {/* Repository Checks Card */}
        <Card className="dashboard-glass-panel border border-border bg-card text-card-foreground">
          <CardHeader className="py-4 border-b border-border px-5 flex flex-row items-center gap-3">
            <HardDrive className="size-4 text-muted-foreground" />
            <div>
              <CardTitle className="text-xs font-bold uppercase tracking-wider text-foreground">Repository Readiness Checks</CardTitle>
              <CardDescription className="text-[10px] text-muted-foreground">Scheduler eligibility diagnostics & remediation protocols</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="p-5 space-y-6">
            
            {/* Critical Failures */}
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Badge variant="outline" className="rounded border-red-200 bg-red-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-red-900 dark:border-red-500/35 dark:bg-red-500/10 dark:text-red-300">
                  Critical Readiness Failures ({criticalFailures.length})
                </Badge>
              </div>
              {criticalFailures.length === 0 ? (
                <div className="flex items-center gap-3 rounded border border-emerald-200 bg-emerald-50 p-4 font-mono text-xs text-emerald-900 dark:border-emerald-500/35 dark:bg-emerald-500/10 dark:text-emerald-300">
                  <CheckCircle2 className="size-4 shrink-0 text-emerald-700 dark:text-emerald-300" />
                  <span>No critical scheduling blockers detected in configuration or credentials.</span>
                </div>
              ) : (
                <div className="space-y-3">
                  {criticalFailures.map((check: any, idx: number) => (
                    <div key={idx} className="space-y-2 rounded border border-red-200 bg-red-50 p-4 font-mono text-xs dark:border-red-500/35 dark:bg-red-500/10">
                      <div className="flex items-start gap-2.5">
                        <AlertCircle className="mt-0.5 size-4 shrink-0 text-red-700 dark:text-red-300" />
                        <div>
                          <strong className="text-foreground block mb-0.5">{check.message}</strong>
                          {check.details?.code && (
                            <span className="rounded border border-red-200 bg-background px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-red-900 dark:border-red-500/35 dark:bg-red-500/10 dark:text-red-300">
                              CODE: {check.details.code}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="pl-6 border-l border-border space-y-1">
                        <span className="text-[10px] text-muted-foreground uppercase block">Remediation</span>
                        <p className="text-muted-foreground font-sans leading-relaxed">{check.remediation}</p>
                        {check.details?.error && (
                          <div className="bg-muted/40 rounded p-2 border border-border text-[10px] text-muted-foreground whitespace-pre-wrap overflow-x-auto mt-2">
                            <strong>Diagnostic Context:</strong> {check.details.error}
                          </div>
                        )}
                        {check.details?.path && (
                          <div className="text-[10px] text-muted-foreground mt-1 select-all">
                            <strong>Path:</strong> {check.details.path}
                          </div>
                        )}
                        {check.details?.missing_labels && (
                          <div className="text-[10px] text-muted-foreground mt-1">
                            <strong>Missing Labels:</strong> {check.details.missing_labels.join(', ')}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Warnings */}
            <div className="border-t border-border pt-5">
              <div className="flex items-center gap-2 mb-3">
                <Badge variant="outline" className="rounded border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-900 dark:border-amber-500/35 dark:bg-amber-500/10 dark:text-amber-300">
                  Readiness Warnings ({warnings.length})
                </Badge>
              </div>
              {warnings.length === 0 ? (
                <div className="flex items-center gap-3 bg-muted/40 border border-border rounded p-4 text-xs font-mono text-muted-foreground">
                  <CheckCircle2 className="size-4 shrink-0 text-muted-foreground" />
                  <span>No degraded repository states or stale issue locks detected.</span>
                </div>
              ) : (
                <div className="space-y-3">
                  {warnings.map((check: any, idx: number) => (
                    <div key={idx} className="space-y-2 rounded border border-amber-200 bg-amber-50 p-4 font-mono text-xs dark:border-amber-500/35 dark:bg-amber-500/10">
                      <div className="flex items-start gap-2.5">
                        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-700 dark:text-amber-300" />
                        <div>
                          <strong className="text-foreground block mb-0.5">{check.message}</strong>
                          {check.details?.code && (
                            <span className="rounded border border-amber-200 bg-background px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-amber-900 dark:border-amber-500/35 dark:bg-amber-500/10 dark:text-amber-300">
                              CODE: {check.details.code}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="pl-6 border-l border-border space-y-1">
                        <span className="text-[10px] text-muted-foreground uppercase block">Remediation</span>
                        <p className="text-muted-foreground font-sans leading-relaxed">{check.remediation}</p>
                        {check.details?.issue_number && (
                          <div className="text-[10px] text-muted-foreground mt-1">
                            <strong>Target Issue:</strong> #{check.details.issue_number}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Repository Issues Matrix */}
        <Card className="dashboard-glass-panel border border-border bg-card text-card-foreground">
          <CardHeader className="py-4 border-b border-border px-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <CardTitle className="text-xs font-bold uppercase tracking-wider text-foreground flex items-center gap-2">
                <Layers className="size-4 text-muted-foreground" />
                Repository Issues Matrix
              </CardTitle>
              <CardDescription className="text-[10px] text-muted-foreground mt-0.5">
                High-density, multi-type repository issue database and scheduler control
              </CardDescription>
            </div>
            
            {/* Search filter input */}
            <div className="relative w-full md:w-[260px]">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search by title or #ID..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-8 pr-3 py-1 text-xs bg-muted border border-border rounded text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary transition-all font-mono"
              />
            </div>
          </CardHeader>
          
          <div className="px-5 py-3 border-b border-border bg-muted/10 flex flex-wrap items-center gap-1.5">
            {[
              { id: 'all', label: 'All' },
              { id: 'all_prds', label: 'All PRDs' },
              { id: 'ready', label: 'Ready for Execution' },
              { id: 'active', label: 'Active Claims' },
              { id: 'failed', label: 'Failed Runs' },
              { id: 'integrated', label: 'Integrated' }
            ].map((tab) => {
              const isActive = activeFilterTab === tab.id;
              return (
                <Button
                  key={tab.id}
                  variant={isActive ? "default" : "outline"}
                  size="xs"
                  onClick={() => setActiveFilterTab(tab.id)}
                  className={`text-[9.5px] uppercase font-bold tracking-wider px-2 h-7 transition-all border ${
                    isActive 
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'text-muted-foreground border-border bg-muted hover:text-foreground hover:bg-muted/60'
                  }`}
                >
                  {tab.label}
                </Button>
              );
            })}
          </div>

          <CardContent className="p-0">
            {(() => {
              const allRows: any[] = [];
              groups.forEach((group: any) => {
                const prd = group.parent_prd;
                allRows.push({
                  id: prd.issue_number,
                  title: prd.title,
                  type: 'PRD',
                  status: prd.prepared ? 'prepared' : 'unprepared',
                  rawData: prd
                });
                
                const items = group.items || [];
                items.forEach((item: any) => {
                  allRows.push({
                    id: item.issue_number,
                    title: item.title,
                    type: 'Implementation',
                    status: item.status,
                    branch: item.implementation_branch,
                    parentPrdNumber: prd.issue_number,
                    parentPrdTitle: prd.title,
                    blockedBy: item.blocked_by,
                    activeBlockers: item.active_blockers,
                    rawData: item
                  });
                });
              });

              const filteredRows = allRows.filter(row => {
                // Search filter
                const matchesSearch = row.title.toLowerCase().includes(searchTerm.toLowerCase()) || 
                                      `#${row.id}`.includes(searchTerm);
                if (!matchesSearch) return false;

                // Tab filter
                if (activeFilterTab === 'all') return true;
                if (activeFilterTab === 'all_prds') return row.type === 'PRD';
                if (activeFilterTab === 'ready') return row.type === 'Implementation' && row.status === 'ready';
                if (activeFilterTab === 'active') return row.type === 'Implementation' && (row.status === 'claimed' || row.status === 'running');
                if (activeFilterTab === 'failed') return row.type === 'Implementation' && row.status === 'failed';
                if (activeFilterTab === 'integrated') return row.type === 'Implementation' && row.status === 'succeeded';
                
                return true;
              });

              if (filteredRows.length === 0) {
                return (
                  <div className="text-center py-12 text-muted-foreground font-mono text-xs">
                    No issues found matching the active filter and search query.
                  </div>
                );
              }

              return (
                <Table>
                  <TableHeader className="bg-muted/30 border-b border-border">
                    <TableRow className="hover:bg-transparent border-border">
                      <TableHead className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider pl-5 py-3">ID</TableHead>
                      <TableHead className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider py-3">Type</TableHead>
                      <TableHead className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider py-3">Title</TableHead>
                      <TableHead className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider py-3">Status</TableHead>
                      <TableHead className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider py-3">Connection / Branch</TableHead>
                      <TableHead className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider pr-5 py-3 text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredRows.map((row) => {
                      const isPrd = row.type === 'PRD';
                      return (
                        <TableRow 
                          key={row.id}
                          className="hover:bg-muted/40 border-b border-border/40 cursor-pointer transition-colors group"
                          onClick={() => onIssueClick?.(row.id)}
                        >
                          <TableCell className="font-mono text-xs text-muted-foreground pl-5 py-3.5">
                            #{row.id}
                          </TableCell>
                          <TableCell className="py-3.5">
                            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded font-sans uppercase tracking-wider ${
                              isPrd 
                                ? 'bg-muted text-muted-foreground border border-border'
                                : 'bg-primary/10 text-primary border border-primary/20'
                            }`}>
                              {row.type}
                            </span>
                          </TableCell>
                          <TableCell className="py-3.5 max-w-[320px]">
                            <div className="flex flex-col gap-1">
                              <span className={`text-xs font-semibold leading-tight transition-colors group-hover:text-primary font-sans ${
                                isPrd ? 'text-foreground font-bold' : 'text-muted-foreground'
                              }`}>
                                {row.title}
                              </span>
                              
                              {/* Dependencies inline for Implementation Issues */}
                              {!isPrd && row.blockedBy && row.blockedBy.length > 0 && (
                                <div className="flex flex-wrap items-center gap-1.5 mt-1 font-mono text-[9px]">
                                  <span className="text-muted-foreground uppercase font-bold tracking-wider">Blocked By:</span>
                                  <div className="flex flex-wrap gap-1">
                                    {row.blockedBy.map((blockerNum: number) => {
                                      const isActiveBlocker = row.activeBlockers?.includes(blockerNum);
                                      return (
                                        <span 
                                          key={blockerNum} 
                                          onClick={(e) => {
                                            e.stopPropagation();
                                            onIssueClick?.(blockerNum);
                                          }}
                                          className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] font-bold ${
                                            isActiveBlocker 
                                              ? 'border-orange-200 bg-orange-50 text-orange-900 hover:bg-orange-100 dark:border-orange-500/35 dark:bg-orange-500/10 dark:text-orange-300 dark:hover:bg-orange-500/20'
                                              : 'bg-muted border-border text-muted-foreground hover:text-foreground hover:bg-muted/80'
                                          }`}
                                        >
                                          #{blockerNum} {isActiveBlocker ? 'Open' : 'Resolved'}
                                        </span>
                                      );
                                    })}
                                  </div>
                                </div>
                              )}
                            </div>
                          </TableCell>
                          <TableCell className="py-3.5">
                            {getStatusBadge(row.status)}
                          </TableCell>
                          <TableCell className="py-3.5 max-w-[200px] truncate font-mono text-[10.5px]">
                            {isPrd ? (
                              <span className="text-muted-foreground/60 italic">PRD Level</span>
                            ) : row.branch ? (
                              <div className="flex items-center gap-1.5 text-muted-foreground">
                                <GitBranch className="size-3 text-muted-foreground/50 shrink-0" />
                                <span className="truncate" title={row.branch}>{row.branch}</span>
                              </div>
                            ) : row.parentPrdNumber ? (
                              <div 
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onIssueClick?.(row.parentPrdNumber);
                                }}
                                className="flex items-center gap-1 text-muted-foreground hover:text-primary transition-colors"
                              >
                                <ChevronRight className="size-3 text-muted-foreground/40 shrink-0" />
                                <span>PRD #{row.parentPrdNumber}</span>
                              </div>
                            ) : (
                              <span className="text-muted-foreground/45">-</span>
                            )}
                          </TableCell>
                          <TableCell className="pr-5 py-3.5 text-right">
                            <Button 
                              variant="outline" 
                              size="xs" 
                              className="h-7 text-[9.5px] uppercase font-bold tracking-wider px-2 font-sans hover:bg-muted border-border"
                              onClick={(e) => {
                                e.stopPropagation();
                                onIssueClick?.(row.id);
                              }}
                            >
                              Details
                            </Button>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              );
            })()}
          </CardContent>
        </Card>

      </section>
      
    </main>
  );
}
