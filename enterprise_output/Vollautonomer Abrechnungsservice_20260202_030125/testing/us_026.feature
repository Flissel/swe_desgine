@smoke @regression
Feature: US-026 Verify Invoice Creation Agent Non-Functional Targets
  As a QA Engineer
  I want to Verify the invoice creation agent meets non-functional quality, reliability, and throughput targets across data aggregation, tax calculation, validation, and email dispatch.
  So that Ensures consistent, compliant, and timely invoice delivery with minimal operational risk.

  Background:
    Given the invoice creation agent is deployed with monitoring enabled and synthetic order data is available

  @@smoke @@regression @@happy-path
  Scenario: Happy path: End-to-end invoice generation meets latency target
    # Validates 95th percentile latency is within 5 seconds under standard run load
    Given the system is under run load tests using synthetic orders
    When measuring end-to-end invoice generation latency from data aggregation to template render
    Then the 95th percentile latency is less than or equal to 5 seconds per invoice
    And the measurement is based on at least 1000 invoices

  @@regression @@boundary
  Scenario Outline: Boundary: Tax calculation accuracy meets threshold across jurisdictions
    # Ensures tax calculator matches reference rules at or above 99.9% with boundary values
    Given the system is under compare TaxCalculator outputs against a verified tax rules dataset
    When measuring tax calculation accuracy for jurisdiction "<jurisdiction>" and rate "<rate>"
    Then the match rate is greater than or equal to 99.9%
    And all mismatches are logged with order ids and expected vs actual tax

    Examples:
      | jurisdiction | rate |
      | DE | 19.0% |
      | UK | 20.0% |
      | FR | 5.5% |

  @@regression @@edge
  Scenario Outline: Edge case: Data aggregation completeness for required fields
    # Validates 100% required fields present before template rendering
    Given the system is under audit aggregated data records against the required-field schema
    When measuring data aggregation completeness for dataset "<dataset_type>"
    Then 100% of required fields are present for invoice generation
    And any missing field is reported with the source system identifier

    Examples:
      | dataset_type |
      | single-line-item |
      | multi-line-item |
      | cross-border-order |

  @@regression @@negative
  Scenario Outline: Error scenario: Email dispatch success rate falls below target
    # Detects failure when first-attempt success rate is below 99.0%
    Given the system is under monitor EmailSender delivery status codes and bounces over a controlled test run
    When measuring email dispatch success rate for campaign "<campaign_id>"
    Then the test fails if first-attempt success rate is less than 99.0%
    And failed sends are classified by SMTP status and bounce type

    Examples:
      | campaign_id |
      | TEST-CAMPAIGN-LOW-SUCCESS |

  @@regression @@boundary
  Scenario Outline: Boundary: Invoice validation success rate at threshold
    # Ensures validation success rate is at or above 99.5% during batch tests
    Given the system is under execute batch tests and log validation outcomes using the validation module
    When measuring invoice validation success rate for batch size "<batch_size>"
    Then the success rate is greater than or equal to 99.5% without manual intervention
    And invalid invoices are quarantined with validation error codes

    Examples:
      | batch_size |
      | 1000 |
      | 5000 |
