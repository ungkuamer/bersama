import { ChevronRight, RefreshCw, Pause, Play, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription, AlertAction } from '@/components/ui/alert'

interface HeaderProps {
  isCollapsed: boolean;
  setIsCollapsed: (collapsed: boolean) => void;
  activeTab: 'readiness' | 'operator';
  activeRunsCount: number;
  readyIssuesCount: number;
  failedRunsCount: number;
  refreshing: boolean;
  pollingActive: boolean;
  setPollingActive: (active: boolean) => void;
  fetchData: (showRefreshIndicator?: boolean) => Promise<void>;
  error: string | null;
  onRetryConnection: () => void;
}

export default function Header({
  isCollapsed,
  setIsCollapsed,
  activeTab,
  activeRunsCount,
  readyIssuesCount,
  failedRunsCount,
  refreshing,
  pollingActive,
  setPollingActive,
  fetchData,
  error,
  onRetryConnection,
}: HeaderProps) {
  return (
    <div className="flex flex-col sticky top-0 z-50 bg-background/95 backdrop-blur-md">
      {/* Top Banner Status Bar */}
      <header className="dashboard-glass-panel border-b px-6 py-4 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div className="flex items-center gap-3">
          {isCollapsed && (
            <button 
              onClick={() => setIsCollapsed(false)}
              className="p-1 rounded bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700 transition mr-2 cursor-pointer"
              title="Expand Sidebar"
            >
              <ChevronRight className="size-4" />
            </button>
          )}
          <div>
            <h1 className="text-xs font-bold text-zinc-400 tracking-widest uppercase flex items-center gap-2 select-none">
              Workspace <span className="text-zinc-700">//</span> <span className="text-white">{activeTab === 'readiness' ? 'Pre-Flight Validation' : 'Operations Command'}</span>
            </h1>
            <p className="text-[10px] text-zinc-500 tracking-tight select-none">
              {activeTab === 'readiness' ? 'Observed parameters & validation metrics' : 'Active agent runs & lifecycle mutations'}
            </p>
          </div>
        </div>

        {/* Global Statistics Panel */}
        <div className="flex flex-wrap items-center gap-4 text-xs">
          {/* Quick Metrics */}
          <div className="dashboard-glass-surface flex items-center gap-3 border rounded px-3 py-1 text-[11px]">
            <div className="flex items-center gap-1.5 border-r border-border pr-3">
              <span className="size-1.5 rounded-full bg-amber-500 animate-pulse"></span>
              <span className="text-zinc-400">ACTIVE RUNS:</span>
              <span className="text-foreground font-bold">{activeRunsCount}</span>
            </div>
            <div className="flex items-center gap-1.5 border-r border-border pr-3">
              <span className="size-1.5 rounded-full bg-blue-500"></span>
              <span className="text-zinc-400">READY ISSUES:</span>
              <span className="text-foreground font-bold">{readyIssuesCount}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="size-1.5 rounded-full bg-red-500"></span>
              <span className="text-zinc-400">FAILED RUNS:</span>
              <span className="text-foreground font-bold">{failedRunsCount}</span>
            </div>
          </div>

          {/* Refresh / Polling controls using clean neutral buttons */}
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="xs"
              onClick={() => fetchData(true)}
              disabled={refreshing}
              title="Manual Sync"
              className="dashboard-focus border-zinc-800 text-zinc-400 hover:text-white"
            >
              <RefreshCw className={`size-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            </Button>
            <span className="text-[10px] text-zinc-650">|</span>
            <Button
              variant="outline"
              size="xs"
              onClick={() => setPollingActive(!pollingActive)}
              className="dashboard-focus border-zinc-800 text-zinc-400 hover:text-white flex items-center gap-1.5"
            >
              {pollingActive ? (
                <>
                  <Pause className="size-3 text-emerald-400" />
                  <span className="text-[10px] font-mono tracking-wider font-semibold">AUTO SYNC ON</span>
                </>
              ) : (
                <>
                  <Play className="size-3 text-zinc-500" />
                  <span className="text-[10px] font-mono tracking-wider font-semibold text-zinc-500">AUTO SYNC OFF</span>
                </>
              )}
            </Button>
          </div>
        </div>
      </header>

      {/* Critical Connection Alerts using standard shadcn Alert block */}
      {error && (
        <div className="px-6 py-2.5 bg-background border-b border-destructive/20">
          <Alert variant="destructive" role="none" className="relative pr-36">
            <AlertCircle className="size-4 text-destructive shrink-0 mt-0.5" />
            <div>
              <AlertTitle className="text-xs font-mono font-bold tracking-wider leading-none mb-1">
                SYSTEM FAULT:
              </AlertTitle>
              <AlertDescription className="text-xs font-mono text-destructive/90 break-words pr-4">
                {error}
              </AlertDescription>
            </div>
            <AlertAction className="absolute top-1/2 -translate-y-1/2 right-3">
              <Button 
                onClick={onRetryConnection}
                variant="destructive"
                size="xs"
                className="uppercase tracking-wider font-mono font-semibold text-[10px]"
              >
                Retry Connection
              </Button>
            </AlertAction>
          </Alert>
        </div>
      )}
    </div>
  )
}
