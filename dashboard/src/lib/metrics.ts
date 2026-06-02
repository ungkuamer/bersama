/**
 * Shared metric formatting utilities.
 *
 * All metric values (tokens, cost, durations) use these formatters so
 * Run Metrics, Implementation Issue Metrics, and PRD Metrics render
 * with consistent number formatting and visual hierarchy.
 */

/** Compact token count: "1.2K", "3.4M", or raw for small values. */
export function formatCompactTokens(tokens: number | null | undefined): string {
  if (tokens == null) return '—';
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toLocaleString(undefined, { maximumFractionDigits: 1 })}M`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toLocaleString(undefined, { maximumFractionDigits: 1 })}K`;
  return tokens.toLocaleString();
}

/** Compact cost: "$0.02" style with 2–4 decimal places as appropriate. */
export function formatCompactCost(cost: number | null | undefined): string {
  if (cost == null) return '—';
  return `$${cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
}

/** Compact duration in ms or s. */
export function formatCompactMs(ms: number | null | undefined): string {
  if (ms == null) return '—';
  if (ms >= 1000) return `${(ms / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })}s`;
  return `${Math.round(ms)}ms`;
}

/** Compact tokens/s: "85 tok/s" style. */
export function formatCompactTokensPerSec(tps: number | null | undefined): string {
  if (tps == null) return '—';
  return `${Math.round(tps)} tok/s`;
}
