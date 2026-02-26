@smoke @regression
Feature: AI Governance and Ethics Verification
  As a AI Governance Lead
  I want to Verify that AI decisions are explainable, bias detection is operational, and ethical guidelines are enforced across the AI lifecycle
  So that Ensures regulatory compliance, reduces ethical and financial risk, and builds stakeholder trust in AI-driven outcomes

  Background:
    Given the AI governance monitoring system is available

  @smoke @regression @happy-path
  Scenario: Explainability coverage meets target for audited sample
    # Validates that explainability coverage is at or above 95% for a statistically significant sample
    Given audit logs and explanation artifacts exist for the sampled AI decisions
    When the explainability coverage is calculated for the sample
    Then the coverage is at least 95%
    And all explanations are human-readable

  @regression @happy-path
  Scenario: Bias detection execution rate is 100% for model releases
    # Ensures every model release includes documented bias assessment
    Given CI/CD pipeline reports and governance artifacts are available for all releases
    When the bias detection execution rate is measured
    Then the rate is 100%
    And each release includes a documented bias assessment

  @regression @happy-path
  Scenario: Bias threshold compliance using disparate impact ratio
    # Validates disparate impact ratio is within the allowed range for protected attributes
    Given standardized bias metrics are computed on validation datasets
    When disparate impact ratios are evaluated for protected attributes
    Then each ratio is between 0.8 and 1.25 inclusive
    And the evaluation results are logged in governance artifacts

  @smoke @regression @happy-path
  Scenario: Ethical guideline adherence shows no critical violations
    # Ensures quarterly governance review finds no critical violations
    Given a quarterly governance review is completed against the approved ethical framework
    When the ethical compliance checklist is evaluated
    Then no critical violations are present
    And the review is approved by the governance board

  @regression @boundary
  Scenario: Explainability coverage boundary at 95%
    # Checks boundary condition for explainability coverage
    Given audit logs contain explanations for 95% of sampled decisions
    When explainability coverage is validated against the target
    Then the coverage is accepted as compliant
    And no exceptions are raised

  @regression @boundary
  Scenario: Bias threshold compliance boundary values
    # Validates boundary values for disparate impact ratio
    Given disparate impact ratios are computed for protected attributes
    When each ratio is compared to the allowed range
    Then ratios at 0.8 and 1.25 are accepted
    And the evaluation outcome is recorded

  @regression @negative @error
  Scenario: Explainability coverage below target fails compliance
    # Error scenario when explainability coverage is below 95%
    Given audit logs contain explanations for less than 95% of sampled decisions
    When explainability coverage is measured
    Then the compliance check fails
    And a remediation ticket is created

  @regression @negative @error
  Scenario: Missing bias assessment for a release
    # Error scenario when a model release lacks documented bias assessment
    Given one model release is missing a documented bias assessment
    When the bias detection execution rate is calculated
    Then the rate is below 100%
    And the release is blocked pending assessment

  @regression @negative @edge
  Scenario Outline: Scenario Outline: Disparate impact ratio out of range
    # Edge case where disparate impact ratio falls outside compliance range
    Given a disparate impact ratio of <ratio> is computed for a protected attribute
    When the ratio is validated against the compliance range
    Then the compliance check fails
    And a bias mitigation plan is required

    Examples:
      | ratio |
      | 0.79 |
      | 1.26 |

  @regression @negative @error
  Scenario Outline: Scenario Outline: Ethical compliance checklist has critical violations
    # Error scenario when critical ethical violations are present
    Given the quarterly governance review reports <critical_count> critical violations
    When the ethical compliance checklist is evaluated
    Then the adherence check fails
    And the system is flagged for corrective action

    Examples:
      | critical_count |
      | 1 |
      | 3 |
