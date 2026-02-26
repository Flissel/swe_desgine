@smoke @regression
Feature: Monitoring Dashboard
  As a Operations Manager
  I want to monitor workflows, KPIs, and agent performance in real time via a management dashboard
  So that to quickly detect exceptions and improve process efficiency and reporting accuracy

  Background:
    Given the Operations Manager is authenticated and has dashboard access

  @happy-path @smoke @regression
  Scenario: Dashboard loads current workflow status, KPIs, and agent performance within SLA
    # Validates successful load of real-time monitoring data within 5 seconds
    When the dashboard is opened
    Then current workflow status is displayed within 5 seconds
    And KPI metrics are displayed within 5 seconds
    And agent performance is displayed within 5 seconds

  @regression
  Scenario: Exception highlighting with timestamp and workflow link
    # Verifies exceptions or SLA breaches are highlighted on refresh with details
    Given a workflow has an exception or SLA breach
    When the dashboard refreshes
    Then the exception is highlighted
    And a timestamp is displayed for the exception
    And a link to the affected workflow details is displayed

  @regression
  Scenario Outline: Dashboard load time boundary conditions
    # Ensures dashboard meets the 5-second load boundary for all sections
    When the dashboard is opened under a measured load time of "<load_time_seconds>" seconds
    Then current workflow status is "<workflow_status_visibility>"
    And KPI metrics are "<kpi_visibility>"
    And agent performance is "<agent_visibility>"

    Examples:
      | load_time_seconds | workflow_status_visibility | kpi_visibility | agent_visibility |
      | 5.0 | displayed | displayed | displayed |
      | 5.1 | not displayed | not displayed | not displayed |

  @negative @regression
  Scenario: Monitoring data source unavailable
    # Shows error message and last known data timestamp when real-time data cannot be loaded
    Given the monitoring data source is unavailable
    When the dashboard attempts to load real-time data
    Then an error message is shown
    And the last known data timestamp is displayed

  @edge-case @regression
  Scenario: Edge case for refresh with no exceptions
    # Confirms no exception highlighting when there are no exceptions or SLA breaches
    Given no workflows have exceptions or SLA breaches
    When the dashboard refreshes
    Then no exceptions are highlighted
    And workflow status, KPI metrics, and agent performance remain visible
