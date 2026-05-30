/**
 * Modern glowing shimmer skeleton progress tracks.
 * Replaces raw textual loading indicators with animated gradient bars.
 */
export function Shimmer({ className }: { className?: string }) {
  return (
    <div
      className={`animate-shimmer bg-gradient-to-r from-zinc-900 via-zinc-800/60 to-zinc-900 bg-[length:200%_100%] rounded ${className || ''}`}
      aria-hidden="true"
    />
  )
}

export function ShimmerText({ lines = 1, className }: { lines?: number; className?: string }) {
  return (
    <div className={`space-y-2 ${className || ''}`} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <Shimmer
          key={i}
          className={`h-3 rounded ${i === lines - 1 && lines > 1 ? 'w-3/4' : 'w-full'}`}
        />
      ))}
    </div>
  )
}

export function ShimmerCard({ className }: { className?: string }) {
  return (
    <div className={`dashboard-glass-surface rounded border p-4 space-y-3 ${className || ''}`} aria-hidden="true">
      <Shimmer className="h-4 w-1/3" />
      <Shimmer className="h-3 w-full" />
      <Shimmer className="h-3 w-5/6" />
      <Shimmer className="h-3 w-2/3" />
    </div>
  )
}
