# Vollautonomer Abrechnungsservice API - API Documentation

**Version:** 1.0.0
**Generated:** 2026-02-02T03:08:39.452417

## Endpoints

### AuditTrail

#### `GET` /api/v1/users/{userId}/audit-trail

**List user audit trail**

Returns audit trail entries related to user profile settings changes with pagination.

*Requirement:* FR-FE-USER-PROFILE-SETTINGS

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| userId | path | string | True | User ID |
| page | query | integer | False | Page number |
| pageSize | query | integer | False | Number of items per page |

**Responses:**

- `200`: Success
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Not Found

---

### BankAccounts

#### `POST` /api/v1/bank-accounts

**Create bank account**

Securely create a new bank account with end-to-end encryption and tokenization; performs IBAN format validation, BIC existence check, and duplicate prevention.

*Requirement:* FR-FE-BANK-ACCOUNT-SETUP

**Request Body:** `CreateBankAccountRequest`

**Responses:**

- `201`: Created
- `400`: Bad Request - Validation failed
- `401`: Unauthorized
- `409`: Conflict - Duplicate account
- `422`: Unprocessable Entity - IBAN/BIC validation failed

---

#### `GET` /api/v1/bank-accounts

**List bank accounts**

Retrieve a paginated list of bank accounts.

*Requirement:* FR-FE-BANK-ACCOUNT-SETUP

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| page | query | integer | False | Page number (default 1) |
| pageSize | query | integer | False | Number of items per page (default 20) |

**Responses:**

- `200`: Success
- `401`: Unauthorized

---

#### `GET` /api/v1/bank-accounts/{bankAccountId}

**Get bank account**

Retrieve details of a specific bank account.

*Requirement:* FR-FE-BANK-ACCOUNT-SETUP

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| bankAccountId | path | string | True | Bank account ID |

**Responses:**

- `200`: Success
- `401`: Unauthorized
- `404`: Not Found

---

#### `PUT` /api/v1/bank-accounts/{bankAccountId}

**Update bank account**

Update an existing bank account with validation checks; requires end-to-end encryption and tokenization.

*Requirement:* FR-FE-BANK-ACCOUNT-SETUP

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| bankAccountId | path | string | True | Bank account ID |

**Request Body:** `UpdateBankAccountRequest`

**Responses:**

- `200`: Success
- `400`: Bad Request - Validation failed
- `401`: Unauthorized
- `404`: Not Found
- `409`: Conflict - Duplicate account
- `422`: Unprocessable Entity - IBAN/BIC validation failed

---

#### `DELETE` /api/v1/bank-accounts/{bankAccountId}

**Delete bank account**

Delete a bank account.

*Requirement:* FR-FE-BANK-ACCOUNT-SETUP

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| bankAccountId | path | string | True | Bank account ID |

**Responses:**

- `204`: No Content
- `401`: Unauthorized
- `404`: Not Found

---

### Bulk

#### `POST` /api/v1/customers/bulk-import

**Bulk import customers**

Import multiple customer records in a single request.

*Requirement:* FR-FE-CUSTOMER-MANAGEMENT

**Request Body:** `BulkImportCustomersRequest`

**Responses:**

- `202`: Accepted
- `400`: Bad Request
- `401`: Unauthorized
- `409`: Conflict
- `422`: Unprocessable Entity

---

#### `GET` /api/v1/customers/bulk-export

**Bulk export customers**

Export customer records, optionally filtered and paginated.

*Requirement:* FR-FE-CUSTOMER-MANAGEMENT

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| format | query | string | False | Export format, e.g. csv or json |
| page | query | integer | False | Page number |
| pageSize | query | integer | False | Number of items per page |
| search | query | string | False | Search by customer name or tax ID |

**Responses:**

- `200`: Success
- `400`: Bad Request
- `401`: Unauthorized

---

### Companies

#### `GET` /api/v1/companies

**List companies**

Retrieve a paginated list of companies to support multi-entity configuration.

