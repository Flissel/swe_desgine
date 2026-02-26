@smoke @regression
Feature: Customer Data Import Reliability and Performance
  As a QA Engineer
  I want to Verify the customer data import from CSV and Excel meets reliability and performance expectations
  So that Ensures Finance and Operations can ingest customer data consistently without delays or data loss

  Background:
    Given the import service is available and the test environment is reset

  @happy-path @smoke @regression
  Scenario Outline: Successful import for supported formats
    # Valid CSV and XLSX files import successfully with required fields mapped
    Given a valid <file_type> file with 100 customer records and required fields populated
    When the user imports the <file_type> file
    Then the import completes successfully
    And all required fields are mapped with 100% accuracy

    Examples:
      | file_type |
      | CSV |
      | XLSX |

  @regression @performance
  Scenario: Import performance for standard batch
    # 10,000 records import within the 2-minute performance target
    Given a valid CSV file with 10000 customer records in a controlled test environment
    When the user imports the file and measures elapsed time
    Then the import completes within 2 minutes
    And all 10000 records are imported successfully

  @edge-case @regression
  Scenario Outline: Mixed-validity file handles errors and imports valid rows
    # Invalid rows are rejected with clear errors while valid rows still import
    Given a mixed-validity CSV file with <valid_count> valid rows and <invalid_count> invalid rows
    When the user imports the file and reviews the import log
    Then all invalid rows are rejected with clear error messages
    And all valid rows are imported successfully

    Examples:
      | valid_count | invalid_count |
      | 90 | 10 |
      | 9990 | 10 |

  @negative @regression
  Scenario Outline: Unsupported file format is rejected
    # Non-CSV/XLSX files are blocked with a clear error message
    Given an unsupported file format <file_type> containing customer records
    When the user attempts to import the file
    Then the import is rejected
    And a clear error message indicates supported formats are CSV and XLSX

    Examples:
      | file_type |
      | TXT |
      | XML |

  @boundary @regression
  Scenario: Boundary condition for minimum required fields
    # Records with only required fields import successfully
    Given a valid CSV file with records containing only required fields
    When the user imports the file
    Then the import completes successfully
    And required fields are mapped with 100% accuracy
