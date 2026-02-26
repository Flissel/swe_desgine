@smoke @regression
Feature: US-019 Data Strategy for Continuous Learning Verification
  As a QA Engineer
  I want to Verify automated data quality checks and continuous model optimization are executed reliably in the production pipeline
  So that Ensures trustworthy data and sustained model performance for Finance, Operations, and IT/DevOps

  Background:
    Given the production pipeline monitoring dashboards and logs are доступ to QA with read permissions

  @happy-path @smoke @regression
  Scenario: Verify data quality rule coverage meets target per batch
    # Happy path for data quality coverage at or above 95%
    Given the system is reviewing automated data validation logs and rule execution reports for a batch
    When I measure the percentage of critical data rules executed
    Then the coverage result should be at least 95%
    And the batch is marked as compliant in the quality report

  @boundary @regression
  Scenario Outline: Data quality coverage boundary at 95%
    # Boundary condition for rule execution coverage exactly at target
    Given a batch has <executed_rules> of <critical_rules> critical data rules executed
    When I calculate the executed coverage percentage
    Then the coverage should be <expected_result>

    Examples:
      | executed_rules | critical_rules | expected_result |
      | 95 | 100 | compliant |

  @edge-case @regression
  Scenario Outline: Detect data quality failure within alert SLA
    # Edge case for detection time near the 15 minute target
    Given the system is measuring timestamps between ingestion and alert generation
    When a data quality failure occurs at <ingestion_time> and alert is generated at <alert_time>
    Then the detection time should be <expected_result>

    Examples:
      | ingestion_time | alert_time | expected_result |
      | 2025-01-10T10:00:00Z | 2025-01-10T10:15:00Z | within SLA |
      | 2025-01-10T10:00:00Z | 2025-01-10T10:16:00Z | SLA breach |

  @negative @regression
  Scenario Outline: Model performance drift exceeds allowed threshold
    # Error scenario when model performance degrades beyond 2% over 30 days
    Given the system compares rolling model metrics against the baseline over 30 days
    When the performance degradation is <degradation_percent>
    Then the drift assessment should be <expected_result>
    And an alert is raised for model performance drift when non-compliant

    Examples:
      | degradation_percent | expected_result |
      | 1.9% | compliant |
      | 2.1% | non-compliant |

  @happy-path @regression
  Scenario Outline: Retraining schedule adherence within SLA window
    # Scenario outline verifying all scheduled retraining runs complete within SLA
    Given the system audits MLOps pipeline schedules and completion logs
    When a retraining run scheduled at <scheduled_time> completes at <completion_time> with SLA <sla_minutes> minutes
    Then the retraining adherence should be <expected_result>

    Examples:
      | scheduled_time | completion_time | sla_minutes | expected_result |
      | 2025-01-10T01:00:00Z | 2025-01-10T01:30:00Z | 60 | compliant |
      | 2025-01-10T01:00:00Z | 2025-01-10T02:10:00Z | 60 | non-compliant |
