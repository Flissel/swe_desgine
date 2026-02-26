@@smoke @@regression
Feature: Workflow Routing Verification
  As a QA Engineer
  I want to Verify that intelligent routing assigns billing tasks to appropriate agents based on type and complexity with acceptable accuracy and latency
  So that Ensures operational efficiency and reduces misrouted tasks, supporting Finance and Operations reliability

  Background:
    Given the routing engine is deployed and monitoring is enabled in the test environment

  @@smoke @@regression @@happy-path
  Scenario Outline: Routing accuracy meets target across task types and complexity
    # Validates accuracy against labeled dataset by task type and complexity
    Given a labeled dataset of billing tasks with expected agent assignments
    When routing assignments are generated for each task in the dataset
    Then the accuracy by task type and complexity is at least 95 percent
    And the accuracy report is stored for audit

    Examples:
      | task_type | complexity |
      | Invoice Dispute | High |
      | Payment Posting | Medium |
      | Refund Request | Low |

  @@regression @@performance @@happy-path
  Scenario Outline: Routing latency meets P95 target under production-like load
    # Validates routing decision latency at P95 with load testing
    Given a performance test environment with production-like load conditions
    When routing decisions are executed for a batch of tasks
    Then the P95 routing decision latency is at most 500 milliseconds per task
    And no routing timeouts are observed

    Examples:
      | concurrent_users | tasks_per_second |
      | 500 | 200 |
      | 1000 | 400 |

  @@regression @@boundary @@edge
  Scenario Outline: Edge case: Accuracy at the minimum acceptable threshold
    # Ensures routing accuracy at exactly the boundary passes
    Given a labeled dataset with expected assignments designed to yield 95 percent accuracy
    When routing assignments are evaluated against expected agents
    Then the measured accuracy equals 95 percent
    And the accuracy result is accepted as meeting the target

    Examples:
      | dataset_size | correct_assignments |
      | 1000 | 950 |

  @@regression @@negative @@error
  Scenario Outline: Error scenario: Misrouting rate exceeds weekly threshold
    # Validates error handling when misrouting rate is above 2 percent
    Given production audit logs and QA sampling reports for the current week
    When the misrouting rate is calculated from the reports
    Then the system flags a breach when misrouting rate is greater than 2 percent
    And an incident record is created for operational review

    Examples:
      | total_tasks | misrouted_tasks |
      | 10000 | 250 |
