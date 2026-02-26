@@smoke @@regression
Feature: US-023 Bank Account Creation NFR Verification
  As a QA Engineer
  I want to verify that the bank account creation service meets performance, reliability, and security non-functional expectations
  So that ensures users can create bank accounts quickly, reliably, and securely without service disruption or data leakage

  Background:
    Given the account creation service is deployed in a controlled test environment with monitoring enabled

  @@smoke @@regression @@happy-path
  Scenario: P95 latency meets target under representative load
    # Validates p95 response time for account creation is within target
    Given the system is under load testing with representative payloads
    When I measure the p95 response time for account creation
    Then the p95 response time should be less than or equal to 2 seconds
    And no load test errors are recorded

  @@regression @@happy-path
  Scenario Outline: Success rate meets target over 7 days
    # Checks account creation success rate meets minimum threshold over a 7-day window
    Given the system is under monitoring production logs for a 7-day period
    When I calculate the successful account creation rate
    Then the success rate should be greater than or equal to <success_rate_threshold>
    And the calculation window should cover exactly 7 days

    Examples:
      | success_rate_threshold |
      | 99.5% |

  @@regression @@negative @@error
  Scenario Outline: Availability below target triggers failure
    # Negative scenario to ensure availability below target is detected
    Given the system is under synthetic uptime checks with incident tracking
    When I measure monthly availability for the account creation endpoint
    Then the measured availability should be greater than or equal to <availability_threshold>
    And a failure is logged if availability is below the threshold

    Examples:
      | availability_threshold |
      | 99.9% |

  @@regression @@edge @@boundary
  Scenario: Audit log completeness for account creation events
    # Verifies audit logs contain all required fields for every creation event
    Given the system audit logs are available for review
    When I reconcile audit logs against account creation transaction records
    Then 100% of account creation events should be logged
    And each log entry should include user ID, timestamp, and request ID
