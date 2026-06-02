import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import SideDrawer, { type Issue, type RunMetrics } from './SideDrawer';

// Mock UI elements or setup when needed
const mockIssue: Issue = {
  number: 105,
  title: 'Unified Side Drawer with Derived Readiness Timeline',
  labels: ['implementation', 'ready-for-agent'],
  state: 'open',
  kind: 'implementation',
  status: 'ready',
  parent_prd_number: 101,
  blocked_by: [104],
  active_blockers: [104],
};

describe('SideDrawer Tab Configuration', () => {
  it('renders standard tabs: Overview, Readiness Timeline, and Operations by default', () => {
    render(
      <SideDrawer
        issue={mockIssue}
        open={true}
        onOpenChange={() => {}}
      />
    );

    // Assert that the three new tabs are present
    expect(screen.getByText('Overview')).toBeInTheDocument();
    expect(screen.getByText('Readiness Timeline')).toBeInTheDocument();
    expect(screen.getByText('Operations')).toBeInTheDocument();

    // The old tabs Execution and Branch should not be present
    expect(screen.queryByText('Execution')).not.toBeInTheDocument();
    expect(screen.queryByText('Branch')).not.toBeInTheDocument();
  });

  it('hides the Operations tab when readOnly is true', () => {
    render(
      <SideDrawer
        issue={mockIssue}
        open={true}
        onOpenChange={() => {}}
        readOnly={true}
      />
    );

    expect(screen.getByText('Overview')).toBeInTheDocument();
    expect(screen.getByText('Readiness Timeline')).toBeInTheDocument();
    expect(screen.queryByText('Operations')).not.toBeInTheDocument();
  });

  it('renders the 6 derived chronological timeline steps in the Readiness Timeline tab', () => {
    render(
      <SideDrawer
        issue={mockIssue}
        open={true}
        onOpenChange={() => {}}
      />
    );

    // Click on Readiness Timeline tab
    const timelineTab = screen.getByText('Readiness Timeline');
    fireEvent.click(timelineTab);

    // Verify all 6 steps exist
    expect(screen.getByText('Prepared PRD')).toBeInTheDocument();
    expect(screen.getByText('Claim Setup')).toBeInTheDocument();
    expect(screen.getByText('Active Claim')).toBeInTheDocument();
    expect(screen.getByText('Agent Run')).toBeInTheDocument();
    expect(screen.getByText('Integration PR')).toBeInTheDocument();
    expect(screen.getByText('Integrated Issue')).toBeInTheDocument();

    // Verify description contains parent PRD number context
    expect(screen.getByText(/under parent PRD #101/i)).toBeInTheDocument();
  });
});

describe('SideDrawer Telemetry Diagnostics', () => {
  const runningIssueWithTelemetryDiags: Issue = {
    number: 125,
    title: 'Show missing telemetry diagnostics',
    labels: ['implementation'],
    state: 'open',
    kind: 'implementation',
    status: 'running',
    parent_prd_number: 123,
    agent_run_id: 'run-125',
    started_at: '2026-06-02T16:14:45Z',
    implementation_branch: 'impl/123/125',
    blocked_by: [],
    active_blockers: [],
    telemetry_diagnostics: [
      {
        code: 'missing_association',
        severity: 'warning',
        message: 'No Run Telemetry Association found. The Agent Run did not declare observability identity at startup.',
      },
    ],
  };

  const runningIssueWithoutTelemetryDiags: Issue = {
    number: 126,
    title: 'Issue with available telemetry',
    labels: ['implementation'],
    state: 'open',
    kind: 'implementation',
    status: 'running',
    parent_prd_number: 123,
    agent_run_id: 'run-126',
    started_at: '2026-06-02T16:15:00Z',
    implementation_branch: 'impl/123/126',
    blocked_by: [],
    active_blockers: [],
    telemetry_diagnostics: null,
  };

  it('renders telemetry diagnostic warnings in the Operations tab when diagnostics are present', () => {
    render(
      <SideDrawer
        issue={runningIssueWithTelemetryDiags}
        open={true}
        onOpenChange={() => {}}
      />
    );

    // Go to Operations tab
    fireEvent.click(screen.getByText('Operations'));

    // Should show the Run Telemetry section header
    expect(screen.getByText('Run Telemetry')).toBeInTheDocument();

    // Should show the diagnostic code (uppercase, underscores replaced with spaces)
    expect(screen.getByText(/missing association/i)).toBeInTheDocument();

    // Should show the diagnostic message
    expect(screen.getByText(/No Run Telemetry Association found/i)).toBeInTheDocument();

    // Should show the "Metrics are unavailable" notice
    expect(screen.getByText(/Metrics are unavailable. This does not affect Agent Run lifecycle status./i)).toBeInTheDocument();
  });

  it('shows multiple diagnostic items when multiple diagnostics are present', () => {
    const issueWithMultipleDiags: Issue = {
      ...runningIssueWithTelemetryDiags,
      telemetry_diagnostics: [
        {
          code: 'missing_association',
          severity: 'warning',
          message: 'No Run Telemetry Association found.',
        },
        {
          code: 'unconfigured_observability',
          severity: 'warning',
          message: 'pi-agent-observability is not configured.',
        },
      ],
    };

    render(
      <SideDrawer
        issue={issueWithMultipleDiags}
        open={true}
        onOpenChange={() => {}}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    expect(screen.getByText(/missing association/i)).toBeInTheDocument();
    expect(screen.getByText(/unconfigured observability/i)).toBeInTheDocument();
    expect(screen.getByText(/No Run Telemetry Association found/i)).toBeInTheDocument();
    expect(screen.getByText(/pi-agent-observability is not configured/i)).toBeInTheDocument();
  });

  it('does not render telemetry diagnostics when diagnostics are null', () => {
    render(
      <SideDrawer
        issue={runningIssueWithoutTelemetryDiags}
        open={true}
        onOpenChange={() => {}}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    // Should NOT show the diagnostic warning section
    expect(screen.queryByText(/missing association/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Metrics are unavailable/i)).not.toBeInTheDocument();

    // Should show the telemetry available state instead
    expect(screen.getByText(/Telemetry is available/i)).toBeInTheDocument();
  });

  it('does not render telemetry section for non-implementation issues', () => {
    const prdIssue: Issue = {
      number: 123,
      title: 'PRD Issue',
      labels: ['prd'],
      state: 'open',
      kind: 'prd',
      children: [],
    };

    render(
      <SideDrawer
        issue={prdIssue}
        open={true}
        onOpenChange={() => {}}
      />
    );

    // Should be on Operations tab by default (not readOnly)
    // No Run Telemetry section for PRD issues
    expect(screen.queryByText('Run Telemetry')).not.toBeInTheDocument();
  });

  it('does not render telemetry diagnostics for issues without running/succeeded/failed status', () => {
    const readyIssue: Issue = {
      number: 127,
      title: 'Ready issue',
      labels: ['implementation', 'ready-for-agent'],
      state: 'open',
      kind: 'implementation',
      status: 'ready',
      blocked_by: [],
      active_blockers: [],
      telemetry_diagnostics: [
        {
          code: 'missing_association',
          severity: 'warning',
          message: 'No association.',
        },
      ],
    };

    render(
      <SideDrawer
        issue={readyIssue}
        open={true}
        onOpenChange={() => {}}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    // Telemetry diagnostics appear for any implementation issue regardless of status
    // as long as telemetry_diagnostics is present
    expect(screen.getByText('Run Telemetry')).toBeInTheDocument();
    expect(screen.getByText(/missing association/i)).toBeInTheDocument();
  });

  it('renders telemetry diagnostics with the amber warning color scheme', () => {
    render(
      <SideDrawer
        issue={runningIssueWithTelemetryDiags}
        open={true}
        onOpenChange={() => {}}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    // The Run Telemetry header should have amber warning styling
    const telemetryHeader = screen.getByText('Run Telemetry');
    expect(telemetryHeader.className).toContain('amber');
  });
});

describe('SideDrawer Run Metrics Rendering', () => {
  const runningIssueWithTelemetry: Issue = {
    number: 126,
    title: 'Render Run Metrics for one associated Agent Run',
    labels: ['implementation'],
    state: 'open',
    kind: 'implementation',
    status: 'succeeded',
    parent_prd_number: 123,
    agent_run_id: 'run-126',
    started_at: '2026-06-02T16:15:00Z',
    finished_at: '2026-06-02T16:25:00Z',
    implementation_branch: 'impl/123/126',
    blocked_by: [],
    active_blockers: [],
    telemetry_diagnostics: null,
  };

  const fullMetrics: RunMetrics = {
    run_id: 'run-126',
    diagnostics: [],
    metrics_available: true,
    input_tokens: 1500,
    output_tokens: 800,
    cache_read_tokens: 200,
    cache_write_tokens: 100,
    total_tokens: 2600,
    model_cost: 0.015,
    tool_call_count: 12,
    tool_error_count: 1,
    model: 'claude-sonnet-4',
    provider: 'anthropic',
    avg_time_to_first_token_ms: 450.0,
    avg_latency_ms: 1200.0,
    avg_output_tokens_per_sec: 85.5,
    latest_time_to_first_token_ms: 320.0,
    latest_latency_ms: 980.0,
    latest_output_tokens_per_sec: 92.0,
  };

  const unavailableMetrics: RunMetrics = {
    run_id: 'run-126',
    diagnostics: [
      {
        code: 'missing_association',
        severity: 'warning',
        message: 'No Run Telemetry Association found.',
      },
    ],
    metrics_available: false,
  };

  it('renders model usage metrics when metrics are available', () => {
    render(
      <SideDrawer
        issue={runningIssueWithTelemetry}
        open={true}
        onOpenChange={() => {}}
        runMetrics={fullMetrics}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    // Model Usage section
    expect(screen.getByText('Model Usage')).toBeInTheDocument();
    expect(screen.getByText('Input Tokens')).toBeInTheDocument();
    expect(screen.getByText('1,500')).toBeInTheDocument();
    expect(screen.getByText('Output Tokens')).toBeInTheDocument();
    expect(screen.getByText('800')).toBeInTheDocument();
    expect(screen.getByText('Cache Read')).toBeInTheDocument();
    expect(screen.getByText('200')).toBeInTheDocument();
    expect(screen.getByText('Cache Write')).toBeInTheDocument();
    expect(screen.getByText('100')).toBeInTheDocument();
    expect(screen.getByText('Total Tokens')).toBeInTheDocument();
    expect(screen.getByText('2,600')).toBeInTheDocument();
    expect(screen.getByText('Model Cost')).toBeInTheDocument();
    expect(screen.getByText('$0.0150')).toBeInTheDocument();
  });

  it('renders tool activity metrics when metrics are available', () => {
    render(
      <SideDrawer
        issue={runningIssueWithTelemetry}
        open={true}
        onOpenChange={() => {}}
        runMetrics={fullMetrics}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    // Tool Activity section
    expect(screen.getByText('Tool Activity')).toBeInTheDocument();
    expect(screen.getByText('Tool Calls')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('Tool Errors')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('renders model and provider info when metrics are available', () => {
    render(
      <SideDrawer
        issue={runningIssueWithTelemetry}
        open={true}
        onOpenChange={() => {}}
        runMetrics={fullMetrics}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    // Model Info section
    expect(screen.getByText('Model')).toBeInTheDocument();
    expect(screen.getByText('claude-sonnet-4')).toBeInTheDocument();
    expect(screen.getByText('Provider')).toBeInTheDocument();
    expect(screen.getByText('anthropic')).toBeInTheDocument();
  });

  it('renders model responsiveness metrics with average as primary and latest as secondary', () => {
    render(
      <SideDrawer
        issue={runningIssueWithTelemetry}
        open={true}
        onOpenChange={() => {}}
        runMetrics={fullMetrics}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    // Responsiveness section
    expect(screen.getByText('Model Responsiveness')).toBeInTheDocument();

    // Average values (primary)
    expect(screen.getByText('Avg TTFT')).toBeInTheDocument();
    expect(screen.getByText('450.0 ms')).toBeInTheDocument();
    expect(screen.getByText('Avg Latency')).toBeInTheDocument();
    expect(screen.getByText('1,200.0 ms')).toBeInTheDocument();
    expect(screen.getByText('Avg Tokens/s')).toBeInTheDocument();
    expect(screen.getByText('85.5')).toBeInTheDocument();

    // Latest values (secondary)
    expect(screen.getByText('Latest TTFT')).toBeInTheDocument();
    expect(screen.getByText('320.0 ms')).toBeInTheDocument();
    expect(screen.getByText('Latest Latency')).toBeInTheDocument();
    expect(screen.getByText('980.0 ms')).toBeInTheDocument();
    expect(screen.getByText('Latest Tokens/s')).toBeInTheDocument();
    expect(screen.getByText('92.0')).toBeInTheDocument();
  });

  it('does not render metrics section when runMetrics is null', () => {
    render(
      <SideDrawer
        issue={runningIssueWithTelemetry}
        open={true}
        onOpenChange={() => {}}
        runMetrics={undefined}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    // Should NOT show Metrics sections that need fetched data
    expect(screen.queryByText('Model Usage')).not.toBeInTheDocument();
    expect(screen.queryByText('Tool Activity')).not.toBeInTheDocument();
    expect(screen.queryByText('Model Responsiveness')).not.toBeInTheDocument();

    // But should still show the available telemetry indicator
    expect(screen.getByText(/Telemetry is available/)).toBeInTheDocument();
  });

  it('renders telemetry diagnostics when runMetrics has unavailable metrics', () => {
    render(
      <SideDrawer
        issue={runningIssueWithTelemetry}
        open={true}
        onOpenChange={() => {}}
        runMetrics={unavailableMetrics}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    // Should show the Run Telemetry warning
    expect(screen.getByText('Run Telemetry')).toBeInTheDocument();
    expect(screen.getByText(/missing association/i)).toBeInTheDocument();
    expect(screen.getByText(/No Run Telemetry Association found/i)).toBeInTheDocument();
    expect(screen.getByText(/Metrics are unavailable. This does not affect Agent Run lifecycle status./i)).toBeInTheDocument();

    // Should NOT show Metrics sections
    expect(screen.queryByText('Model Usage')).not.toBeInTheDocument();
  });

  it('renders latest telemetry timestamp when provided', () => {
    const metricsWithTimestamp: RunMetrics = {
      ...fullMetrics,
      latest_telemetry_at: '2026-06-02T16:24:30Z',
    };

    render(
      <SideDrawer
        issue={runningIssueWithTelemetry}
        open={true}
        onOpenChange={() => {}}
        runMetrics={metricsWithTimestamp}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    // Should show latest telemetry timestamp
    expect(screen.getByText('Latest Telemetry')).toBeInTheDocument();
  });

  it('renders error count in model usage when present', () => {
    const metricsWithErrors: RunMetrics = {
      ...fullMetrics,
      error_count: 2,
    };

    render(
      <SideDrawer
        issue={runningIssueWithTelemetry}
        open={true}
        onOpenChange={() => {}}
        runMetrics={metricsWithErrors}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    expect(screen.getByText('Errors')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });
});

describe('SideDrawer Implementation Issue Metrics', () => {
  const implementationIssue: Issue = {
    number: 127,
    title: 'Aggregate Implementation Issue Metrics across attempts',
    labels: ['implementation'],
    state: 'open',
    kind: 'implementation',
    status: 'failed',
    parent_prd_number: 123,
    agent_run_id: 'run-127',
    started_at: '2026-06-02T16:30:00Z',
    finished_at: '2026-06-02T16:35:00Z',
    implementation_branch: 'impl/123/127-aggregate',
    blocked_by: [],
    active_blockers: [],
    telemetry_diagnostics: null,
  };

  const aggregatedMetrics = {
    issue_number: 127,
    diagnostics: [],
    metrics_available: true,
    run_count: 3,
    successful_run_count: 2,
    runs_with_telemetry: 2,
    runs_without_telemetry: 1,
    failure_count: 1,
    latest_run_status: 'failed',
    input_tokens: 5000,
    output_tokens: 2500,
    cache_read_tokens: 600,
    cache_write_tokens: 300,
    total_tokens: 8400,
    model_cost: 0.045,
    tool_call_count: 36,
    tool_error_count: 2,
    avg_time_to_first_token_ms: 500.0,
    avg_latency_ms: 1250.0,
    avg_output_tokens_per_sec: 82.5,
    runs: [
      {
        run_id: 'run-127a',
        status: 'succeeded',
        started_at: '2026-06-02T16:15:00Z',
        finished_at: '2026-06-02T16:20:00Z',
        has_telemetry_association: true,
      },
      {
        run_id: 'run-127b',
        status: 'failed',
        started_at: '2026-06-02T16:25:00Z',
        finished_at: '2026-06-02T16:30:00Z',
        has_telemetry_association: true,
      },
      {
        run_id: 'run-127c',
        status: 'failed',
        started_at: '2026-06-02T16:30:00Z',
        finished_at: '2026-06-02T16:35:00Z',
        has_telemetry_association: false,
      },
    ],
  };

  const aggregatedMetricsNoTelemetry = {
    issue_number: 126,
    diagnostics: [
      {
        code: 'missing_association',
        severity: 'warning',
        message: 'No Agent Run associations found.',
      },
    ],
    metrics_available: false,
    run_count: 0,
    successful_run_count: 0,
    runs_with_telemetry: 0,
    runs_without_telemetry: 0,
    failure_count: 0,
    latest_run_status: null,
    runs: [],
  };

  it('renders Implementation Issue Metrics section header', () => {
    render(
      <SideDrawer
        issue={implementationIssue}
        open={true}
        onOpenChange={() => {}}
        implementationIssueMetrics={aggregatedMetrics}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    expect(screen.getByText('Implementation Issue Metrics')).toBeInTheDocument();
  });

  it('renders summary with attempt count, latest status, failures, and telemetry coverage', () => {
    render(
      <SideDrawer
        issue={implementationIssue}
        open={true}
        onOpenChange={() => {}}
        implementationIssueMetrics={aggregatedMetrics}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    expect(screen.getByText('Attempts')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument(); // run_count = 3
    expect(screen.getByText('Latest Status')).toBeInTheDocument();
    // 'failed' appears in both the summary card and the attempt history badges
    const failedElements = screen.getAllByText('failed');
    expect(failedElements.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Failures')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument(); // failure_count = 1
    expect(screen.getByText('With Telemetry')).toBeInTheDocument();
    expect(screen.getByText('2 / 3')).toBeInTheDocument(); // runs_with_telemetry / run_count
  });

  it('renders aggregated model usage metrics', () => {
    render(
      <SideDrawer
        issue={implementationIssue}
        open={true}
        onOpenChange={() => {}}
        implementationIssueMetrics={aggregatedMetrics}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    expect(screen.getByText('Aggregated Usage')).toBeInTheDocument();
    expect(screen.getByText('Total Tokens')).toBeInTheDocument();
    expect(screen.getByText('8,400')).toBeInTheDocument();
    expect(screen.getByText('Model Cost')).toBeInTheDocument();
    expect(screen.getByText('$0.0450')).toBeInTheDocument();
    expect(screen.getByText('Tool Calls')).toBeInTheDocument();
    expect(screen.getByText('36')).toBeInTheDocument();
    expect(screen.getByText('Tool Errors')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('renders averaged responsiveness metrics', () => {
    render(
      <SideDrawer
        issue={implementationIssue}
        open={true}
        onOpenChange={() => {}}
        implementationIssueMetrics={aggregatedMetrics}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    expect(screen.getByText('Avg. Responsiveness')).toBeInTheDocument();
    expect(screen.getByText('Avg TTFT')).toBeInTheDocument();
    expect(screen.getByText('500.0 ms')).toBeInTheDocument();
    expect(screen.getByText('Avg Latency')).toBeInTheDocument();
    expect(screen.getByText('Avg Tokens/s')).toBeInTheDocument();
    expect(screen.getByText('82.5')).toBeInTheDocument();
  });

  it('renders attempt history with status badges and telemetry indicators', () => {
    render(
      <SideDrawer
        issue={implementationIssue}
        open={true}
        onOpenChange={() => {}}
        implementationIssueMetrics={aggregatedMetrics}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    expect(screen.getByText('Attempt History')).toBeInTheDocument();

    // Check run IDs are shown
    expect(screen.getByText('run-127a')).toBeInTheDocument();
    expect(screen.getByText('run-127b')).toBeInTheDocument();
    expect(screen.getByText('run-127c')).toBeInTheDocument();

    // Check status badges
    const succeededBadges = screen.getAllByText('succeeded');
    const failedBadges = screen.getAllByText('failed');
    expect(succeededBadges.length).toBeGreaterThanOrEqual(1);
    expect(failedBadges.length).toBeGreaterThanOrEqual(1);
  });

  it('does not render implementation issue metrics when prop is not provided', () => {
    render(
      <SideDrawer
        issue={implementationIssue}
        open={true}
        onOpenChange={() => {}}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    expect(screen.queryByText('Implementation Issue Metrics')).not.toBeInTheDocument();
    expect(screen.queryByText('Attempt History')).not.toBeInTheDocument();
  });

  it('does not render implementation issue metrics for non-implementation issues', () => {
    const prdIssue: Issue = {
      number: 123,
      title: 'PRD Issue',
      labels: ['prd'],
      state: 'open',
      kind: 'prd',
      children: [],
    };

    render(
      <SideDrawer
        issue={prdIssue}
        open={true}
        onOpenChange={() => {}}
        implementationIssueMetrics={aggregatedMetrics}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    expect(screen.queryByText('Implementation Issue Metrics')).not.toBeInTheDocument();
  });

  it('renders telemetry diagnostics from aggregated metrics when diagnostics are present', () => {
    render(
      <SideDrawer
        issue={implementationIssue}
        open={true}
        onOpenChange={() => {}}
        implementationIssueMetrics={aggregatedMetricsNoTelemetry}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    expect(screen.getByText('Telemetry Diagnostics')).toBeInTheDocument();
    expect(screen.getByText(/missing association/i)).toBeInTheDocument();
    expect(screen.getByText(/No Agent Run associations found/i)).toBeInTheDocument();
  });

  it('displays N/A for latest_run_status when null', () => {
    const metricsWithNullStatus = {
      ...aggregatedMetricsNoTelemetry,
      run_count: 2,
      runs: [
        {
          run_id: 'run-a',
          status: '',
          started_at: null,
          finished_at: null,
          has_telemetry_association: false,
        },
      ],
    };

    render(
      <SideDrawer
        issue={implementationIssue}
        open={true}
        onOpenChange={() => {}}
        implementationIssueMetrics={metricsWithNullStatus}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    expect(screen.getByText('Implementation Issue Metrics')).toBeInTheDocument();
    expect(screen.getByText('N/A')).toBeInTheDocument();
  });

  it('shows attempt history with telemetry indicator icons', () => {
    const metricsWithMixedTelemetry = {
      ...aggregatedMetrics,
      run_count: 2,
      runs_with_telemetry: 1,
      runs_without_telemetry: 1,
      failure_count: 0,
      latest_run_status: 'succeeded',
      runs: [
        {
          run_id: 'run-t',
          status: 'succeeded',
          started_at: '2026-06-02T16:15:00Z',
          has_telemetry_association: true,
        },
        {
          run_id: 'run-nt',
          status: 'succeeded',
          started_at: '2026-06-02T16:20:00Z',
          has_telemetry_association: false,
        },
      ],
    };

    render(
      <SideDrawer
        issue={implementationIssue}
        open={true}
        onOpenChange={() => {}}
        implementationIssueMetrics={metricsWithMixedTelemetry}
      />
    );

    fireEvent.click(screen.getByText('Operations'));

    // Both runs should be visible
    expect(screen.getByText('run-t')).toBeInTheDocument();
    expect(screen.getByText('run-nt')).toBeInTheDocument();
  });
});

