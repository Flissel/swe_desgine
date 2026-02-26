@smoke @regression
Feature: Agenten-basierte Rechnungsgenerierung Zuverlässigkeit und Durchsatz
  As a QA Engineer
  I want to Verify that AI-agent-based invoice generation runs end-to-end without human intervention and meets reliability and throughput expectations in production-like conditions
  So that Ensures the finance and operations teams can rely on fully automated invoice creation, reducing manual effort and operational risk

  Background:
    Given the AI-agent invoice generation pipeline is deployed with production-like configurations and monitoring enabled

  @@smoke @@regression @@happy-path
  Scenario: Automation rate meets target over 30-day audit window
    # Validates that automated invoice generation without human intervention is at or above 99% over a 30-day period
    Given system logs and workflow audit trails are available for the last 30 days
    When the automation rate is calculated from invoices generated without human intervention
    Then the automation rate should be at least 99%
    And the calculation includes all invoice types and channels

  @@regression @@happy-path
  Scenario: Generation success rate for 10,000 representative jobs
    # Validates the success rate meets or exceeds 99.5% for a large batch in staging
    Given 10,000 representative invoice generation jobs are queued in staging
    When the jobs are executed and completed vs failed jobs are recorded
    Then the generation success rate should be at least 99.5%
    And failures are verified as non-retryable for exclusion from success count

  @@regression @@happy-path
  Scenario: Average end-to-end generation time meets 2-minute SLA
    # Ensures average processing time per invoice is within the SLA across staging and production monitoring
    Given invoice generation jobs are submitted in staging and production monitoring is enabled
    When average end-to-end time from submission to invoice creation is measured
    Then the average end-to-end generation time should be less than or equal to 2 minutes
    And outliers above 5 minutes are flagged for review

  @@regression @@happy-path
  Scenario: Automatic recovery from transient faults meets target
    # Validates that automatic retries recover from transient faults without human intervention
    Given controlled transient faults are injected into the invoice generation pipeline
    When automatic retries are triggered by the system
    Then the error recovery rate should be at least 95%
    And no manual intervention is required for recovered jobs

  @@regression @@edge
  Scenario Outline: Edge case: Success rate at boundary for batch size variations
    # Checks boundary conditions for success rate when batch size varies near typical load
    Given a batch of invoice jobs is executed in staging
    When the generation success rate is computed
    Then the success rate should be at least 99.5%
    And the batch completion is validated against expected job counts

    Examples:
      | batch_size | expected_success_rate |
      | 9999 | >=99.5% |
      | 10000 | >=99.5% |
      | 10001 | >=99.5% |

  @@regression @@boundary
  Scenario Outline: Boundary condition: Average generation time exactly at 2 minutes
    # Validates SLA boundary when average time equals 2 minutes
    Given invoice jobs are processed under controlled load
    When average end-to-end generation time is calculated
    Then the average time should be less than or equal to 2 minutes
    And the measurement window includes at least 1,000 invoices

    Examples:
      | average_time_minutes |
      | 2.0 |

  @@regression @@negative
  Scenario Outline: Error scenario: Automation rate below target
    # Ensures failure is reported when automation rate is less than 99%
    Given system logs indicate a 30-day automation rate below target
    When the automation rate is evaluated against the target
    Then the system should report a compliance failure
    And the report should list invoices requiring human intervention

    Examples:
      | automation_rate |
      | 98.9% |

  @@regression @@negative
  Scenario Outline: Error scenario: Recovery rate below target after transient faults
    # Validates that insufficient recovery rate triggers an error condition
    Given transient faults are injected during invoice generation
    When the automatic recovery rate is calculated
    Then the system should report a recovery SLA breach
    And failed retries are logged with root-cause metadata

    Examples:
      | recovery_rate |
      | 94.5% |
