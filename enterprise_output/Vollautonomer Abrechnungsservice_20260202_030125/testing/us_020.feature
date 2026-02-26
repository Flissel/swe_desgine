@@smoke @@regression
Feature: US-020 Verify: Innovationsökosystem
  As a Operations Manager
  I want to Audit partnerships and standards adoption to confirm the innovation ecosystem meets the defined targets
  So that Ensures strategic ecosystem objectives are met, enabling interoperability, vendor diversity, and long-term scalability

  Background:
    Given the audit period and data sources are configured for the innovation ecosystem review

  @@happy-path @@smoke @@regression
  Scenario: Happy path: All targets met across partnerships, standards, and API integration
    # Validates that each metric meets or exceeds its target under normal conditions
    Given the system is under Review signed partnership agreements in the vendor management system conditions
    When measuring Number of active technology provider partnerships
    Then the result meets target: >= 50
    And the partnership count is reported in the audit summary

  @@boundary @@regression
  Scenario: Boundary conditions: Metrics exactly at target thresholds
    # Ensures boundary values are accepted as meeting targets
    Given the system is under Inspect governance documents and compliance attestations conditions
    When measuring Number of relevant industry standards formally adopted
    Then the result meets target: >= 2
    And the standards list is complete and approved

  @@edge @@regression
  Scenario: Edge case: Percentage of partners integrated via standardized APIs just above threshold
    # Validates acceptance when the integration percentage marginally exceeds the target
    Given the system is under Analyze integration registry and API management platform reports conditions
    When measuring Percentage of partners integrated via standardized APIs or protocols
    Then the result meets target: >= 80%
    And the integration percentage is computed from valid partner counts

  @@negative @@regression
  Scenario: Error scenario: Missing source data prevents audit calculation
    # Ensures the system reports an error when required data sources are unavailable
    Given the vendor management system data source is unavailable
    When measuring Number of active technology provider partnerships
    Then an audit error is reported indicating missing partnership data
    And no target comparison is performed for the missing metric

  @@regression @@data-driven
  Scenario Outline: Scenario Outline: Data-driven validation of targets across metrics
    # Verifies target compliance using multiple data sets for each metric
    Given the system is under <condition> conditions
    When measuring <metric>
    Then the result is <result>
    And the audit records include <evidence>

    Examples:
      | condition | metric | result | evidence |
      | Review signed partnership agreements in the vendor management system | Number of active technology provider partnerships | meets target: >= 50 | a list of active partners |
      | Inspect governance documents and compliance attestations | Number of relevant industry standards formally adopted | meets target: >= 2 | approved standards documentation |
      | Analyze integration registry and API management platform reports | Percentage of partners integrated via standardized APIs or protocols | meets target: >= 80% | integration registry totals |
