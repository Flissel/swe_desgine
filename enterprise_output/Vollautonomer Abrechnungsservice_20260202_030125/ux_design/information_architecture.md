# Information Architecture - Vollautonomer Abrechnungsservice

## Site Map

- **Home** (`/`)
  - Content: dashboard, quick-actions, status-overview
  - **Monitoring-Dashboard** (`/monitoring`)
    - Content: real-time-dashboard, kpis, agent-performance, alerts
  - **Rechnungen** (`/invoices`)
    - Content: list, filters, search, status
  - **Workflows** (`/workflows`)
    - Content: workflow-list, routing-rules, event-stream
  - **Einstellungen** (`/settings`)
    - Content: forms, configuration, security
  - **Workflow-Status** (`/monitoring/workflows`)
    - Content: real-time-table, filters, drilldown
  - **Agenten-Performance** (`/monitoring/agents`)
    - Content: charts, leaderboard, logs
  - **Exception-Handling** (`/monitoring/exceptions`)
    - Content: queue, auto-resolve, audit-trail
  - **Automatische Fakturierung** (`/invoices/auto`)
    - Content: rules, status, POD-validation
  - **Rechnungsdetails** (`/invoices/:id`)
    - Content: detail-view, timeline, documents
  - **Rechnungserstellung (Agenten)** (`/invoices/agents`)
    - Content: agent-jobs, automation-status
  - **Workflow-Routing** (`/workflows/routing`)
    - Content: rules-engine, complexity-mapping
  - **Event-Driven Architektur** (`/workflows/events`)
    - Content: event-stream, uptime, latency
  - **Company Settings** (`/settings/company`)
    - Content: legal, tax, address, billing-defaults
  - **Bankkonten** (`/settings/bank-accounts`)
    - Content: form, validation, security-checks
  - **Customer Management** (`/settings/customers`)
    - Content: list, bulk-import, deduplication
  - **Compliance & Regulierung** (`/settings/compliance`)
    - Content: gdpr, fatca, tax-rules, audit-logs
  - **AI Governance & Sicherheit** (`/settings/ai-governance`)
    - Content: transparency, bias-detection, ethics
  - **Kundendetails** (`/settings/customers/:id`)
    - Content: detail-view, validation-status
  - **AI-Entscheidungstransparenz** (`/settings/ai-governance/transparency`)
    - Content: decision-logs, explainability
  - **Cybersecurity** (`/settings/ai-governance/cybersecurity`)
    - Content: zero-trust, threat-detection, alerts

---

## Interaction Patterns

- Infinite Scroll fuer Listen
- Modal Dialoge fuer Formulare
- Toast Notifications fuer Feedback
- Drag & Drop fuer Datei-Upload

---

## Design Principles

1. Mobile First
1. Progressive Disclosure
1. Consistency ueber alle Screens
1. Fehlertoleranz
