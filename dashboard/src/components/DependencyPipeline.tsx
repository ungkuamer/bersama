import { useMemo } from 'react';

export interface PipelineNode {
  number: number;
  status?: string;
  blocked_by?: number[];
  active_blockers?: number[];
}

interface DependencyPipelineProps {
  children: PipelineNode[];
}

/** Topological sort of nodes using their blocked_by dependency edges. */
function topologicalSort(nodes: PipelineNode[]): PipelineNode[] {
  const nodeMap = new Map<number, PipelineNode>();
  for (const n of nodes) {
    nodeMap.set(n.number, n);
  }

  const inDegree = new Map<number, number>();
  const adjacency = new Map<number, number[]>();

  for (const n of nodes) {
    if (!inDegree.has(n.number)) inDegree.set(n.number, 0);
    if (!adjacency.has(n.number)) adjacency.set(n.number, []);
  }

  for (const n of nodes) {
    for (const blocker of n.blocked_by || []) {
      // Edge: blocker -> n
      if (nodeMap.has(blocker)) {
        if (!adjacency.has(blocker)) adjacency.set(blocker, []);
        adjacency.get(blocker)!.push(n.number);
        inDegree.set(n.number, (inDegree.get(n.number) ?? 0) + 1);
        if (!inDegree.has(blocker)) inDegree.set(blocker, 0);
      }
    }
  }

  const queue: number[] = [];
  for (const [num, deg] of inDegree) {
    if (deg === 0) queue.push(num);
  }
  // If no nodes have in-degree 0 (circular deps or all nodes blocked),
  // fall back to original order
  if (queue.length === 0) return [...nodes];

  const sorted: PipelineNode[] = [];
  while (queue.length > 0) {
    const current = queue.shift()!;
    const node = nodeMap.get(current);
    if (node) sorted.push(node);
    for (const neighbor of adjacency.get(current) ?? []) {
      const newDeg = (inDegree.get(neighbor) ?? 1) - 1;
      inDegree.set(neighbor, newDeg);
      if (newDeg === 0) queue.push(neighbor);
    }
  }

  // Append any nodes that didn't make it (cycles or missing blockers)
  for (const n of nodes) {
    if (!sorted.find(s => s.number === n.number)) {
      sorted.push(n);
    }
  }

  return sorted;
}

const statusColor = (status?: string): { fill: string; stroke: string; text: string; animate?: boolean } => {
  switch (status) {
    case 'succeeded':
      return { fill: 'var(--pipeline-succeeded-fill)', stroke: 'var(--pipeline-succeeded-stroke)', text: 'var(--pipeline-succeeded-text)' };
    case 'running':
      return { fill: 'var(--pipeline-running-fill)', stroke: 'var(--pipeline-running-stroke)', text: 'var(--pipeline-running-text)', animate: true };
    case 'blocked':
      return { fill: 'var(--pipeline-blocked-fill)', stroke: 'var(--pipeline-blocked-stroke)', text: 'var(--pipeline-blocked-text)' };
    case 'ready':
      return { fill: 'var(--pipeline-ready-fill)', stroke: 'var(--pipeline-ready-stroke)', text: 'var(--pipeline-ready-text)' };
    case 'claimed':
      return { fill: 'var(--pipeline-claimed-fill)', stroke: 'var(--pipeline-claimed-stroke)', text: 'var(--pipeline-claimed-text)' };
    default:
      return { fill: 'var(--pipeline-default-fill)', stroke: 'var(--pipeline-default-stroke)', text: 'var(--pipeline-default-text)' };
  }
};

const NODE_WIDTH = 64;
const NODE_HEIGHT = 28;
const PADDING = 24;
const ARROW_GAP = 12;

export default function DependencyPipeline({ children }: DependencyPipelineProps) {
  const sorted = useMemo(() => topologicalSort(children), [children]);

  if (sorted.length === 0) return null;

  const totalWidth = sorted.length * NODE_WIDTH + (sorted.length - 1) * (ARROW_GAP + 8) + PADDING * 2;
  const svgHeight = NODE_HEIGHT + PADDING * 2;

  return (
    <div
      role="group"
      aria-label="Dependency pipeline map"
      className="dependency-pipeline w-full overflow-x-auto py-3"
    >
      <svg
        viewBox={`0 0 ${totalWidth} ${svgHeight}`}
        className="w-full h-auto min-h-[60px]"
        preserveAspectRatio="xMidYMid meet"
        aria-label="Dependency pipeline visualization"
      >
        {sorted.map((node, idx) => {
          const x = PADDING + idx * (NODE_WIDTH + ARROW_GAP + 8);
          const y = PADDING;
          const color = statusColor(node.status);

          return (
            <g key={node.number}>
              {/* Connecting arrow to next node */}
              {idx < sorted.length - 1 && (
                <g>
                  <line
                    x1={x + NODE_WIDTH}
                    y1={y + NODE_HEIGHT / 2}
                    x2={x + NODE_WIDTH + ARROW_GAP + 4}
                    y2={y + NODE_HEIGHT / 2}
                    stroke="var(--pipeline-connector)"
                    strokeWidth={1.5}
                    strokeDasharray={color.animate ? '4 2' : undefined}
                  />
                  {/* Arrowhead */}
                  <polygon
                    points={`${x + NODE_WIDTH + ARROW_GAP + 8},${y + NODE_HEIGHT / 2} ${x + NODE_WIDTH + ARROW_GAP},${y + NODE_HEIGHT / 2 - 4} ${x + NODE_WIDTH + ARROW_GAP},${y + NODE_HEIGHT / 2 + 4}`}
                    fill="var(--pipeline-arrow)"
                  />
                </g>
              )}

              {/* Node background */}
              <rect
                x={x}
                y={y}
                width={NODE_WIDTH}
                height={NODE_HEIGHT}
                rx={6}
                ry={6}
                fill={color.fill}
                stroke={color.stroke}
                strokeWidth={1.5}
                className={color.animate ? 'pipeline-node-running' : ''}
              />

              {/* Node label */}
              <text
                x={x + NODE_WIDTH / 2}
                y={y + NODE_HEIGHT / 2 + 1}
                textAnchor="middle"
                dominantBaseline="middle"
                fill={color.text}
                fontSize={10}
                fontWeight={700}
                fontFamily="'Geist Mono Variable', monospace"
                className={color.animate ? 'pipeline-text-running' : ''}
              >
                #{node.number}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
