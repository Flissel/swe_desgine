# Data Dictionary: Vollautonomer Abrechnungsservice Data Dictionary

**Generated:** 2026-02-02T03:08:39.458310

## Summary

- Entities: 12
- Relationships: 10
- Glossary Terms: 7

---

## Entities

### Agent

AI agent performing billing tasks

*Source Requirements:* AUTO-001, AUTO-002, AUTO-003, AUTO-004

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| agent_id | uuid | Yes |  |
| agent_type | string | Yes |  |
| specialization | string | No |  |

### BankAccount

Bank account details for billing and payments

*Source Requirements:* FR-FE-BANK-ACCOUNT-SETUP, REQ-016

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| bank_account_id | uuid | Yes |  |
| bank_name | string | Yes |  |
| account_holder | string | Yes |  |
| iban | string | Yes |  |
| bic | string | No |  |
| account_type | string | No |  |
| currency | string | No |  |

### Company

Billing entity representing an organization

*Source Requirements:* FR-FE-COMPANY-SETTINGS, REQ-017

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| company_id | uuid | Yes |  |
| company_name | string | Yes |  |
| tax_id | string | No |  |
| vat_number | string | No |  |
| address | string | No |  |
| contact_details | string | No |  |

### CompanySettings

Configuration for company billing and payment preferences

*Source Requirements:* FR-FE-COMPANY-SETTINGS, REQ-017

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| settings_id | uuid | Yes |  |
| default_payment_terms | string | No |  |
| multi_entity_support | boolean | No |  |
| international_address_formats | boolean | No |  |
| automated_tax_validation | boolean | No |  |

### CompliancePolicy

Regulatory rules enforced in autonomous billing

*Source Requirements:* STRAT-002, STRAT-004, STRAT-005

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| policy_id | uuid | Yes |  |
| regulation | string | Yes |  |
| active | boolean | Yes |  |

### Customer

Customer records for billing

*Source Requirements:* REQ-018

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| customer_id | uuid | Yes |  |
| name | string | Yes |  |
| email | string | No |  |

### DunningCase

Dunning process for overdue invoices

*Source Requirements:* NFR-AGENT-MAHNAGENT

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| dunning_case_id | uuid | Yes |  |
| invoice_id | uuid | Yes |  |
| dunning_level | integer | Yes |  |
| fees | decimal | No |  |
| status | string | Yes |  |

### Invoice

Billing document generated after validation

*Source Requirements:* REQ-001, AUTO-001

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| invoice_id | uuid | Yes |  |
| status | string | Yes |  |
| generated_at | date | Yes |  |

### PODValidation

Proof-of-delivery validation event triggering billing

*Source Requirements:* REQ-001

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| pod_validation_id | uuid | Yes |  |
| validated | boolean | Yes |  |
| validated_at | date | Yes |  |

### Payment

Incoming payment matched to invoices

*Source Requirements:* NFR-AGENT-ZAHLUNGSRECONCILIATION-AGENT

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| payment_id | uuid | Yes |  |
| invoice_id | uuid | Yes |  |
| payment_date | date | Yes |  |
| amount | decimal | Yes |  |
| status | string | Yes |  |

### UserProfile

User profile settings and permissions

*Source Requirements:* FR-FE-USER-PROFILE-SETTINGS

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| user_id | uuid | Yes |  |
| user_role | string | Yes |  |
| notification_preferences | string | No |  |
| dashboard_customization | string | No |  |
| language_settings | string | No |  |
| security_settings | string | No |  |

### Workflow

Routed billing process executed by agents

*Source Requirements:* AUTO-002, AUTO-004, STRAT-003

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| workflow_id | uuid | Yes |  |
| workflow_type | string | Yes |  |
| complexity | string | No |  |

---

## Relationships

| Relationship | Source | Target | Cardinality | Description |
|--------------|--------|--------|-------------|-------------|
| triggers | PODValidation | Invoice | 1:N |  |
| assigned_to | Workflow | Agent | 1:N |  |
| produces | Workflow | Invoice | 1:N |  |
| governs | CompliancePolicy | Workflow | 1:N |  |
| has | Company | CompanySettings | 1:1 |  |
| owns | Company | BankAccount | 1:N |  |
| manages | Company | Customer | 1:N |  |
| billed_for | Customer | Invoice | 1:N |  |
| settled_by | Invoice | Payment | 1:N |  |
| dunning_for | Invoice | DunningCase | 1:N |  |

---

## Glossary

### BIC

Bank Identifier Code

### Dunning

Process of handling overdue invoices with reminders and fees

### IBAN

International Bank Account Number

### POD

Proof of delivery validation event.

### Reconciliation

Matching incoming payments to invoices

### Workflow Routing

Assignment of billing tasks to suitable agents based on type and complexity.

### Zero-Touch Billing

Fully automated invoice generation without human intervention.

