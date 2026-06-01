import { 
  BarChart3,
  Database, 
  Layers, 
  ChevronLeft, 
  ChevronRight, 
  ChevronDown,
} from 'lucide-react';

interface Repo {
  name: string;
  repo_path: string;
  main_branch: string;
  worktree_root: string;
  global_concurrency: number;
  per_prd_concurrency: number;
  default_harness: string;
}

interface SidebarProps {
  repos: Repo[];
  selectedRepo: string;
  setSelectedRepo: (repo: string) => void;
  activeTab: 'readiness' | 'operator';
  setActiveTab: (tab: 'readiness' | 'operator') => void;
  isCollapsed: boolean;
  setIsCollapsed: (collapsed: boolean) => void;
}

export default function Sidebar({
  repos,
  selectedRepo,
  setSelectedRepo,
  activeTab,
  setActiveTab,
  isCollapsed,
  setIsCollapsed
}: SidebarProps) {
  const navItems = [
    { label: 'Dashboard', icon: BarChart3, tab: 'readiness' as const },
    { label: 'Lifecycle', icon: Layers, tab: 'operator' as const },
  ];

  return (
    <aside 
      className={`sticky top-0 z-40 flex h-screen shrink-0 select-none flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-all duration-300 ease-in-out ${
        isCollapsed ? 'w-16' : 'w-70'
      }`}
    >
      <div className="flex min-h-14 items-center justify-between border-b border-sidebar-border px-4">
        <div className="flex items-center gap-2 overflow-hidden">
          <div className="flex size-4 shrink-0 items-center justify-center rounded-full border-2 border-sidebar-foreground">
            <span className="size-1.5 rounded-full bg-sidebar-foreground" />
          </div>
          
          {!isCollapsed && (
            <span className="truncate text-sm font-semibold tracking-tight">Bersama OS</span>
          )}
        </div>

        {!isCollapsed && (
          <button 
            onClick={() => setIsCollapsed(true)}
            className="rounded-md p-1 text-muted-foreground transition hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
            title="Collapse Sidebar"
          >
            <ChevronLeft className="size-4" />
          </button>
        )}
      </div>

      {repos.length > 0 && (
        <div className="border-b border-sidebar-border p-3">
          <div className="rounded-lg border border-sidebar-border bg-background p-2 shadow-xs">
            <div className="flex items-center justify-between">
              {isCollapsed ? (
                <div className="flex w-full justify-center py-1">
                  <span 
                    className="cursor-pointer rounded border border-sidebar-border bg-sidebar-accent px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase text-sidebar-foreground"
                    title={selectedRepo}
                  >
                    {selectedRepo.substring(0, 2).toUpperCase()}
                  </span>
                </div>
              ) : (
                <div className="relative flex w-full items-center">
                  <Database className="mr-2 size-3.5 shrink-0 text-muted-foreground" />
                  <select 
                    value={selectedRepo} 
                    onChange={(e) => setSelectedRepo(e.target.value)}
                    className="w-full cursor-pointer appearance-none bg-transparent pr-5 font-mono text-xs font-medium text-foreground focus:outline-none"
                    style={{ WebkitAppearance: 'none' }}
                  >
                    {repos.map(r => (
                      <option key={r.name} value={r.name} className="bg-background text-foreground">
                        {r.name}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-0 size-3 text-muted-foreground" />
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <nav className="flex-1 px-3 py-4">
        <div className="flex flex-col gap-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.tab;
            return (
              <button
                key={item.label}
                onClick={() => setActiveTab(item.tab)}
                className={`flex h-9 w-full items-center gap-3 rounded-lg px-3 text-sm transition ${
                  isActive
                    ? 'bg-sidebar-accent font-medium text-sidebar-accent-foreground'
                    : 'text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
                }`}
                title={isCollapsed ? item.label : undefined}
              >
                <Icon className="size-4 shrink-0" />
                {!isCollapsed && <span>{item.label}</span>}
              </button>
            );
          })}
        </div>
      </nav>

      <div className="flex flex-col gap-2 border-t border-sidebar-border p-3">
        {isCollapsed && (
          <button 
            onClick={() => setIsCollapsed(false)}
            className="flex w-full justify-center rounded-md border p-2 text-muted-foreground transition hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
            title="Expand Sidebar"
          >
            <ChevronRight className="size-4" />
          </button>
        )}
        
        {!isCollapsed && (
          <div className="flex items-center justify-between px-1 py-1 text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <span className="size-1.5 rounded-full bg-emerald-500"></span>
              <span>Host Live</span>
            </div>
            <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">v1.0</span>
          </div>
        )}
      </div>
    </aside>
  );
}