*Requirement:* FR-FE-COMPANY-SETTINGS

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| page | query | integer | False | Page number for pagination |
| pageSize | query | integer | False | Number of items per page |

**Responses:**

- `200`: Success
- `400`: Bad Request
- `401`: Unauthorized

---

#### `POST` /api/v1/companies

**Create company**

Create a company with core settings and billing configuration.

*Requirement:* FR-FE-COMPANY-SETTINGS

**Request Body:** `CreateCompanyRequest`

**Responses:**

- `201`: Created
- `400`: Bad Request
- `401`: Unauthorized
- `422`: Unprocessable Entity

---

#### `GET` /api/v1/companies/{companyId}

**Get company settings**

Retrieve company settings including billing configuration.

*Requirement:* FR-FE-COMPANY-SETTINGS

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| companyId | path | string | True | Company ID |

**Responses:**

- `200`: Success
- `401`: Unauthorized
- `404`: Not Found

---

#### `PUT` /api/v1/companies/{companyId}

**Update company settings**

Update company settings including tax and billing fields.

*Requirement:* FR-FE-COMPANY-SETTINGS

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| companyId | path | string | True | Company ID |

**Request Body:** `UpdateCompanyRequest`

**Responses:**

- `200`: Success
- `400`: Bad Request
- `401`: Unauthorized
- `404`: Not Found
- `422`: Unprocessable Entity

---

### Customers

#### `POST` /api/v1/customers

**Create customer**

Create a new customer record for automated billing.

*Requirement:* FR-FE-CUSTOMER-MANAGEMENT

**Request Body:** `CreateCustomerRequest`

**Responses:**

- `201`: Created
- `400`: Bad Request
- `401`: Unauthorized
- `409`: Conflict
- `422`: Unprocessable Entity

---

#### `GET` /api/v1/customers

**List customers**

Retrieve a paginated list of customers with optional search and filtering.

*Requirement:* FR-FE-CUSTOMER-MANAGEMENT

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| page | query | integer | False | Page number |
| pageSize | query | integer | False | Number of items per page |
| search | query | string | False | Search by customer name or tax ID |
| sort | query | string | False | Sort fields, e.g. customer_name,-created_at |

**Responses:**

- `200`: Success
- `400`: Bad Request
- `401`: Unauthorized

---

#### `GET` /api/v1/customers/{id}

**Get customer**

Retrieve a single customer by ID.

*Requirement:* FR-FE-CUSTOMER-MANAGEMENT

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| id | path | string | True | Customer ID |

**Responses:**

- `200`: Success
- `401`: Unauthorized
- `404`: Not Found

---

#### `PUT` /api/v1/customers/{id}

**Update customer**

Update all fields of a customer record.

*Requirement:* FR-FE-CUSTOMER-MANAGEMENT

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| id | path | string | True | Customer ID |

**Request Body:** `UpdateCustomerRequest`

**Responses:**

- `200`: Success
- `400`: Bad Request
- `401`: Unauthorized
- `404`: Not Found
- `409`: Conflict
- `422`: Unprocessable Entity

---

#### `DELETE` /api/v1/customers/{id}

**Delete customer**

Delete a customer record.

*Requirement:* FR-FE-CUSTOMER-MANAGEMENT

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| id | path | string | True | Customer ID |

**Responses:**

- `204`: No Content
- `401`: Unauthorized
- `404`: Not Found
- `409`: Conflict

---

#### `POST` /api/v1/customers/bulk-import

**Bulk import customers**

Import multiple customer records in a single request.

*Requirement:* FR-FE-CUSTOMER-MANAGEMENT

**Request Body:** `BulkImportCustomersRequest`

**Responses:**

- `202`: Accepted
- `400`: Bad Request
- `401`: Unauthorized
- `409`: Conflict
- `422`: Unprocessable Entity

---

#### `GET` /api/v1/customers/bulk-export

**Bulk export customers**

Export customer records, optionally filtered and paginated.

