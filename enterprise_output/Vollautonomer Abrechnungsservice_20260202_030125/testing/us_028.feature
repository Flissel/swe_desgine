@@smoke @@regression
Feature: US-028 Verify Mahnagent operational reliability and correctness
  As a QA Engineer
  I want to verify that the Mahnagent meets operational reliability and correctness requirements for the dunning process
  So that ensures overdue invoice handling is accurate, timely, and resilient, reducing financial risk and operational delays

  Background:
    Given the Mahnagent services are deployed in a test environment with observability enabled

  @@smoke @@regression @@happy-path
  Scenario: Happy path: All accuracy, performance, and uptime targets are met
    # Validates that each acceptance criterion meets its target under normal conditions
    Given the validated test suites and benchmark datasets are available
    When the system executes accuracy, batch, cost, performance, and uptime measurements
    Then Dunning level accuracy is at least 99.5 percent
    And Dunning letter generation success rate is at least 99.0 percent
    And Cost calculation accuracy is at least 99.5 percent
    And end-to-end p95 latency per invoice is at most 2 seconds
    And monthly uptime for dunning operations is at least 99.9 percent

  @@regression @@boundary
  Scenario Outline: Boundary conditions: Metrics exactly at target thresholds
    # Ensures the system passes when metrics are exactly on the acceptance thresholds
    Given the system has measured results at threshold values
    When the results are evaluated against acceptance criteria
    Then the evaluation status is pass for each metric

    Examples:
      | metric | measured_value | threshold | expected_result |
      | Dunning level accuracy | 99.5% | >= 99.5% | pass |
      | Letter generation success rate | 99.0% | >= 99.0% | pass |
      | Cost calculation accuracy | 99.5% | >= 99.5% | pass |
      | p95 latency per invoice | 2.0s | <= 2.0s | pass |
      | Monthly uptime | 99.9% | >= 99.9% | pass |

  @@regression @@edge
  Scenario Outline: Edge case: High-volume batch processing at typical workload peak
    # Validates performance and batch success rate during peak but typical workload
    Given a batch of invoices at typical peak volume is prepared
    When the system generates dunning letters and processes invoices end-to-end
    Then the letter generation success rate meets or exceeds 99.0 percent
    And the p95 latency per invoice meets or is below 2 seconds

    Examples:
      | invoice_count | workload_profile | expected_success_rate | expected_p95_latency |
      | 10000 | typical peak | >= 99.0% | <= 2s |

  @@regression @@negative
  Scenario Outline: Error scenario: Dunning level accuracy below target
    # Validates failure when DunningLevelCalculator accuracy is below target
    Given the validated overdue invoice scenarios are executed
    When the measured Dunning level accuracy is below the target
    Then the evaluation status is fail for Dunning level accuracy

    Examples:
      | measured_accuracy | threshold | expected_result |
      | 99.2% | >= 99.5% | fail |

  @@regression @@negative
  Scenario Outline: Error scenario: Letter generation error rate above threshold
    # Validates failure when DunningLetterGenerator has too many errors
    Given a batch run is executed with injected generation faults
    When the measured letter generation success rate is below target
    Then the evaluation status is fail for letter generation success rate

    Examples:
      | measured_success_rate | threshold | expected_result |
      | 98.7% | >= 99.0% | fail |

  @@regression @@negative
  Scenario Outline: Error scenario: Cost calculation accuracy below target
    # Validates failure when CostCalculator accuracy misses the benchmark
    Given benchmark invoice cases with expected fees and interest are provided
    When the CostCalculator results are compared to the benchmark
    Then the evaluation status is fail for cost calculation accuracy

    Examples:
      | measured_accuracy | threshold | expected_result |
      | 99.3% | >= 99.5% | fail |

  @@regression @@negative
  Scenario Outline: Error scenario: p95 latency exceeds target
    # Validates failure when end-to-end processing time per invoice is too slow
    Given performance tests are executed under typical workload
    When the measured p95 latency exceeds the target
    Then the evaluation status is fail for performance

    Examples:
      | measured_p95_latency | threshold | expected_result |
      | 2.3s | <= 2.0s | fail |

  @@regression @@negative
  Scenario Outline: Error scenario: Monthly uptime below target
    # Validates failure when uptime is below the target
    Given monthly uptime is calculated from observability tools and incident logs
    When the measured uptime is below the target
    Then the evaluation status is fail for uptime

    Examples:
      | measured_uptime | threshold | expected_result |
      | 99.7% | >= 99.9% | fail |
