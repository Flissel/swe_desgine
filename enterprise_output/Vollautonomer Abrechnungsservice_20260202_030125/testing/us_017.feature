@@smoke @@regression
Feature: Verify Zero-Trust controls and AI-driven threat detection/response
  As a Security Team
  I want to verify Zero-Trust controls and AI-driven threat detection/response meet defined security outcomes in autonomous systems
  So that reduces breach risk and ensures resilient operations while satisfying stakeholder security expectations

  Background:
    Given the autonomous system security monitoring and audit tooling are operational

  @@smoke @@regression @@happy-path
  Scenario Outline: Meet Zero-Trust enforcement target across services
    # Validates that automated compliance scans show Zero-Trust enforcement at or above the target threshold
    Given the system is under audit for service mesh and IAM policies using automated compliance scans
    When I measure the percentage of services enforcing mTLS, least privilege, and continuous authorization
    Then the Zero-Trust enforcement percentage should be greater than or equal to 95 percent

    Examples:
      | measured_percentage |
      | 97 |
      | 100 |

  @@smoke @@regression @@happy-path
  Scenario Outline: AI detection true positive rate meets target during red-team simulations
    # Ensures AI detection meets or exceeds true positive rate for simulated attacks
    Given the system is under red-team and adversarial simulations with ground truth labels
    When I measure the AI detection true positive rate for simulated attacks
    Then the true positive rate should be greater than or equal to 90 percent

    Examples:
      | true_positive_rate |
      | 90 |
      | 95 |

  @@regression @@happy-path
  Scenario Outline: AI detection false positive rate within limit over 30 days
    # Verifies false positive rate is at or below threshold over a representative period
    Given the system alert logs for a representative 30-day period are available
    When I measure the AI detection false positive rate
    Then the false positive rate should be less than or equal to 5 percent

    Examples:
      | false_positive_rate |
      | 5 |
      | 3 |

  @@regression @@happy-path
  Scenario Outline: MTTD for high-severity threats meets target
    # Confirms mean time to detect high-severity threats is within the required threshold
    Given attack simulation timestamps and alert creation timestamps are captured
    When I calculate the mean time to detect for high-severity threats
    Then the MTTD should be less than or equal to 5 minutes

    Examples:
      | mttd_minutes |
      | 5 |
      | 2 |

  @@regression @@happy-path
  Scenario Outline: MTTR for high-severity threats meets target
    # Confirms mean time to respond/contain high-severity threats is within the required threshold
    Given alert creation timestamps and automated containment timestamps are captured
    When I calculate the mean time to respond/contain for high-severity threats
    Then the MTTR should be less than or equal to 15 minutes

    Examples:
      | mttr_minutes |
      | 15 |
      | 10 |

  @@regression @@boundary
  Scenario Outline: Boundary validation for Zero-Trust enforcement threshold
    # Validates boundary values around the Zero-Trust enforcement threshold
    Given the system is under audit for service mesh and IAM policies using automated compliance scans
    When I measure the percentage of services enforcing Zero-Trust policies
    Then the result should be evaluated against the 95 percent threshold

    Examples:
      | measured_percentage | expected_result |
      | 94.9 | fail |
      | 95.0 | pass |
      | 95.1 | pass |

  @@regression @@edge-case
  Scenario Outline: Edge case for low volume of simulated attacks
    # Assesses true positive rate calculation when simulated attacks are minimal
    Given the system is under red-team simulations with a minimal set of labeled attacks
    When I calculate the AI detection true positive rate
    Then the true positive rate should be computed accurately and compared to the 90 percent target

    Examples:
      | total_attacks | detected_attacks | expected_result |
      | 10 | 9 | pass |
      | 10 | 8 | fail |

  @@regression @@negative @@error
  Scenario: Error handling when audit data is missing
    # Ensures the system reports an error when required audit data is unavailable
    Given the compliance scan results for service mesh and IAM policies are unavailable
    When I attempt to measure Zero-Trust enforcement percentage
    Then the system should return a data availability error and no compliance decision

  @@regression @@negative @@error
  Scenario: Error handling when timestamps are inconsistent
    # Validates that invalid timestamps are rejected for MTTD and MTTR calculations
    Given attack simulation timestamps and alert timestamps contain out-of-order values
    When I calculate MTTD and MTTR for high-severity threats
    Then the system should flag invalid timestamp data and prevent calculation