*Requirement:* FR-FE-CUSTOMER-MANAGEMENT

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| format | query | string | False | Export format, e.g. csv or json |
| page | query | integer | False | Page number |
| pageSize | query | integer | False | Number of items per page |
| search | query | string | False | Search by customer name or tax ID |

**Responses:**

- `200`: Success
- `400`: Bad Request
- `401`: Unauthorized

---

#### `POST` /api/v1/customers/duplicates

**Detect duplicate customers**

Detect potential duplicate customers based on matching rules.

*Requirement:* FR-FE-CUSTOMER-MANAGEMENT

**Request Body:** `DetectDuplicatesRequest`

**Responses:**

- `200`: Success
- `400`: Bad Request
- `401`: Unauthorized

---

### DataQuality

#### `POST` /api/v1/customers/duplicates

**Detect duplicate customers**

Detect potential duplicate customers based on matching rules.

*Requirement:* FR-FE-CUSTOMER-MANAGEMENT

**Request Body:** `DetectDuplicatesRequest`

**Responses:**

- `200`: Success
- `400`: Bad Request
- `401`: Unauthorized

---

### Endpoints

#### `GET` /api/v1/endpoints

**List API endpoints**

Retrieve a paginated list of available API endpoints for frontend discovery.

*Requirement:* FR-FE-API-ENDPOINTS

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| page | query | integer | False | Page number (1-based) |
| pageSize | query | integer | False | Number of items per page |
| search | query | string | False | Search term to filter endpoints by path or summary |

**Responses:**

- `200`: Success
- `400`: Bad Request
- `401`: Unauthorized
- `500`: Internal Server Error

---

#### `GET` /api/v1/endpoints/{id}

**Get API endpoint details**

Retrieve detailed metadata for a specific API endpoint.

*Requirement:* FR-FE-API-ENDPOINTS

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| id | path | string | True | Endpoint ID |

**Responses:**

- `200`: Success
- `400`: Bad Request
- `401`: Unauthorized
- `404`: Not Found
- `500`: Internal Server Error

---

### FrontendComponents

#### `GET` /api/v1/frontend-components

**List frontend components**

Retrieve a paginated list of frontend components.

*Requirement:* FR-FE-FRONTEND-COMPONENTS

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| page | query | integer | False | Page number (starting from 1) |
| pageSize | query | integer | False | Number of items per page |

**Responses:**

- `200`: Success
- `400`: Bad Request
- `401`: Unauthorized

---

#### `POST` /api/v1/frontend-components

**Create a frontend component**

Create a new frontend component.

*Requirement:* FR-FE-FRONTEND-COMPONENTS

**Request Body:** `CreateFrontendComponentRequest`

**Responses:**

- `201`: Created
- `400`: Bad Request
- `401`: Unauthorized
- `409`: Conflict

---

#### `GET` /api/v1/frontend-components/{id}

**Get a frontend component**

Retrieve a frontend component by ID.

*Requirement:* FR-FE-FRONTEND-COMPONENTS

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| id | path | string | True | Component ID |

**Responses:**

- `200`: Success
- `400`: Bad Request
- `401`: Unauthorized
- `404`: Not Found

---

#### `PUT` /api/v1/frontend-components/{id}

**Update a frontend component**

Update an existing frontend component by ID.

*Requirement:* FR-FE-FRONTEND-COMPONENTS

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| id | path | string | True | Component ID |

**Request Body:** `UpdateFrontendComponentRequest`

**Responses:**

- `200`: Success
- `400`: Bad Request
- `401`: Unauthorized
- `404`: Not Found

---

#### `DELETE` /api/v1/frontend-components/{id}

**Delete a frontend component**

Delete a frontend component by ID.

*Requirement:* FR-FE-FRONTEND-COMPONENTS

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| id | path | string | True | Component ID |

**Responses:**

- `204`: No Content
- `400`: Bad Request
- `401`: Unauthorized
- `404`: Not Found

---

### Invoices

#### `POST` /api/v1/pods/{podId}/invoices

