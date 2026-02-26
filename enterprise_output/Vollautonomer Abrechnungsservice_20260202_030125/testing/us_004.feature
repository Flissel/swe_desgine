@@smoke @@regression
Feature: Company Settings Management
  As a Finance Team (Accountant)
  I want to configure company settings including legal, tax, address, and billing defaults
  So that ensure accurate invoicing, compliant tax handling, and a reliable audit trail for payments

  Background:
    Given the accountant is authenticated and on the Company Settings page

  @@smoke @@regression @@happy-path
  Scenario: Save valid company settings for selected entity
    # Happy path to persist and display valid company settings
    Given a company entity "Acme Ltd" is selected with existing valid settings
    When the accountant updates company_name, tax_id, vat_number, address, contact_details, and default_payment_terms with valid values
    And saves the Company Settings
    Then the updated settings are persisted for "Acme Ltd"
    And the saved values are displayed correctly on the page

  @@regression @@edge
  Scenario: Switch entity and update settings only for the active entity
    # Edge case to ensure entity isolation when multiple entities exist
    Given multiple company entities exist: "Acme Ltd" and "Beta LLC"
    And "Beta LLC" is selected as the active entity
    When the accountant updates the settings for "Beta LLC" and saves
    Then only "Beta LLC" settings are updated
    And "Acme Ltd" settings remain unchanged

  @@regression @@negative
  Scenario: Block save when tax_id or vat_number is invalid
    # Error scenario to validate automated tax validation and error messaging
    Given a company entity "Acme Ltd" is selected
    When the accountant enters invalid tax_id or vat_number
    And attempts to save the Company Settings
    Then the save is blocked by automated tax validation
    And a clear validation error message is displayed

  @@regression @@boundary
  Scenario Outline: Validate boundary conditions for payment terms and address length
    # Boundary scenario for input limits and minimum values
    Given a company entity "Acme Ltd" is selected
    When the accountant sets default_payment_terms to "<payment_terms>" and address line to "<address_line>"
    And saves the Company Settings
    Then the system accepts values within allowed limits and persists them
    And the displayed values match the saved inputs

    Examples:
      | payment_terms | address_line |
      | 0 | A |
      | 365 | 1234567890123456789012345678901234567890 |

  @@regression @@negative @@boundary
  Scenario Outline: Reject payment terms outside allowed range
    # Negative boundary scenario for invalid payment terms
    Given a company entity "Acme Ltd" is selected
    When the accountant sets default_payment_terms to "<payment_terms>"
    And attempts to save the Company Settings
    Then the save is rejected with a clear validation message for payment terms

    Examples:
      | payment_terms |
      | -1 |
      | 366 |
