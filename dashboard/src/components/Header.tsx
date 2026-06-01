import { ChevronRight, AlertCircle, Sun, Moon } from 'lucide-react'
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
}

export default function Header({
  isCollapsed,
  setIsCollapsed,
  activeTab,
  error,
  onRetryConnection,
  theme,
  toggleTheme,
}: HeaderProps) {
  const pageTitle = activeTab === 'readiness' ? 'Documents' : 'Operations'
  const pageDescription = activeTab === 'readiness'
    ? 'Scheduling readiness, repository checks, and issue lifecycle'
    : 'Agent runs, log tails, and lifecycle controls'

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
