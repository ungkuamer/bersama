import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import DependencyPipeline, { type PipelineNode } from './DependencyPipeline';

/** Helper to collect all #123 text labels from the SVG pipeline */
const collectNodeLabels = (): string[] => {
  const group = screen.getByRole('group', { name: /Dependency pipeline map/i });
  const labels = group.querySelectorAll('text');
  return Array.from(labels).map(el => el.textContent ?? '');
};

const colorMap: Record<string, string> = {
  succeeded: 'var(--pipeline-succeeded-text)',
  running: 'var(--pipeline-running-text)',
  blocked: 'var(--pipeline-blocked-text)',
  ready: 'var(--pipeline-ready-text)',
  claimed: 'var(--pipeline-claimed-text)',
  unready: 'var(--pipeline-default-text)',
  failed: 'var(--pipeline-default-text)',
};

describe('DependencyPipeline', () => {
  it('renders nothing for empty children', () => {
    const { container } = render(<DependencyPipeline children={[]} />);
    expect(screen.queryByRole('group', { name: /Dependency pipeline map/i })).not.toBeInTheDocument();
    expect(container.querySelector('svg')).not.toBeInTheDocument();
  });

  it('renders a single node when given one child', () => {
    const children: PipelineNode[] = [
      { number: 12, status: 'ready', blocked_by: [], active_blockers: [] },
    ];
    render(<DependencyPipeline children={children} />);

    expect(screen.getByRole('group', { name: /Dependency pipeline map/i })).toBeInTheDocument();
    expect(collectNodeLabels()).toEqual(['#12']);

    const text = screen.getByText('#12');
    expect(text).toHaveAttribute('fill', colorMap.ready);
  });

  it('renders sequential nodes connected by arrows', () => {
    const children: PipelineNode[] = [
      { number: 10, status: 'succeeded', blocked_by: [], active_blockers: [] },
      { number: 11, status: 'running', blocked_by: [10], active_blockers: [] },
      { number: 12, status: 'blocked', blocked_by: [11], active_blockers: [11] },
    ];
    render(<DependencyPipeline children={children} />);

    const labels = collectNodeLabels();
    expect(labels).toEqual(['#10', '#11', '#12']);

    // Verify connecting lines exist (2 arrows for 3 nodes)
    const svg = document.querySelector('svg');
    expect(svg).toBeInTheDocument();
    const lines = svg!.querySelectorAll('line');
    expect(lines.length).toBe(2);
    const polygons = svg!.querySelectorAll('polygon');
    expect(polygons.length).toBe(2);
  });

  it('color-codes nodes by their execution status', () => {
    const children: PipelineNode[] = [
      { number: 1, status: 'succeeded', blocked_by: [], active_blockers: [] },
      { number: 2, status: 'running', blocked_by: [1], active_blockers: [] },
      { number: 3, status: 'blocked', blocked_by: [2], active_blockers: [2] },
      { number: 4, status: 'ready', blocked_by: [3], active_blockers: [3] },
      { number: 5, status: 'claimed', blocked_by: [4], active_blockers: [] },
      { number: 6, status: 'failed', blocked_by: [5], active_blockers: [] },
      { number: 7, status: 'unready', blocked_by: [6], active_blockers: [] },
    ];
    render(<DependencyPipeline children={children} />);

    const labels = collectNodeLabels();
    expect(labels).toHaveLength(7);

    // Check each node's text color
    const textElements = document.querySelectorAll('svg text');
    const textColors = Array.from(textElements).map(el => el.getAttribute('fill'));

    expect(textColors[0]).toBe(colorMap.succeeded);
    expect(textColors[1]).toBe(colorMap.running);
    expect(textColors[2]).toBe(colorMap.blocked);
    expect(textColors[3]).toBe(colorMap.ready);
    expect(textColors[4]).toBe(colorMap.claimed);
    expect(textColors[5]).toBe(colorMap.failed);
    expect(textColors[6]).toBe(colorMap.unready);
  });

  it('adds pulse animation classes to running nodes', () => {
    const children: PipelineNode[] = [
      { number: 10, status: 'running', blocked_by: [], active_blockers: [] },
    ];
    render(<DependencyPipeline children={children} />);

    const rect = document.querySelector('rect.pipeline-node-running');
    expect(rect).toBeInTheDocument();

    const text = document.querySelector('text.pipeline-text-running');
    expect(text).toBeInTheDocument();
  });

  it('does not add pulse animation to non-running nodes', () => {
    const children: PipelineNode[] = [
      { number: 10, status: 'succeeded', blocked_by: [], active_blockers: [] },
      { number: 11, status: 'blocked', blocked_by: [10], active_blockers: [10] },
      { number: 12, status: 'ready', blocked_by: [], active_blockers: [] },
    ];
    render(<DependencyPipeline children={children} />);

    const pulsingRects = document.querySelectorAll('rect.pipeline-node-running');
    expect(pulsingRects.length).toBe(0);
  });

  it('topologically sorts nodes based on blocked_by dependencies', () => {
    // Provide nodes out of order; pipeline should sort them
    const children: PipelineNode[] = [
      { number: 30, status: 'blocked', blocked_by: [20], active_blockers: [20] },
      { number: 20, status: 'succeeded', blocked_by: [10], active_blockers: [] },
      { number: 10, status: 'succeeded', blocked_by: [], active_blockers: [] },
    ];
    render(<DependencyPipeline children={children} />);

    const labels = collectNodeLabels();
    // After topological sort: #10 -> #20 -> #30
    expect(labels).toEqual(['#10', '#20', '#30']);
  });

  it('handles independent nodes (no dependency edges) by preserving original order', () => {
    const children: PipelineNode[] = [
      { number: 5, status: 'ready', blocked_by: [], active_blockers: [] },
      { number: 3, status: 'ready', blocked_by: [], active_blockers: [] },
      { number: 8, status: 'ready', blocked_by: [], active_blockers: [] },
    ];
    render(<DependencyPipeline children={children} />);

    const labels = collectNodeLabels();
    expect(labels).toEqual(['#5', '#3', '#8']);
  });

  it('handles mixed dependencies by ordering blocked nodes after their blockers', () => {
    const children: PipelineNode[] = [
      { number: 50, status: 'blocked', blocked_by: [40, 60], active_blockers: [40] },
      { number: 40, status: 'succeeded', blocked_by: [], active_blockers: [] },
      { number: 60, status: 'succeeded', blocked_by: [], active_blockers: [] },
    ];
    render(<DependencyPipeline children={children} />);

    const labels = collectNodeLabels();
    // #50 should come after both #40 and #60
    const idx50 = labels.indexOf('#50');
    const idx40 = labels.indexOf('#40');
    const idx60 = labels.indexOf('#60');
    expect(idx50).toBeGreaterThan(idx40);
    expect(idx50).toBeGreaterThan(idx60);
  });

  it('renders the SVG with an accessible label', () => {
    const children: PipelineNode[] = [
      { number: 1, status: 'ready', blocked_by: [], active_blockers: [] },
    ];
    render(<DependencyPipeline children={children} />);

    expect(screen.getByLabelText(/Dependency pipeline visualization/i)).toBeInTheDocument();
  });

  it('renders connecting lines as dashed when the source node is running', () => {
    const children: PipelineNode[] = [
      { number: 10, status: 'running', blocked_by: [], active_blockers: [] },
      { number: 11, status: 'ready', blocked_by: [10], active_blockers: [] },
    ];
    render(<DependencyPipeline children={children} />);

    const lines = document.querySelectorAll('svg line');
    expect(lines.length).toBe(1);
    // The line from running node should have strokeDasharray
    expect(lines[0].getAttribute('stroke-dasharray')).toBe('4 2');
  });

  it('renders connecting lines as solid when the source node is not running', () => {
    const children: PipelineNode[] = [
      { number: 10, status: 'succeeded', blocked_by: [], active_blockers: [] },
      { number: 11, status: 'ready', blocked_by: [10], active_blockers: [] },
    ];
    render(<DependencyPipeline children={children} />);

    const lines = document.querySelectorAll('svg line');
    expect(lines.length).toBe(1);
    expect(lines[0].getAttribute('stroke-dasharray')).toBeNull();
  });
});
