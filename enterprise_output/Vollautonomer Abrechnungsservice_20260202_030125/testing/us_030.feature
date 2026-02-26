@@smoke @@regression
Feature: US-030 Verify Exception-Handler-Agent Reliability and Response Targets
  As a DevOps Engineer
  I want to Verify the Exception-Handler-Agent detects, analyzes, and escalates exceptions while providing solution recommendations and learning updates within defined reliability and response targets.
  So that Ensures operational resilience and timely recovery from abnormal cases, reducing downtime and financial impact for Finance and Operations.

  Background:
    Given the Exception-Handler-Agent is deployed with telemetry, escalation, and learning integrations enabled

  @@smoke @@regression @@happy-path
  Scenario: Happy path: All reliability and response targets are met under controlled tests
    # Validates end-to-end detection, recommendation time, escalation accuracy, and learning updates meet targets
    Given controlled fault-injection tests are running with 100 injected exception scenarios
    When the system completes detection, analysis, escalation, recommendation, and learning updates
    Then at least 95 percent of injected exceptions are analyzed end-to-end
    And time to recommendation is 60 seconds or less from detection
    And at least 98 percent of critical exceptions are escalated to the correct channel
    And at least 90 percent of resolved exceptions are recorded in the LearningSystem

  @@regression @@boundary
  Scenario: Boundary conditions: Threshold values are exactly met
    # Ensures acceptance criteria pass at exact target thresholds
    Given a test run with metrics at boundary values
    When the system evaluates detection rate, recommendation time, escalation accuracy, and learning update success rate
    Then the detection and analysis completion rate equals 95 percent
    And the time to recommendation equals 60 seconds
    And the escalation accuracy for critical exceptions equals 98 percent
    And the learning update success rate equals 90 percent

  @@regression @@edge-case
  Scenario Outline: Edge case outline: High concurrency stability near error-rate limit
    # Validates stability under 500 concurrent exceptions and near-threshold error rates
    Given load testing runs with <concurrent_events> concurrent exception events
    When the agent workflow processes exceptions and logs workflow errors
    Then the workflow error rate is less than or equal to <max_error_rate_percent> percent

    Examples:
      | concurrent_events | max_error_rate_percent |
      | 500 | 1 |
      | 450 | 1 |

  @@regression @@negative
  Scenario Outline: Error scenario outline: Target thresholds are breached
    # Verifies failures are detected when performance metrics fall below targets
    Given a controlled test run with degraded metrics
    When the system measures detection rate, recommendation time, escalation accuracy, and learning update success rate
    Then the run is marked as non-compliant because <failed_metric> does not meet its target

    Examples:
      | failed_metric |
      | detection and analysis completion rate is 94 percent |
      | time to recommendation is 61 seconds |
      | escalation accuracy is 97 percent |
      | learning update success rate is 89 percent |
