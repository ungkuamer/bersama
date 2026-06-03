import { ChevronRight, AlertCircle, Sun, Moon, Activity, Layers, Database } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription, AlertAction } from '@/components/ui/alert'

interface HeaderProps {
  isCollapsed: boolean;
  setIsCollapsed: (collapsed: boolean) => void;
  activeTab: 'readiness' | 'operator';
  error: string | null;
  onRetryConnection: () => void;
  theme: 'light' | 'dark';
  toggleTheme: () => void;
  activeRunsCount: number;
  capacity: number;
  readyIssuesCount: number;
  failedRunsCount: number;
  reposCount: number;
}

export default function Header({
  isCollapsed,
  setIsCollapsed,
  activeTab,
  error,
  onRetryConnection,
  theme,
  toggleTheme,
  activeRunsCount,
  capacity,
  readyIssuesCount,
  failedRunsCount,
  reposCount,
}: HeaderProps) {
  const pageTitle = activeTab === 'readiness' ? 'Health Check' : 'Operations'
  const pageDescription = activeTab === 'readiness'
    ? 'Scheduling readiness, repository checks, and issue operations'
    : 'Agent runs, log tails, and operations controls'

  return (
    <div className="sticky top-0 z-50 flex flex-col bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <header className="border-b px-6 py-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          {isCollapsed && (
            <button 
              onClick={() => setIsCollapsed(false)}
              className="mr-1 rounded-md border bg-background p-1 text-muted-foreground transition hover:bg-muted hover:text-foreground"
              title="Expand Sidebar"
            >
              <ChevronRight className="size-4" />
            </button>
          )}
          <div className="flex flex-col gap-0.5">
            <h1 className="text-base font-semibold tracking-tight text-foreground">{pageTitle}</h1>
            <p className="text-xs text-muted-foreground">{pageDescription}</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Button
            variant="outline"
            size="icon-sm"
            onClick={toggleTheme}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {theme === 'dark' ? <Sun /> : <Moon />}
          </Button>
        </div>
      </header>

      {/* Consolidated Status Bar */}
      <div className="flex flex-wrap items-center gap-4 border-b bg-card/50 backdrop-blur-sm px-6 py-2 text-xs font-medium md:gap-6">
        <div className="flex items-center gap-2" title={`${activeRunsCount} of ${capacity} concurrency slots in use`}>
          <Activity className={`size-3.5 text-primary ${activeRunsCount > 0 ? 'animate-pulse text-emerald-500' : 'text-muted-foreground'}`} />
          <span className="text-muted-foreground">Active Runs:</span>
          <span className="font-mono font-semibold text-foreground">
            {activeRunsCount}/{capacity}
          </span>
          {capacity > 0 && (
            <span className="text-[10px] text-muted-foreground/80 font-mono">
              ({Math.round((activeRunsCount / capacity) * 100)}% util)
            </span>
          )}
        </div>

        <div className="h-4 w-px bg-border hidden sm:block" />

        <div className="flex items-center gap-2">
          <Layers className="size-3.5 text-muted-foreground" />
          <span className="text-muted-foreground">Ready Issues:</span>
          <span className="font-mono font-semibold text-foreground">{readyIssuesCount}</span>
        </div>

        <div className="h-4 w-px bg-border hidden sm:block" />

        <div className="flex items-center gap-2">
          <AlertCircle className={`size-3.5 ${failedRunsCount > 0 ? 'text-destructive' : 'text-muted-foreground'}`} />
          <span className="text-muted-foreground">Failed Runs:</span>
          <span className={`font-mono font-semibold ${failedRunsCount > 0 ? 'text-destructive font-bold' : 'text-foreground'}`}>
            {failedRunsCount}
          </span>
        </div>

        <div className="h-4 w-px bg-border hidden sm:block" />

        <div className="flex items-center gap-2">
          <Database className="size-3.5 text-muted-foreground" />
          <span className="text-muted-foreground">Workspaces:</span>
          <span className="font-mono font-semibold text-foreground">{reposCount}</span>
        </div>
      </div>

      {error && (
        <div className="border-b bg-background px-6 py-2.5">
          <Alert variant="destructive" role="none" className="relative pr-36">
            <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
            <div>
              <AlertTitle className="mb-1 text-xs font-semibold leading-none">Connection issue</AlertTitle>
              <AlertDescription className="break-words pr-4 text-xs text-destructive/90">
                {error}
              </AlertDescription>
            </div>
            <AlertAction className="absolute top-1/2 -translate-y-1/2 right-3">
              <Button 
                onClick={onRetryConnection}
                variant="destructive"
                size="xs"
              >
                Retry
              </Button>
            </AlertAction>
          </Alert>
        </div>
      )}
    </div>
  )
}