**Generate invoice after POD validation**

Creates an invoice automatically based on a validated Proof of Delivery (POD).

*Requirement:* REQ-001

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| podId | path | string | True | Validated POD ID |

**Request Body:** `GenerateInvoiceRequest`

**Responses:**

- `201`: Invoice Created
- `400`: Bad Request
- `401`: Unauthorized
- `404`: POD Not Found
- `409`: Invoice Already Exists
- `500`: Internal Server Error

---

#### `GET` /api/v1/invoices/{invoiceId}

**Get invoice by ID**

Retrieves details of a generated invoice.

*Requirement:* REQ-001

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| invoiceId | path | string | True | Invoice ID |

**Responses:**

- `200`: Success
- `401`: Unauthorized
- `404`: Invoice Not Found
- `500`: Internal Server Error

---

### PODs

#### `POST` /api/v1/pods/{podId}/invoices

**Generate invoice after POD validation**

Creates an invoice automatically based on a validated Proof of Delivery (POD).

*Requirement:* REQ-001

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| podId | path | string | True | Validated POD ID |

**Request Body:** `GenerateInvoiceRequest`

**Responses:**

- `201`: Invoice Created
- `400`: Bad Request
- `401`: Unauthorized
- `404`: POD Not Found
- `409`: Invoice Already Exists
- `500`: Internal Server Error

---

### SessionManagement

#### `GET` /api/v1/users/{userId}/sessions

**List active user sessions**

Returns active sessions for a user to support session management.

*Requirement:* FR-FE-USER-PROFILE-SETTINGS

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| userId | path | string | True | User ID |
| page | query | integer | False | Page number |
| pageSize | query | integer | False | Number of items per page |

**Responses:**

- `200`: Success
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Not Found

---

#### `DELETE` /api/v1/users/{userId}/sessions/{sessionId}

**Terminate a user session**

Revokes a specific session for a user.

*Requirement:* FR-FE-USER-PROFILE-SETTINGS

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| userId | path | string | True | User ID |
| sessionId | path | string | True | Session ID |

**Responses:**

- `204`: No Content
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Not Found

---

### TaxValidation

#### `POST` /api/v1/companies/{companyId}/tax-validations

**Validate tax identifiers**

Trigger automated validation for tax ID and VAT number.

*Requirement:* FR-FE-COMPANY-SETTINGS

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| companyId | path | string | True | Company ID |

**Request Body:** `TaxValidationRequest`

**Responses:**

- `200`: Success
- `400`: Bad Request
- `401`: Unauthorized
- `404`: Not Found
- `422`: Unprocessable Entity

---

### UserProfileSettings

#### `GET` /api/v1/users/{userId}/profile-settings

**Get user profile settings**

Retrieves UI personalization, permissions, and security settings for a user.

*Requirement:* FR-FE-USER-PROFILE-SETTINGS

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| userId | path | string | True | User ID |

**Responses:**

- `200`: Success
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Not Found

---

#### `PUT` /api/v1/users/{userId}/profile-settings

**Update user profile settings**

Updates UI personalization, permissions, and security settings for a user. Enforces role-based access control and writes to audit trail.

*Requirement:* FR-FE-USER-PROFILE-SETTINGS

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| userId | path | string | True | User ID |

**Request Body:** `UpdateUserProfileSettingsRequest`

**Responses:**

- `200`: Success
- `400`: Bad Request
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Not Found

---

## Schemas

### AuditTrailListResponse

| Property | Type | Description |
|----------|------|-------------|
| items | array | Audit trail entries |
| page | integer | Current page |
| pageSize | integer | Items per page |
| totalItems | integer | Total number of items |

### BankAccountListResponse

| Property | Type | Description |
|----------|------|-------------|
| items | array | List of bank accounts |
| page | integer | Current page |
| pageSize | integer | Page size |
| totalItems | integer | Total number of items |
| totalPages | integer | Total number of pages |

### BankAccountResponse

