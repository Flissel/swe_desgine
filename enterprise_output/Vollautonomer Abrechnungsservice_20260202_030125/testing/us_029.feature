@smoke @regression
Feature: Steuerberechnungs-Agent quality and compliance verification
  As a QA Engineer
  I want to Verify the Steuerberechnungs-Agent computes taxes accurately and reliably within agreed performance and export standards
  So that Ensures compliant tax calculations, smooth finance operations, and dependable system integration

  Background:
    Given the Steuerberechnungs-Agent is deployed in the staging environment with access to audited reference datasets

  @happy-path @regression @smoke
  Scenario: Accuracy meets target for audited tax rule test cases
    # Validates tax calculation correctness for MwSt., Reverse Charge, and Steuerkennzeichnung against approved datasets
    Given the automated test suite uses TaxRateFinder and VATCalculator with audited reference datasets
    When tax calculation accuracy is measured against the approved tax rule test cases
    Then the correctness is at least 99.5%
    And the suite reports no critical mismatches in MwSt., Reverse Charge, and Steuerkennzeichnung

  @happy-path @performance @regression
  Scenario: Performance latency stays within 95th percentile target
    # Validates computation latency under normal synthetic load
    Given performance testing is executed with synthetic invoices under normal load in staging
    When computation latency per invoice is profiled
    Then the 95th percentile latency is less than or equal to 500 ms
    And no latency spikes exceed operational thresholds

  @happy-path @regression
  Scenario: DATEV exports are schema compliant for standard cases
    # Validates DATEVExporter output against schema and sample imports
    Given DATEVExporter output is generated for standard invoices
    When the export is validated against the DATEV schema and sample import rules
    Then all exports conform to the schema with zero errors
    And sample imports complete without validation failures

  @happy-path @regression @monitoring
  Scenario: Service availability meets monthly uptime target
    # Validates monthly uptime for tax calculation service from monitoring logs
    Given service health checks and incident logs are collected via DevOps monitoring tools
    When monthly uptime is calculated for the tax calculation service
    Then the uptime is at least 99.9%
    And no unresolved incidents are present for the period

  @boundary @regression
  Scenario: Boundary latency at 95th percentile threshold
    # Checks boundary condition when latency equals the maximum allowed value
    Given a controlled load test is executed with synthetic invoices under normal load
    When the 95th percentile computation latency is recorded
    Then the 95th percentile latency equals 500 ms
    And the test is marked as passing within the performance target

  @edge @regression
  Scenario: Edge case handling for zero-value and negative-value invoices
    # Verifies tax calculations for edge cases that may affect MwSt. and Reverse Charge
    Given the automated test suite includes invoices with zero and negative taxable amounts
    When tax calculations are executed for these invoices
    Then the computed tax values match the audited reference dataset outcomes
    And no invalid Steuerkennzeichnung values are produced

  @regression @data-driven
  Scenario Outline: Scenario Outline: Accuracy across tax rule categories
    # Data-driven validation for correctness across tax rule categories
    Given the test suite uses the audited reference dataset for <rule_category>
    When correctness is calculated for <rule_category> cases
    Then the correctness is at least <expected_correctness>
    And all deviations are logged for review

    Examples:
      | rule_category | expected_correctness |
      | MwSt. | 99.5% |
      | Reverse Charge | 99.5% |
      | Steuerkennzeichnung | 99.5% |

  @regression @data-driven
  Scenario Outline: Scenario Outline: DATEV export schema validation for multiple invoice types
    # Data-driven validation of DATEV export for different invoice structures
    Given a DATEV export is generated for <invoice_type> invoices
    When the export is validated against the DATEV schema
    Then schema validation returns zero errors
    And the export passes sample import checks

    Examples:
      | invoice_type |
      | domestic standard |
      | intra-EU reverse charge |
      | credit note |

  @negative @regression
  Scenario: Error scenario when reference dataset is missing
    # Ensures the system fails safely and reports missing dataset errors
    Given the audited reference dataset for tax rules is unavailable
    When the automated accuracy test suite is executed
    Then the suite reports a missing dataset error
    And no accuracy metrics are reported as successful

  @negative @regression
  Scenario: Error scenario for invalid DATEV schema version
    # Ensures schema validation fails for invalid DATEV schema versions
    Given DATEVExporter is configured with an unsupported schema version
    When the export is validated against the DATEV schema
    Then schema validation reports errors
    And the export is marked as non-conforming

  @boundary @regression @monitoring
  Scenario: Boundary condition for monthly uptime at minimum threshold
    # Validates availability when uptime equals the minimum acceptable threshold
    Given monitoring logs show total uptime minutes equal to 99.9% for the month
    When the monthly uptime calculation is performed
    Then the service meets the minimum uptime requirement
    And no breach alerts are triggered
