@smoke @regression
Feature: User Profile Settings Management
  As a System Administrator
  I want to configure user profile settings for roles, notifications, dashboards, language, and security
  So that to enforce role-based access control, ensure compliant auditing, and maintain reliable session management across the system

  Background:
    Given the system has existing users and role-based access control enabled

  @@smoke @@regression @@happy-path
  Scenario: Update profile settings successfully and reflect changes immediately
    # Valid admin updates all profile settings and changes are persisted and reflected in UI and permissions
    Given a system administrator is authenticated and authorized to manage profile settings
    When the administrator updates user_role, notification_preferences, dashboard_customization, language_settings, and security_settings and saves
    Then the changes are persisted to the user profile
    And the updated settings are immediately reflected in the user's UI and access permissions

  @@regression @@negative
  Scenario: Attempt to modify restricted settings is denied and audited
    # User with limited permissions attempts restricted changes and access is denied with audit trail entry
    Given a user is authenticated with a role that restricts access to security_settings
    When the user attempts to modify restricted profile settings
    Then access is denied
    And the denied attempt is logged in the audit trail with user, timestamp, and setting name

  @@regression @@negative @@boundary
  Scenario: Session expires after inactivity timeout
    # Session is terminated when inactivity exceeds configured timeout
    Given a user session is inactive for the configured timeout duration
    When the user performs any action
    Then the session is terminated
    And the user is prompted to re-authenticate

  @@regression @@happy-path @@outline
  Scenario Outline: Update profile settings with data-driven variations
    # Validate different combinations of profile settings persist and reflect correctly
    Given a system administrator is authenticated and authorized to manage profile settings
    When the administrator sets user_role to "<role>", notification_preferences to "<notifications>", dashboard_customization to "<dashboard>", language_settings to "<language>", and security_settings timeout to <timeout_minutes> minutes and saves
    Then the changes are persisted for the user profile
    And the user's UI language and dashboard reflect "<language>" and "<dashboard>", and permissions reflect "<role>"

    Examples:
      | role | notifications | dashboard | language | timeout_minutes |
      | Analyst | EmailOnly | SalesOverview | en-US | 15 |
      | Manager | EmailAndSMS | Operations | fr-FR | 30 |

  @@regression @@boundary
  Scenario Outline: Boundary timeout at exact configured limit does not expire session
    # Session remains active at the exact timeout boundary and expires only after exceeding it
    Given the security_settings timeout is configured to <timeout_minutes> minutes
    And a user session has been inactive for exactly <timeout_minutes> minutes
    When the user performs any action
    Then the session remains active
    And the action completes successfully without re-authentication prompt

    Examples:
      | timeout_minutes |
      | 15 |
