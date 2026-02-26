@smoke @regression
Feature: US-024 Company Settings Update Propagation Reliability
  As a DevOps Engineer
  I want to Verify that company settings updates are applied reliably and propagate across all relevant services within defined operational limits
  So that Ensures configuration changes are consistent, timely, and auditable, reducing operational risk for Finance and Operations

  Background:
    Given company settings services, audit logging, and monitoring are enabled in staging and production

  @smoke @regression @happy-path
  Scenario Outline: P95 propagation time meets target across environments
    # Validates that update propagation time meets the P95 <= 2 minutes target
    Given a valid settings change request is submitted in <environment>
    When I measure end-to-end propagation time across all dependent services
    Then the P95 propagation time is less than or equal to 2 minutes
    And all dependent services reflect the updated settings

    Examples:
      | environment |
      | staging |
      | production |

  @regression @happy-path
  Scenario: Update success rate meets 99.9% over rolling 30-day window
    # Validates success rate based on deployment logs and API responses
    Given deployment logs and API responses are available for the last 30 days
    When I calculate the successful update rate
    Then the success rate is greater than or equal to 99.9%

  @regression @happy-path
  Scenario Outline: Audit log completeness for sampled updates
    # Validates audit logs contain required fields for each update
    Given a sample of <sample_size> recent update events is selected
    When I review the audit log entries for each update
    Then 100% of updates include user, timestamp, and change details

    Examples:
      | sample_size |
      | 10 |
      | 50 |

  @regression @boundary
  Scenario Outline: Propagation time boundary at exactly 2 minutes
    # Validates boundary condition where P95 equals target limit
    Given a valid settings change request is submitted in <environment>
    When I measure end-to-end propagation time across all dependent services
    Then the P95 propagation time equals 2 minutes
    And the update is considered within operational limits

    Examples:
      | environment |
      | staging |
      | production |

  @regression @negative
  Scenario Outline: Success rate just below target triggers failure
    # Validates error condition when update success rate is below 99.9%
    Given deployment logs and API responses are available for the last 30 days
    When I calculate the successful update rate as <success_rate>
    Then the result does not meet the 99.9% success rate target
    And the system reports a compliance failure for update reliability

    Examples:
      | success_rate |
      | 99.89% |

  @regression @negative
  Scenario Outline: Propagation time exceeds target due to service outage
    # Validates error handling when a dependent service is unavailable
    Given a dependent service is unavailable in <environment>
    When a valid settings change request is submitted
    Then propagation time exceeds 2 minutes
    And the update is flagged as not meeting the propagation time target

    Examples:
      | environment |
      | staging |
      | production |

  @regression @negative
  Scenario Outline: Audit log missing required field
    # Validates error scenario where audit log entry is incomplete
    Given a settings update has been performed by user <user_id>
    When I review the audit log entry for that update
    Then the audit log entry is missing <missing_field>
    And the audit log completeness check fails

    Examples:
      | user_id | missing_field |
      | user-1001 | timestamp |
      | user-1002 | change details |

  @regression @edge
  Scenario Outline: Edge case with simultaneous updates across services
    # Validates reliability when multiple settings updates occur concurrently
    Given <concurrent_updates> settings updates are submitted concurrently in <environment>
    When I measure propagation time and success rate across all dependent services
    Then the P95 propagation time is less than or equal to 2 minutes
    And the update success rate remains greater than or equal to 99.9%

    Examples:
      | concurrent_updates | environment |
      | 20 | staging |
      | 50 | production |