| Property | Type | Description |
|----------|------|-------------|
| id | string | Bank account ID |
| bankName | string | Name of the bank |
| accountHolder | string | Name of the account holder |
| ibanMasked | string | Masked IBAN |
| bic | string | Bank Identifier Code |
| accountType | string | Type of account |
| currency | string | Account currency (ISO 4217) |
| updatedAt | string | Update timestamp |

### BulkExportCustomersResponse

| Property | Type | Description |
|----------|------|-------------|
| items | array | Exported customer records |
| page | integer | Current page number |
| pageSize | integer | Items per page |
| total | integer | Total number of customers |

### BulkImportCustomersRequest

| Property | Type | Description |
|----------|------|-------------|
| items | array | Array of customer records |
| mode | string | Import mode: create or upsert |

### BulkImportCustomersResponse

| Property | Type | Description |
|----------|------|-------------|
| created | integer | Number of created records |
| updated | integer | Number of updated records |
| errors | array | Array of import errors |

### CompanyListResponse

| Property | Type | Description |
|----------|------|-------------|
| items | array | List of companies |
| page | integer | Current page |
| pageSize | integer | Page size |
| totalItems | integer | Total number of companies |

### CompanyResponse

| Property | Type | Description |
|----------|------|-------------|
| id | string | Company ID |
| companyName | string | Company name |
| taxId | string | Tax ID |
| vatNumber | string | VAT number |
| address | object | International address format |
| contactDetails | object | Company contact details |
| defaultPaymentTerms | string | Default payment terms |

### CreateBankAccountRequest

| Property | Type | Description |
|----------|------|-------------|
| bankName | string | Name of the bank |
| accountHolder | string | Name of the account holder |
| iban | string | International Bank Account Number |
| bic | string | Bank Identifier Code |
| accountType | string | Type of account (e.g., checking, savings) |
| currency | string | Account currency (ISO 4217) |

### CreateCompanyRequest

| Property | Type | Description |
|----------|------|-------------|
| companyName | string | Company name |
| taxId | string | Tax ID |
| vatNumber | string | VAT number |
| address | object | International address format |
| contactDetails | object | Company contact details |
| defaultPaymentTerms | string | Default payment terms (e.g., NET_30) |

### CreateCustomerRequest

| Property | Type | Description |
|----------|------|-------------|
| customer_name | string | Customer name |
| billing_address | string | Billing address |
| shipping_address | string | Shipping address |
| tax_id | string | Tax identification number |
| payment_terms | string | Payment terms |
| credit_limit | number | Credit limit |
| preferred_payment_method | string | Preferred payment method |

### CreateFrontendComponentRequest

| Property | Type | Description |
|----------|------|-------------|
| name | string | Component name |
| type | string | Component type |
| description | string | Component description |
| config | object | Component configuration |

### CustomerListResponse

| Property | Type | Description |
|----------|------|-------------|
| items | array | List of customers |
| page | integer | Current page number |
| pageSize | integer | Items per page |
| total | integer | Total number of customers |

### CustomerResponse

| Property | Type | Description |
|----------|------|-------------|
| id | string | Customer ID |
| customer_name | string | Customer name |
| billing_address | string | Billing address |
| shipping_address | string | Shipping address |
| tax_id | string | Tax identification number |
| payment_terms | string | Payment terms |
| credit_limit | number | Credit limit |
| preferred_payment_method | string | Preferred payment method |

### DetectDuplicatesRequest

| Property | Type | Description |
|----------|------|-------------|
| match_fields | array | Fields to match for duplicates |
| threshold | number | Similarity threshold |

### DetectDuplicatesResponse

| Property | Type | Description |
|----------|------|-------------|
| pairs | array | Array of duplicate candidate pairs |

### EndpointListResponse

| Property | Type | Description |
|----------|------|-------------|
| items | array | List of API endpoints |
| page | integer | Current page number |
| pageSize | integer | Items per page |
| totalItems | integer | Total number of endpoints |
| totalPages | integer | Total pages |

