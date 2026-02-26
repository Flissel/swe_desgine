@smoke @regression
Feature: Verify Organizational AI-First Adoption
  As a Change Management Lead
  I want to verify organizational adoption of AI-first decision-making and implementation of new AI-focused roles
  So that ensures cultural transformation is measurable, sustained, and supported across Finance, Operations, and IT/DevOps

  Background:
    Given the audit data sources for decision logs, HR role catalog, LMS reports, and governance documents are available

  @@smoke @@regression @@happy-path
  Scenario: AI-supported strategic decisions meet target within 6 months
    # Validates the decision log metric meets or exceeds 70% within the time window
    Given the system is under audit of decision logs and meeting minutes across stakeholder teams for the last 6 months
    When the percentage of strategic decisions documented with AI-supported evidence is calculated
    Then the result is at least 70%
    And the calculation period is exactly 6 months

  @@smoke @@regression @@happy-path
  Scenario: AI-first role profiles defined and staffed meet targets
    # Validates role definition and staffing thresholds are met
    Given the system is under review of HR role catalog and hiring records
    When the number of AI-first role profiles defined and the staffing percentage are measured
    Then at least 5 AI-first roles are defined
    And at least 80% of the defined roles are staffed

  @@regression @@happy-path
  Scenario: AI literacy training completion meets 90% within 4 months
    # Validates LMS completion rate across Finance, Operations, and IT/DevOps meets the target
    Given the system is under review of LMS completion reports for Finance, Operations, and IT/DevOps
    When the AI literacy training completion rate is measured for the last 4 months
    Then the completion rate is at least 90%

  @@regression @@happy-path
  Scenario: AI governance adoption meets policy application target
    # Validates that approved policies are applied in at least 75% of new initiatives
    Given the system is under governance documentation review and project intake audits
    When the percentage of new initiatives applying approved AI governance policies is measured
    Then the application rate is at least 75%
    And the policies are approved and published

  @@regression @@boundary
  Scenario Outline: Boundary conditions for decision log compliance
    # Checks boundary outcomes around the 70% decision documentation target
    Given the system is under audit of decision logs and meeting minutes across stakeholder teams for the last 6 months
    When the percentage of strategic decisions documented with AI-supported evidence is calculated as <percentage>
    Then the compliance result is <outcome>

    Examples:
      | percentage | outcome |
      | 69% | non-compliant |
      | 70% | compliant |
      | 71% | compliant |

  @@regression @@edge
  Scenario Outline: Edge case for staffing ratio when roles defined minimum
    # Validates staffing ratio calculation at minimum role count
    Given the system is under review of HR role catalog and hiring records
    When there are <roles_defined> AI-first roles defined and <roles_staffed> roles staffed
    Then the staffing percentage is <staffing_percentage>
    And the staffing target result is <outcome>

    Examples:
      | roles_defined | roles_staffed | staffing_percentage | outcome |
      | 5 | 4 | 80% | compliant |
      | 5 | 3 | 60% | non-compliant |

  @@regression @@negative
  Scenario: Error scenario when LMS report is missing
    # Validates error handling when required LMS data is unavailable
    Given the LMS completion reports are unavailable for Finance, Operations, and IT/DevOps
    When the AI literacy training completion rate is requested
    Then the system returns a data availability error
    And no completion rate is calculated
