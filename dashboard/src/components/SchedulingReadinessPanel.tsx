import { useEffect, useState } from 'react';
import { ShimmerText, ShimmerCard } from '@/components/Shimmer';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { AlertCircle, AlertTriangle, CheckCircle2, Clock, GitBranch, Server, Layers, HardDrive, Shield } from 'lucide-react';
import DependencyPipeline from '@/components/DependencyPipeline';

export interface SchedulingReadinessPanelProps {
  repoName: string;
  apiBase: string;
}

export default function SchedulingReadinessPanel({ repoName, apiBase }: SchedulingReadinessPanelProps) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

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
      <div className="grow p-6 grid grid-cols-1 lg:grid-cols-3 gap-6 overflow-hidden animate-pulse">
        <div className="lg:col-span-1 space-y-6">
          <ShimmerCard />
          <ShimmerCard />
        </div>
        <div className="lg:col-span-2 space-y-6">
          <ShimmerCard />
          <ShimmerCard />
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
    switch (status) {
      case 'ready':
        return <Badge className="bg-blue-950/80 border-blue-900 text-blue-400 font-mono text-[9px] uppercase">Ready</Badge>;
      case 'claimed':
        return <Badge className="bg-cyan-950/80 border-cyan-900 text-cyan-400 font-mono text-[9px] uppercase">Claimed</Badge>;
      case 'running':
        return <Badge className="bg-amber-950/80 border-amber-900 text-amber-400 font-mono text-[9px] uppercase animate-pulse">Running</Badge>;
      case 'succeeded':
        return <Badge className="bg-emerald-950/80 border-emerald-900 text-emerald-400 font-mono text-[9px] uppercase">Succeeded</Badge>;
      case 'failed':
        return <Badge className="bg-red-950/80 border-red-900 text-red-400 font-mono text-[9px] uppercase">Failed</Badge>;
      case 'blocked':
        return <Badge className="bg-orange-950/80 border-orange-900 text-orange-400 font-mono text-[9px] uppercase">Blocked</Badge>;
      default:
        return <Badge className="bg-zinc-950/80 border-zinc-900 text-zinc-400 font-mono text-[9px] uppercase">{status}</Badge>;
    }
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

        {/* Grouped Issues Card */}
        <Card className="dashboard-glass-panel border border-zinc-800 bg-[#0d0d0f]/80">
          <CardHeader className="py-4 border-b border-zinc-900/60 px-5">
            <CardTitle className="text-xs font-bold uppercase tracking-wider text-white flex items-center gap-2">
              <Layers className="size-4 text-teal-400" />
              Open Issues Grouped by Parent PRD
            </CardTitle>
            <CardDescription className="text-[10px] text-zinc-500">
              Visual dependency topological ordering and status alignment
            </CardDescription>
          </CardHeader>
          <CardContent className="p-5">
            {groups.length === 0 ? (
              <div className="text-center py-12 text-zinc-600 font-mono text-xs">
                No open implementation issue groups registered.
              </div>
            ) : (
              <div className="space-y-6">
                {groups.map((group: any) => {
                  const prd = group.parent_prd;
                  const items = group.items || [];
                  const pipelineNodes = items.map((item: any) => ({
                    number: item.issue_number,
                    status: item.status,
                    blocked_by: item.blocked_by,
                    active_blockers: item.active_blockers
                  }));

                  return (
                    <div 
                      key={prd.issue_number}
                      className="border border-zinc-900 bg-black/30 rounded-lg overflow-hidden"
                    >
                      {/* Parent PRD Header */}
                      <div className="bg-[#121215]/80 px-4 py-3 border-b border-zinc-900 flex flex-col md:flex-row md:items-center justify-between gap-2 font-mono text-xs">
                        <div className="flex items-center gap-2">
                          <span className="bg-zinc-900 border border-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded font-bold">
                            PRD #{prd.issue_number}
                          </span>
                          <span className="text-white font-bold font-sans truncate max-w-[280px]" title={prd.title}>
                            {prd.title}
                          </span>
                        </div>
                        <div>
                          {prd.prepared ? (
                            <Badge className="bg-emerald-950/60 border-emerald-900 text-emerald-400 font-semibold font-mono uppercase text-[9px] tracking-wider">Prepared</Badge>
                          ) : (
                            <Badge className="bg-zinc-950/80 border-zinc-955 text-zinc-500 font-semibold font-mono uppercase text-[9px] tracking-wider">Unprepared</Badge>
                          )}
                        </div>
                      </div>

                      {/* Dependency Pipeline Map */}
                      {pipelineNodes.length > 0 && (
                        <div className="px-4 py-2 border-b border-zinc-900/60 bg-black/10">
                          <DependencyPipeline children={pipelineNodes} />
                        </div>
                      )}

                      {/* Child Slices List */}
                      <div className="divide-y divide-zinc-900 bg-black/40 font-mono text-xs">
                        {items.length === 0 ? (
                          <div className="p-4 text-center text-[10px] text-zinc-600">
                            No implementation issue slices listed under this PRD.
                          </div>
                        ) : (
                          items.map((c: any) => (
                            <div key={c.issue_number} className="p-3.5 flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                              <div className="space-y-1.5 max-w-[480px]">
                                <div className="flex items-baseline gap-2">
                                  <span className="text-zinc-500 font-bold">#{c.issue_number}</span>
                                  <span className="text-zinc-300 font-semibold font-sans">{c.title}</span>
                                </div>
                                
                                {/* Blocking Dependencies display */}
                                {c.blocked_by && c.blocked_by.length > 0 && (
                                  <div className="flex flex-wrap items-center gap-1.5 text-[9.5px]">
                                    <span className="text-zinc-500 uppercase font-bold tracking-wider">Blocked By:</span>
                                    <div className="flex flex-wrap gap-1">
                                      {c.blocked_by.map((blockerNum: number) => {
                                        const isActiveBlocker = c.active_blockers?.includes(blockerNum);
                                        return (
                                          <span 
                                            key={blockerNum} 
                                            className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[9px] font-bold ${
                                              isActiveBlocker 
                                                ? 'bg-orange-950/20 border-orange-900/40 text-orange-400' 
                                                : 'bg-zinc-950 border-zinc-900 text-zinc-600'
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

                              <div className="shrink-0 flex items-start">
                                {getStatusBadge(c.status)}
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

      </section>
      
    </main>
  );
}
