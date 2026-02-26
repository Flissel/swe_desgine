@smoke @regression
Feature: Frontend Database Design
  As a System Administrator
  I want to design and configure database schemas through the frontend interface
  So that to ensure reliable data structures that support stable integrations and system monitoring

  Background:
    Given I am authenticated with admin privileges and on the database design page

  @happy-path @smoke @regression
  Scenario: Create a new table with valid fields
    # Valid table creation is saved and listed with its fields
    Given I start a new table design
    When I create a table named "Customers" with fields "id" and "email" and save the design
    Then the table is saved successfully
    And the schema list shows the table "Customers" with fields "id" and "email"

  @negative @regression
  Scenario: Prevent duplicate field names in the same table
    # Validation prevents saving a table with duplicate field names
    Given I am designing a table named "Orders"
    When I add a field named "order_id" and add another field named "order_id"
    Then the system prevents the save
    And a validation message indicates a duplicate field name

  @negative @regression
  Scenario: Invalid relationship reference is rejected
    # Relationship creation fails when referencing a non-existent table or field
    Given a schema includes the table "Customers" with field "id"
    When I define a relationship from "Orders.customer_id" to the invalid reference "UnknownTable.id"
    Then the system shows an error
    And the relationship is not saved

  @edge @regression
  Scenario: Warn on navigation with unsaved changes
    # User is warned before leaving with unsaved changes
    Given I have unsaved changes in the schema editor
    When I attempt to navigate away from the database design page
    Then the system warns me about unsaved changes
    And I can cancel navigation and remain on the page

  @boundary @regression
  Scenario Outline: Create table with boundary field name lengths
    # Field name length boundaries are accepted within limits
    Given I start a new table design
    When I create a table named "<table_name>" with a field named "<field_name>" and save the design
    Then the table is saved successfully
    And the schema list shows the table "<table_name>" with field "<field_name>"

    Examples:
      | table_name | field_name |
      | T | f |
      | Table_32_Chars_Name_1234567890 | Field_32_Chars_Name_1234567890 |

  @negative @regression
  Scenario: Reject relationship with invalid field reference
    # Invalid field reference in relationships is not saved
    Given a schema includes the table "Orders" with field "id"
    When I define a relationship from "Orders.customer_id" to the invalid reference "Customers.nonexistent_field"
    Then the system shows an error
    And the relationship is not saved
