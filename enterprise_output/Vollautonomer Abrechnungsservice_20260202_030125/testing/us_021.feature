@@smoke @@regression
Feature: US-021 Verify Non-Traditional Performance Metrics
  As a DevOps Engineer
  I want to Validate that autonomy level, AI performance indicators, and business impact metrics are measured, reported, and meet agreed thresholds
  So that Ensures non-traditional performance metrics are reliable for decision-making across Finance, Operations, and IT/DevOps

  Background:
    Given the metric collection services are available and configured for Finance, Operations, and IT/DevOps
    And the reporting dashboard is accessible to authorized users

  @@smoke @@happy-path
  Scenario: Happy path: All metrics meet or exceed agreed thresholds
    # Validates that autonomy, AI effectiveness, and business impact meet targets under standard conditions
    Given the system has 30 days of audit logs and workflow telemetry for core processes
    And scheduled evaluation pipelines ran on holdout datasets with baseline comparisons
    And Finance has completed pre- and post-implementation cost baseline analysis
    When the metrics are calculated and reported for autonomy level, AI effectiveness, and business impact
    Then the autonomy level index is at least 70 percent
    And the AI model effectiveness for critical models is at least 0.85
    And the operational cost reduction is at least 5 percent within 90 days

  @@regression @@boundary
  Scenario Outline: Boundary conditions: Metrics exactly at thresholds
    # Ensures threshold boundary values are accepted as passing
    Given the system has the required measurement inputs for the last 30 days
    When the metrics are calculated with values exactly at the target thresholds
    Then the results are marked as meeting the thresholds

    Examples:
      | autonomy_index | ai_f1_score | cost_reduction_percent |
      | 70 | 0.85 | 5 |

  @@regression @@edge
  Scenario Outline: Edge case: Autonomy index slightly below target
    # Validates near-threshold autonomy underperformance is flagged
    Given the system has 30 days of audit logs and workflow telemetry for core processes
    When the autonomy level index is computed at a near-threshold value
    Then the autonomy metric is reported as below target
    And the report includes a remediation alert for affected processes

    Examples:
      | autonomy_index |
      | 69.9 |

  @@regression @@edge
  Scenario Outline: Edge case: AI effectiveness slightly below target for a critical model
    # Validates near-threshold AI underperformance is flagged
    Given the evaluation pipeline runs on the holdout dataset for a critical model
    When the AI model effectiveness score is computed at a near-threshold value
    Then the AI effectiveness metric is reported as below target
    And the model is flagged for review

    Examples:
      | ai_f1_score |
      | 0.849 |

  @@regression @@edge
  Scenario Outline: Edge case: Business impact slightly below target within 90 days
    # Validates near-threshold cost reduction underperformance is flagged
    Given Finance completes variance analysis within 90 days
    When the cost reduction percentage is computed at a near-threshold value
    Then the business impact metric is reported as below target
    And the report highlights the shortfall and impacted cost centers

    Examples:
      | cost_reduction_percent |
      | 4.99 |

  @@regression @@negative
  Scenario: Error scenario: Missing audit logs for autonomy calculation
    # Validates error handling when required telemetry is unavailable
    Given audit logs for the 30-day period are incomplete or unavailable
    When the system attempts to calculate the autonomy level index
    Then the calculation fails with a clear data availability error
    And the report marks the autonomy metric as not measurable

  @@regression @@negative
  Scenario: Error scenario: Evaluation pipeline fails for holdout dataset
    # Validates error handling when AI effectiveness cannot be computed
    Given the scheduled evaluation pipeline is configured for the critical models
    When the pipeline fails to run or produces invalid results
    Then the AI effectiveness metric is not reported
    And an incident is raised with failure details

  @@regression @@negative
  Scenario: Error scenario: Finance baseline data missing
    # Validates error handling when cost baseline inputs are absent
    Given pre-implementation cost baseline data is missing
    When the business impact metric is calculated
    Then the system reports a baseline data validation error
    And the cost reduction metric is marked as not measurable
