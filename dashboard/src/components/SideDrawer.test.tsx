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
