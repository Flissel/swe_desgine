@smoke @regression
Feature: US-005 Customer Management
  As a Finance Team (Accountant)
  I want to manage customer records including billing/shipping addresses, tax IDs, payment terms, credit limits, and preferred payment methods
  So that to ensure accurate invoicing, timely payments, and a complete audit trail

  Background:
    Given the accountant is logged in and on the Customer Management page

  @happy-path @smoke
  Scenario: Create a new customer with all required fields
    # Valid customer record is saved and listed
    Given the accountant has entered all required customer details including billing and shipping addresses
    When the accountant saves the customer record
    Then the customer is saved successfully
    And the customer appears in the customer list with all entered details

  @regression
  Scenario Outline: Bulk import flags duplicate by tax ID or customer name
    # Duplicate detection provides merge, update, or skip options
    Given a bulk import file contains a customer with <duplicate_type> matching an existing record
    When the accountant runs the bulk import
    Then the system flags the duplicate record
    And the system provides options to merge, update, or skip the record

    Examples:
      | duplicate_type |
      | tax_id |
      | customer_name |

  @negative @regression
  Scenario Outline: Prevent saving when required field is missing
    # Missing required field triggers validation error
    Given the accountant is creating a customer record with missing <required_field>
    When the accountant attempts to save the record
    Then the system prevents saving the record
    And a validation error indicates the missing field <required_field>

    Examples:
      | required_field |
      | customer_name |
      | billing_address |
      | tax_id |

  @negative @regression
  Scenario Outline: Prevent saving when tax ID format is invalid
    # Invalid tax ID format is rejected
    Given the accountant enters a tax ID with format <tax_id_format>
    When the accountant attempts to save the record
    Then the system prevents saving the record
    And a validation error indicates the tax ID format is invalid

    Examples:
      | tax_id_format |
      | too_short |
      | contains_special_characters |
      | missing_required_prefix |

  @edge @regression
  Scenario Outline: Save customer with boundary credit limit values
    # Credit limit boundaries are accepted when valid
    Given the accountant enters a credit limit of <credit_limit> with all other required fields valid
    When the accountant saves the customer record
    Then the customer is saved successfully
    And the saved credit limit equals <credit_limit>

    Examples:
      | credit_limit |
      | 0 |
      | 1000000 |
