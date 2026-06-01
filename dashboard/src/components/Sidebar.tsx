import { 
  Database, 
  Layers, 
  Terminal, 
  ChevronLeft, 
  ChevronRight, 
  ChevronDown,
  Activity, 
  Cpu
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
  return (
    <aside 
      className={`h-screen sticky top-0 bg-zinc-950 border-r border-zinc-900 flex flex-col shrink-0 transition-all duration-300 ease-in-out z-40 select-none ${
        isCollapsed ? 'w-16' : 'w-64'
      }`}
    >
      {/* Sidebar Header with Logo & Brand */}
      <div className="p-4 border-b border-zinc-900 flex items-center justify-between min-h-[73px]">
        <div className="flex items-center gap-3 overflow-hidden">
          {/* Stylized Glowing Logo */}
          <div className="dashboard-glass-surface size-8 rounded border border-emerald-500/30 flex items-center justify-center text-emerald-400 font-bold shrink-0 shadow-[0_0_12px_rgba(16,185,129,0.15)] bg-emerald-950/20">
            B
          </div>
          
          {!isCollapsed && (
            <div className="flex flex-col select-none animate-fade-in">
              <h1 className="text-xs font-bold text-white tracking-widest uppercase flex items-center gap-1.5">
                Bersama
                <span className="text-[8px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-1 rounded">OS</span>
              </h1>
              <p className="text-[9px] text-zinc-500 tracking-tight">Agent Orchestration</p>
            </div>
          )}
        </div>

        {/* Collapse Toggle Button (Top) */}
        {!isCollapsed && (
          <button 
            onClick={() => setIsCollapsed(true)}
            className="p-1 rounded bg-zinc-900 border border-zinc-800 text-zinc-500 hover:text-zinc-200 hover:border-zinc-700 transition cursor-pointer"
            title="Collapse Sidebar"
          >
            <ChevronLeft className="size-3.5" />
          </button>
        )}
      </div>

      {/* Premium Workspace Selector (Repository Switcher) */}
      {repos.length > 0 && (
        <div className="p-3 border-b border-zinc-900 bg-zinc-950/40">
          <div className="relative group rounded-lg bg-zinc-900/40 hover:bg-zinc-900/80 border border-zinc-900 hover:border-zinc-800 p-2.5 transition duration-200">
            <div className="flex items-center gap-1.5 text-zinc-500 text-[9px] font-bold uppercase tracking-wider">
              <Database className="size-3 text-emerald-500" />
              <span>REPO:</span>
            </div>
            
            <div className="mt-1 flex items-center justify-between">
              {isCollapsed ? (
                <div className="w-full flex justify-center py-1">
                  <span 
                    className="text-[10px] font-mono font-bold text-emerald-400 bg-emerald-950/30 border border-emerald-900/50 px-1.5 py-0.5 rounded cursor-pointer uppercase"
                    title={selectedRepo}
                  >
                    {selectedRepo.substring(0, 2).toUpperCase()}
                  </span>
                </div>
              ) : (
                <div className="w-full relative flex items-center">
                  <select 
                    value={selectedRepo} 
                    onChange={(e) => setSelectedRepo(e.target.value)}
                    className="w-full bg-transparent text-[11px] font-bold text-zinc-200 focus:outline-none cursor-pointer pr-5 appearance-none font-mono"
                    style={{ WebkitAppearance: 'none' }}
                  >
                    {repos.map(r => (
                      <option key={r.name} value={r.name} className="bg-zinc-950 text-zinc-300 text-xs py-2">
                        {r.name}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="size-3 text-zinc-500 absolute right-0 pointer-events-none" />
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Core Navigation Links */}
      <nav className="flex-1 px-2 py-4 flex flex-col gap-1.5">
        <button
          onClick={() => setActiveTab('readiness')}
          className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-semibold tracking-wide transition-all duration-200 cursor-pointer ${
            activeTab === 'readiness'
              ? 'bg-emerald-500/10 text-emerald-400 font-bold border-l-2 border-emerald-500 shadow-[inset_1px_0_0_rgba(16,185,129,0.2)]'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/40 border-l-2 border-transparent'
          }`}
          title={isCollapsed ? "Scheduling Readiness" : undefined}
        >
          <Layers className={`size-4 shrink-0 transition-transform ${activeTab === 'readiness' ? 'text-emerald-400 scale-105' : 'text-zinc-500'}`} />
          {!isCollapsed && <span>Scheduling Readiness</span>}
        </button>

        <button
          onClick={() => setActiveTab('operator')}
          className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-semibold tracking-wide transition-all duration-200 cursor-pointer ${
            activeTab === 'operator'
              ? 'bg-emerald-500/10 text-emerald-400 font-bold border-l-2 border-emerald-500 shadow-[inset_1px_0_0_rgba(16,185,129,0.2)]'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/40 border-l-2 border-transparent'
          }`}
          title={isCollapsed ? "Operator Console" : undefined}
        >
          <Terminal className={`size-4 shrink-0 transition-transform ${activeTab === 'operator' ? 'text-emerald-400 scale-105' : 'text-zinc-500'}`} />
          {!isCollapsed && <span>Operator Console</span>}
        </button>

        {/* Decorative metadata menu when expanded */}
        {!isCollapsed && (
          <div className="mt-8 px-3 select-none">
            <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest block mb-2">SYSTEM TELEMETRY</span>
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2 text-[10px] text-zinc-500">
                <Activity className="size-3 text-zinc-600 shrink-0" />
                <span className="truncate">Node Status: Online</span>
              </div>
              <div className="flex items-center gap-2 text-[10px] text-zinc-500">
                <Cpu className="size-3 text-zinc-600 shrink-0" />
                <span className="truncate">Harness: local</span>
              </div>
            </div>
          </div>
        )}
      </nav>

      {/* Sidebar Footer with Expand Toggle (Bottom) */}
      <div className="p-3 border-t border-zinc-900 bg-zinc-950/20 flex flex-col gap-2">
        {isCollapsed && (
          <button 
            onClick={() => setIsCollapsed(false)}
            className="w-full p-2 rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-400 hover:text-zinc-200 flex justify-center transition cursor-pointer"
            title="Expand Sidebar"
          >
            <ChevronRight className="size-4" />
          </button>
        )}
        
        {!isCollapsed && (
          <div className="flex items-center justify-between text-[10px] text-zinc-500 px-1 py-1">
            <div className="flex items-center gap-1.5">
              <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
              <span>Host Live</span>
            </div>
            <span className="text-[8px] font-mono bg-zinc-900 px-1.5 py-0.5 rounded text-zinc-400">v1.0</span>
          </div>
        )}
      </div>
    </aside>
  );
}