### EndpointResponse

| Property | Type | Description |
|----------|------|-------------|
| id | string | Endpoint ID |
| path | string | Endpoint path |
| method | string | HTTP method |
| summary | string | Short description |
| description | string | Detailed description |
| parameters | array | Endpoint parameters |

### FrontendComponentListResponse

| Property | Type | Description |
|----------|------|-------------|
| items | array | List of frontend components |
| page | integer | Current page |
| pageSize | integer | Items per page |
| totalItems | integer | Total number of items |
| totalPages | integer | Total number of pages |

### FrontendComponentResponse

| Property | Type | Description |
|----------|------|-------------|
| id | string | Component ID |
| name | string | Component name |
| type | string | Component type |
| description | string | Component description |
| config | object | Component configuration |

### GenerateInvoiceRequest

| Property | Type | Description |
|----------|------|-------------|
| validationTimestamp | string | ISO 8601 timestamp of POD validation |
| currency | string | Invoice currency code |

### InvoiceResponse

| Property | Type | Description |
|----------|------|-------------|
| invoiceId | string | Invoice ID |
| podId | string | Associated POD ID |
| status | string | Invoice status |
| createdAt | string | Invoice creation timestamp |

### SessionListResponse

| Property | Type | Description |
|----------|------|-------------|
| items | array | Active sessions |
| page | integer | Current page |
| pageSize | integer | Items per page |
| totalItems | integer | Total number of items |

### TaxValidationRequest

| Property | Type | Description |
|----------|------|-------------|
| taxId | string | Tax ID to validate |
| vatNumber | string | VAT number to validate |
| countryCode | string | ISO 3166-1 alpha-2 country code |

### TaxValidationResponse

| Property | Type | Description |
|----------|------|-------------|
| taxIdValid | boolean | Tax ID validation result |
| vatNumberValid | boolean | VAT number validation result |
| validationProvider | string | Validation provider name |
| validatedAt | string | ISO timestamp of validation |

### UpdateBankAccountRequest

| Property | Type | Description |
|----------|------|-------------|
| bankName | string | Name of the bank |
| accountHolder | string | Name of the account holder |
| iban | string | International Bank Account Number |
| bic | string | Bank Identifier Code |
| accountType | string | Type of account (e.g., checking, savings) |
| currency | string | Account currency (ISO 4217) |

### UpdateCompanyRequest

| Property | Type | Description |
|----------|------|-------------|
| companyName | string | Company name |
| taxId | string | Tax ID |
| vatNumber | string | VAT number |
| address | object | International address format |
| contactDetails | object | Company contact details |
| defaultPaymentTerms | string | Default payment terms (e.g., NET_30) |

### UpdateCustomerRequest

| Property | Type | Description |
|----------|------|-------------|
| customer_name | string | Customer name |
| billing_address | string | Billing address |
| shipping_address | string | Shipping address |
| tax_id | string | Tax identification number |
| payment_terms | string | Payment terms |
| credit_limit | number | Credit limit |
| preferred_payment_method | string | Preferred payment method |

### UpdateFrontendComponentRequest

| Property | Type | Description |
|----------|------|-------------|
| name | string | Component name |
| type | string | Component type |
| description | string | Component description |
| config | object | Component configuration |

### UpdateUserProfileSettingsRequest

| Property | Type | Description |
|----------|------|-------------|
| userRole | string | Assigned user role |
| notificationPreferences | object | Notification preferences |
| dashboardCustomization | object | Dashboard customization settings |
| languageSettings | object | Language and locale settings |
| securitySettings | object | Security settings including MFA and password policy |

### UserProfileSettingsResponse

| Property | Type | Description |
|----------|------|-------------|
| userId | string | User ID |
| userRole | string | Assigned user role |
| notificationPreferences | object | Notification preferences |
| dashboardCustomization | object | Dashboard customization settings |
| languageSettings | object | Language and locale settings |
| securitySettings | object | Security settings including MFA and password policy |

