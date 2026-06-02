import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import SideDrawer, { type Issue } from './SideDrawer';

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
