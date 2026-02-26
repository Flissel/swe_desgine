@@smoke @@regression
Feature: Frontend: Bank Account Setup
  As a Finance Team (Accountant)
  I want to enter and manage bank account details via the web interface with validation and security controls
  So that to ensure accurate invoicing and timely payments with a reliable audit trail

  Background:
    Given the accountant is authenticated and on the Bank Account Setup page

  @@smoke @@happy-path @@regression
  Scenario: Save a new bank account successfully with encryption and tokenization
    # Valid bank account details are saved with security controls applied
    Given no existing bank account with the same IBAN exists
    When the accountant submits valid bank_name, account_holder, iban, bic, account_type, and currency
    Then the system saves the account successfully
    And the system applies end-to-end encryption and tokenization to the stored account data

  @@negative @@regression
  Scenario Outline: Validate invalid IBAN formats
    # Invalid IBAN formats are blocked with a clear validation error
    Given the accountant has entered all required fields with a invalid IBAN format
    When the accountant attempts to submit the form
    Then the system blocks submission
    And the system displays a validation error message for the IBAN field

    Examples:
      | iban | bic | bank_name | account_holder | account_type | currency |
      | DE12 | DEUTDEFF | Demo Bank | Jane Doe | Checking | EUR |
      | INVALIDIBAN123 | DEUTDEFF | Demo Bank | Jane Doe | Checking | EUR |

  @@negative @@regression
  Scenario Outline: Validate non-existent BIC codes
    # Non-existent BIC values are blocked with a clear validation error
    Given the accountant has entered all required fields with a non-existent BIC
    When the accountant attempts to submit the form
    Then the system blocks submission
    And the system displays a validation error message for the BIC field

    Examples:
      | iban | bic | bank_name | account_holder | account_type | currency |
      | DE89370400440532013000 | XXXXXX00 | Demo Bank | Jane Doe | Checking | EUR |

  @@negative @@regression
  Scenario Outline: Prevent duplicate IBANs
    # Duplicate IBAN submissions are blocked and the user is informed
    Given an existing bank account with IBAN <iban> is already stored
    When the accountant submits a new account with the same IBAN <iban>
    Then the system prevents the duplicate from being saved
    And the system informs the user that the account already exists

    Examples:
      | iban |
      | DE89370400440532013000 |

  @@edge @@regression
  Scenario Outline: Boundary validation for IBAN length
    # IBAN length boundaries are enforced
    Given the accountant enters an IBAN with length <length>
    When the accountant submits the form with all other fields valid
    Then the system returns <result>
    And the system displays <message> for the IBAN field

    Examples:
      | length | result | message |
      | 15 | a validation error | an IBAN length validation error |
      | 34 | a successful save | no validation error |
      | 35 | a validation error | an IBAN length validation error |
