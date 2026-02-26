@@smoke @@regression
Feature: Frontend API Endpoints
  As a System Administrator
  I want to configure and access frontend API endpoints
  So that ensure reliable integrations and enable monitoring of endpoint availability

  Background:
    Given the frontend is loaded and ready to initialize API endpoint configuration

  @@smoke @@regression @@happy-path
  Scenario: Load component with valid endpoint configuration
    # Verifies the component connects and displays status when configured with valid endpoints
    Given the frontend is configured with valid API endpoint URLs
    When the user loads the frontend component
    Then the component successfully connects to each endpoint
    And the component displays endpoint status without errors

  @@regression @@negative
  Scenario: Handle unreachable or 5xx endpoint response
    # Verifies error messaging and logging when endpoints fail
    Given an API endpoint is unreachable or returns a 5xx error
    When the frontend attempts to call the endpoint
    Then the component displays a clear error message
    And the failure is logged for monitoring

  @@regression @@negative
  Scenario: Authentication required endpoint returns 401 or 403
    # Verifies the component prompts for valid authentication on auth failure
    Given an API endpoint requires authentication
    When the frontend sends a request with missing or invalid credentials
    Then the component receives a 401 or 403 response
    And the component prompts for valid authentication

  @@regression @@edge
  Scenario: Endpoint configuration with trailing slashes and query parameters
    # Validates handling of boundary URL formats without errors
    Given the frontend is configured with endpoint URLs that include trailing slashes or query parameters
    When the user loads the frontend component
    Then the component normalizes the URLs and connects successfully
    And the component displays endpoint status without errors

  @@regression @@happy-path
  Scenario Outline: Endpoint status retrieval for multiple endpoints
    # Data-driven verification of status display for multiple valid endpoints
    Given the frontend is configured with a list of API endpoints
    When the user loads the frontend component
    Then the component connects to the endpoint <endpoint_name>
    And the status for <endpoint_name> is displayed as <expected_status>

    Examples:
      | endpoint_name | expected_status |
      | health-check | Available |
      | metrics | Available |

  @@regression @@negative
  Scenario Outline: Authentication failure scenarios by credential state
    # Data-driven verification for missing and invalid credentials responses
    Given an API endpoint requires authentication
    When the frontend sends a request with <credential_state> credentials
    Then the component receives a <status_code> response
    And the component prompts for valid authentication

    Examples:
      | credential_state | status_code |
      | missing | 401 |
      | invalid | 403 |
