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
  Clock, 
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
        <div className="bg-red-950/30 border border-red-900 rounded-lg p-6 max-w-lg text-center space-y-4">
          <AlertCircle className="size-10 text-red-500 mx-auto" />
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">Readiness Analysis Fault</h3>
          <p className="text-xs text-red-300 font-mono leading-relaxed">{error}</p>
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

  const getStatusBadge = (status: string) => {
    const baseClass = "inline-flex items-center gap-1 font-mono text-[9px] uppercase font-bold tracking-wider px-2 py-0.5 rounded border bg-neutral-100 text-neutral-800 dark:bg-neutral-800 dark:text-neutral-200 border-neutral-200 dark:border-neutral-700";
    
    let dotColor = "bg-neutral-400";
    let isPulse = false;

    switch (status) {
      case 'ready':
        dotColor = "bg-blue-500";
        break;
      case 'claimed':
        dotColor = "bg-cyan-500";
        break;
      case 'running':
        dotColor = "bg-amber-500 animate-pulse";
        isPulse = true;
        break;
      case 'succeeded':
      case 'prepared':
        dotColor = "bg-emerald-500";
        break;
      case 'failed':
        dotColor = "bg-red-500";
        break;
      case 'blocked':
        dotColor = "bg-orange-500";
        break;
      case 'unprepared':
        dotColor = "bg-zinc-500";
        break;
      default:
        dotColor = "bg-zinc-400";
    }

    return (
      <Badge className={`${baseClass} ${isPulse ? 'animate-pulse' : ''}`} variant="outline">
        <span className={`size-1.5 rounded-full ${dotColor}`} />
        {status}
      </Badge>
    );
  };

  return (
    <main className="grow p-6 grid grid-cols-1 xl:grid-cols-3 gap-6 overflow-y-auto max-h-[calc(100vh-140px)]">
      
      {/* LEFT COLUMN: METADATA & CAPACITY */}
      <section className="xl:col-span-1 flex flex-col gap-6">
        
        {/* Configuration Provenance & Harness Variables */}
        <Card className="dashboard-glass-panel border border-zinc-800 bg-[#0d0d0f]/80 select-none">
          <CardHeader className="py-4 border-b border-zinc-900/60 px-5 flex flex-row items-center gap-3">
            <Shield className="size-4 text-teal-400" />
            <div>
              <CardTitle className="text-xs font-bold uppercase tracking-wider text-white">Config Provenance</CardTitle>
              <CardDescription className="text-[10px] text-zinc-500">Repository metadata & harness parameters</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="p-5 space-y-4 text-xs font-mono">
            <div>
              <span className="text-[10px] text-zinc-500 uppercase block mb-1">Observed At</span>
              <span className="text-zinc-200">{observedAt}</span>
            </div>
            
            <div className="border-t border-zinc-900/40 pt-3">
              <span className="text-[10px] text-zinc-500 uppercase block mb-1">Config Source</span>
              <span className="text-zinc-200">{configProvenance?.source || 'N/A'}</span>
            </div>
            
            <div className="border-t border-zinc-900/40 pt-3">
              <span className="text-[10px] text-zinc-500 uppercase block mb-1">Local Repo Path</span>
              <span className="text-zinc-300 break-all select-all font-semibold" title={repo?.path}>{repo?.path || 'N/A'}</span>
            </div>
            
            <div className="border-t border-zinc-900/40 pt-3">
              <span className="text-[10px] text-zinc-500 uppercase block mb-1">Worktree Root</span>
              <span className="text-zinc-300 break-all select-all font-semibold" title={repo?.worktree_root}>{repo?.worktree_root || 'N/A'}</span>
            </div>
            
            <div className="border-t border-zinc-900/40 pt-3">
              <span className="text-[10px] text-zinc-500 uppercase block mb-1">Main Branch</span>
              <div className="flex items-center gap-1.5 text-zinc-200">
                <GitBranch className="size-3 text-teal-500" />
                <span>{repo?.main_branch || 'N/A'}</span>
              </div>
            </div>

            <div className="border-t border-zinc-900/40 pt-3">
              <span className="text-[10px] text-zinc-500 uppercase block mb-1">Default Harness</span>
              <div className="space-y-1.5">
                <div className="flex items-center gap-1.5 text-zinc-200">
                  <Server className="size-3 text-teal-500" />
                  <span>Name: {defaultHarness?.name || 'None'}</span>
                </div>
                <div className="flex items-center gap-1.5 text-zinc-200">
                  <Clock className="size-3 text-teal-500" />
                  <span>Timeout: {defaultHarness?.timeout_seconds ? `${defaultHarness.timeout_seconds}s` : 'Unconfigured'}</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Capacity Limits Card */}
        <Card className="dashboard-glass-panel border border-zinc-800 bg-[#0d0d0f]/80 select-none">
          <CardHeader className="py-4 border-b border-zinc-900/60 px-5 flex flex-row items-center gap-3">
            <Layers className="size-4 text-teal-400" />
            <div>
              <CardTitle className="text-xs font-bold uppercase tracking-wider text-white">Agent Run Capacity</CardTitle>
              <CardDescription className="text-[10px] text-zinc-500">Active claimed/running issues concurrency limit</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="p-5 space-y-4">
            <div className="flex items-baseline justify-between font-mono">
              <span className="text-[10px] text-zinc-500 uppercase">Usage Status</span>
              <span className="text-lg font-bold text-white">
                {capacity.used} <span className="text-zinc-600 text-xs">/</span> {capacity.total} <span className="text-xs font-normal text-zinc-400">runs</span>
              </span>
            </div>

            {/* Capacity Progress Bar */}
            <div className="h-2 w-full bg-zinc-950 border border-zinc-900 rounded-full overflow-hidden">
              <div 
                className={`h-full rounded-full transition-all duration-300 ${
                  capacity.used >= capacity.total && capacity.total > 0 
                    ? 'bg-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.3)]' 
                    : 'bg-teal-500 shadow-[0_0_10px_rgba(20,184,166,0.3)]'
                }`}
                style={{ width: `${capacity.total > 0 ? (capacity.used / capacity.total) * 100 : 0}%` }}
              />
            </div>
            
            <div className="text-[10px] text-zinc-500 font-mono leading-relaxed bg-black/40 rounded p-3 border border-zinc-900/50">
              {capacity.used >= capacity.total && capacity.total > 0 ? (
                <div className="flex items-start gap-2 text-amber-400">
                  <AlertTriangle className="size-3.5 shrink-0 mt-0.5" />
                  <span>Maximum concurrency limit reached. No additional issues will be claimed until active runs finish or release claims.</span>
                </div>
              ) : (
                <div className="flex items-start gap-2 text-zinc-400">
                  <CheckCircle2 className="size-3.5 text-emerald-400 shrink-0 mt-0.5" />
                  <span>Available capacity exists. The Execution Scheduler is eligible to claim Ready Implementation Issues up to the total limit.</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </section>

      {/* RIGHT COLUMN: REPOSITORY CHECKS & GROUPS */}
      <section className="xl:col-span-2 flex flex-col gap-6">
        
        {/* Repository Checks Card */}
        <Card className="dashboard-glass-panel border border-zinc-800 bg-[#0d0d0f]/80">
          <CardHeader className="py-4 border-b border-zinc-900/60 px-5 flex flex-row items-center gap-3">
            <HardDrive className="size-4 text-teal-400" />
            <div>
              <CardTitle className="text-xs font-bold uppercase tracking-wider text-white">Repository Readiness Checks</CardTitle>
              <CardDescription className="text-[10px] text-zinc-500">Scheduler eligibility diagnostics & remediation protocols</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="p-5 space-y-6">
            
            {/* Critical Failures */}
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Badge variant="outline" className="bg-red-950/20 border-red-900/60 text-red-400 text-[10px] uppercase font-bold tracking-wider rounded px-2 py-0.5">
                  Critical Readiness Failures ({criticalFailures.length})
                </Badge>
              </div>
              {criticalFailures.length === 0 ? (
                <div className="flex items-center gap-3 bg-emerald-950/10 border border-emerald-950/60 rounded p-4 text-xs font-mono text-emerald-400">
                  <CheckCircle2 className="size-4 shrink-0 text-emerald-400" />
                  <span>No critical scheduling blockers detected in configuration or credentials.</span>
                </div>
              ) : (
                <div className="space-y-3">
                  {criticalFailures.map((check: any, idx: number) => (
                    <div key={idx} className="bg-red-950/10 border border-red-950/60 rounded p-4 space-y-2 text-xs font-mono">
                      <div className="flex items-start gap-2.5">
                        <AlertCircle className="size-4 text-red-500 shrink-0 mt-0.5" />
                        <div>
                          <strong className="text-white block mb-0.5">{check.message}</strong>
                          {check.details?.code && (
                            <span className="text-[9px] bg-red-950/40 text-red-400 border border-red-900/40 px-1.5 py-0.5 rounded uppercase font-bold tracking-wider">
                              CODE: {check.details.code}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="pl-6 border-l border-zinc-900 space-y-1">
                        <span className="text-[10px] text-zinc-500 uppercase block">Remediation</span>
                        <p className="text-zinc-300 font-sans leading-relaxed">{check.remediation}</p>
                        {check.details?.error && (
                          <div className="bg-black/60 rounded p-2 border border-zinc-900 text-[10px] text-zinc-500 whitespace-pre-wrap overflow-x-auto mt-2">
                            <strong>Diagnostic Context:</strong> {check.details.error}
                          </div>
                        )}
                        {check.details?.path && (
                          <div className="text-[10px] text-zinc-500 mt-1 select-all">
                            <strong>Path:</strong> {check.details.path}
                          </div>
                        )}
                        {check.details?.missing_labels && (
                          <div className="text-[10px] text-zinc-500 mt-1">
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
            <div className="border-t border-zinc-900/60 pt-5">
              <div className="flex items-center gap-2 mb-3">
                <Badge variant="outline" className="bg-amber-950/20 border-amber-900/60 text-amber-400 text-[10px] uppercase font-bold tracking-wider rounded px-2 py-0.5">
                  Readiness Warnings ({warnings.length})
                </Badge>
              </div>
              {warnings.length === 0 ? (
                <div className="flex items-center gap-3 bg-zinc-950/40 border border-zinc-900 rounded p-4 text-xs font-mono text-zinc-500">
                  <CheckCircle2 className="size-4 shrink-0 text-zinc-700" />
                  <span>No degraded repository states or stale issue locks detected.</span>
                </div>
              ) : (
                <div className="space-y-3">
                  {warnings.map((check: any, idx: number) => (
                    <div key={idx} className="bg-amber-950/5 border border-amber-950/30 rounded p-4 space-y-2 text-xs font-mono">
                      <div className="flex items-start gap-2.5">
                        <AlertTriangle className="size-4 text-amber-500 shrink-0 mt-0.5" />
                        <div>
                          <strong className="text-zinc-200 block mb-0.5">{check.message}</strong>
                          {check.details?.code && (
                            <span className="text-[9px] bg-amber-950/30 text-amber-400 border border-amber-900/30 px-1.5 py-0.5 rounded uppercase font-bold tracking-wider">
                              CODE: {check.details.code}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="pl-6 border-l border-zinc-900 space-y-1">
                        <span className="text-[10px] text-zinc-500 uppercase block">Remediation</span>
                        <p className="text-zinc-400 font-sans leading-relaxed">{check.remediation}</p>
                        {check.details?.issue_number && (
                          <div className="text-[10px] text-zinc-500 mt-1">
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
        <Card className="dashboard-glass-panel border border-zinc-800 bg-[#0d0d0f]/80">
          <CardHeader className="py-4 border-b border-zinc-900/60 px-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <CardTitle className="text-xs font-bold uppercase tracking-wider text-white flex items-center gap-2">
                <Layers className="size-4 text-teal-400" />
                Repository Issues Matrix
              </CardTitle>
              <CardDescription className="text-[10px] text-zinc-500 mt-0.5">
                High-density, multi-type repository issue database and scheduler control
              </CardDescription>
            </div>
            
            {/* Search filter input */}
            <div className="relative w-full md:w-[260px]">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3 text-zinc-500" />
              <input
                type="text"
                placeholder="Search by title or #ID..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-8 pr-3 py-1 text-xs bg-zinc-950 border border-zinc-900 rounded text-zinc-300 placeholder-zinc-500 focus:outline-none focus:border-teal-500 transition-all font-mono"
              />
            </div>
          </CardHeader>
          
          <div className="px-5 py-3 border-b border-zinc-900/40 bg-black/20 flex flex-wrap items-center gap-1.5">
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
                  className={`text-[9.5px] uppercase font-bold tracking-wider px-2 h-7 transition-all ${
                    isActive 
                      ? 'bg-zinc-100 text-zinc-950 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-white dark:hover:bg-zinc-700' 
                      : 'text-zinc-500 border-zinc-900 bg-zinc-950 hover:text-zinc-300 hover:bg-zinc-900/40'
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
                  <div className="text-center py-12 text-zinc-600 font-mono text-xs">
                    No issues found matching the active filter and search query.
                  </div>
                );
              }

              return (
                <Table>
                  <TableHeader className="bg-zinc-950/60 border-b border-zinc-900">
                    <TableRow className="hover:bg-transparent border-zinc-900">
                      <TableHead className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider pl-5 py-3">ID</TableHead>
                      <TableHead className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider py-3">Type</TableHead>
                      <TableHead className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider py-3">Title</TableHead>
                      <TableHead className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider py-3">Status</TableHead>
                      <TableHead className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider py-3">Connection / Branch</TableHead>
                      <TableHead className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider pr-5 py-3 text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredRows.map((row) => {
                      const isPrd = row.type === 'PRD';
                      return (
                        <TableRow 
                          key={row.id}
                          className="hover:bg-zinc-900/40 border-zinc-900/40 cursor-pointer transition-colors group"
                          onClick={() => onIssueClick?.(row.id)}
                        >
                          <TableCell className="font-mono text-xs text-zinc-400 pl-5 py-3.5">
                            #{row.id}
                          </TableCell>
                          <TableCell className="py-3.5">
                            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded font-sans uppercase tracking-wider ${
                              isPrd 
                                ? 'bg-zinc-800/60 text-zinc-400 border border-zinc-700/30' 
                                : 'bg-teal-950/40 text-teal-400 border border-teal-900/30'
                            }`}>
                              {row.type}
                            </span>
                          </TableCell>
                          <TableCell className="py-3.5 max-w-[320px]">
                            <div className="flex flex-col gap-1">
                              <span className={`text-xs font-semibold leading-tight transition-colors group-hover:text-teal-400 font-sans ${
                                isPrd ? 'text-white font-bold' : 'text-zinc-300'
                              }`}>
                                {row.title}
                              </span>
                              
                              {/* Dependencies inline for Implementation Issues */}
                              {!isPrd && row.blockedBy && row.blockedBy.length > 0 && (
                                <div className="flex flex-wrap items-center gap-1.5 mt-1 font-mono text-[9px]">
                                  <span className="text-zinc-500 uppercase font-bold tracking-wider">Blocked By:</span>
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
                                          className={`inline-flex items-center gap-1 px-1.5 py-0.2 rounded border text-[9px] font-bold ${
                                            isActiveBlocker 
                                              ? 'bg-orange-950/20 border-orange-900/40 text-orange-400 hover:text-orange-350 hover:bg-orange-950/40' 
                                              : 'bg-zinc-950 border-zinc-900 text-zinc-650 hover:text-zinc-400 hover:bg-zinc-900'
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
                              <span className="text-zinc-600 italic">PRD Level</span>
                            ) : row.branch ? (
                              <div className="flex items-center gap-1.5 text-zinc-400">
                                <GitBranch className="size-3 text-zinc-650 shrink-0" />
                                <span className="truncate" title={row.branch}>{row.branch}</span>
                              </div>
                            ) : row.parentPrdNumber ? (
                              <div 
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onIssueClick?.(row.parentPrdNumber);
                                }}
                                className="flex items-center gap-1 text-zinc-500 hover:text-teal-400 transition-colors"
                              >
                                <ChevronRight className="size-3 text-zinc-700 shrink-0" />
                                <span>PRD #{row.parentPrdNumber}</span>
                              </div>
                            ) : (
                              <span className="text-zinc-600">-</span>
                            )}
                          </TableCell>
                          <TableCell className="pr-5 py-3.5 text-right">
                            <Button 
                              variant="outline" 
                              size="xs" 
                              className="h-7 text-[9.5px] uppercase font-bold tracking-wider px-2 font-sans hover:bg-zinc-900 border-zinc-900 hover:border-zinc-800"
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
