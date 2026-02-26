@smoke @regression
Feature: US-012 Exception Handling Verification
  As a QA Engineer
  I want to validate that LLMs and specialized agents automatically detect and resolve exceptions within operational boundaries
  So that ensures uninterrupted operations, minimizes manual intervention, and reduces financial risk from unhandled exceptions

  Background:
    Given the controlled fault-injection test environment is configured for finance and operations workflows

  @happy-path @smoke @regression
  Scenario: Happy path: Detection and remediation meet targets
    # Validates detection rate, auto-remediation success, MTTD, MTTR, and false positive rate all meet targets
    Given known exceptions are injected across finance and operations workflows
    When exception detection and remediation metrics are collected from monitoring tools and incident records
    Then detection rate is at least 95% of injected known exceptions
    And auto-remediation success rate is at least 85% of detected exceptions
    And mean time to detect is 2 minutes or less
    And mean time to resolve is 10 minutes or less for eligible exceptions
    And false positive rate is 5% or less of detections

  @regression @boundary
  Scenario Outline: Boundary conditions: Metrics at exact thresholds
    # Validates system behavior at target boundaries for all metrics
    Given a test run produces metric values at the boundary thresholds
    When the metrics are evaluated against acceptance criteria
    Then the run is marked as passing because all metrics meet minimum or maximum thresholds

    Examples:
      | detection_rate | auto_remediation_rate | mttd | mttr | false_positive_rate |
      | 95% | 85% | 2 minutes | 10 minutes | 5% |

  @regression @edge
  Scenario Outline: Edge case: Low volume exceptions with mixed workflows
    # Ensures calculations remain accurate when only a small number of exceptions are injected across workflows
    Given a small set of known exceptions is injected across finance and operations workflows
    When detection and remediation metrics are calculated for the test run
    Then metrics are computed correctly without rounding errors
    And all metrics meet their respective targets

    Examples:
      | injected_exceptions | detected_exceptions | remediated_exceptions | mttd | mttr | false_positives |
      | 20 | 19 | 17 | 1.8 minutes | 9.5 minutes | 1 |

  @negative @regression
  Scenario Outline: Error scenario: Metrics fall below targets
    # Validates failure handling when one or more metrics do not meet targets
    Given a test run produces metrics below target thresholds
    When the metrics are evaluated against acceptance criteria
    Then the run is marked as failing
    And the failing metrics are reported in the test results

    Examples:
      | detection_rate | auto_remediation_rate | mttd | mttr | false_positive_rate |
      | 92% | 80% | 2.5 minutes | 12 minutes | 7% |

  @regression @data-driven
  Scenario Outline: Scenario Outline: Metric evaluation across varied runs
    # Data-driven validation for each acceptance criterion using varied run data
    Given test run <run_id> has injected <injected> known exceptions and detected <detected> exceptions
    When auto-remediation resolved <resolved> exceptions and monitoring reports MTTD <mttd> and MTTR <mttr>
    Then detection rate is evaluated against 95% target
    And auto-remediation success rate is evaluated against 85% target
    And false positive rate <false_positive_rate> is evaluated against 5% target

    Examples:
      | run_id | injected | detected | resolved | mttd | mttr | false_positive_rate |
      | R1 | 100 | 96 | 85 | 1.2 minutes | 8 minutes | 4% |
      | R2 | 200 | 190 | 160 | 2 minutes | 10 minutes | 5% |
