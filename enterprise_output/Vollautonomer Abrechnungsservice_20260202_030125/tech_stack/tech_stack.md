# Technology Stack - Vollautonomer Abrechnungsservice

## Overview

| Category | Technology |
|----------|------------|
| Architecture | Microservices |
| Deployment | Cloud-native |

---

## Frontend

| Component | Technology |
|-----------|------------|
| Framework | **React** |
| Languages | TypeScript, JavaScript |
| UI Library | Material-UI |
| State Management | Redux Toolkit |

**Rationale:** React mit TypeScript bietet hohe Entwicklerproduktivität, große Community, ausgereifte Komponentenökosysteme und eignet sich für komplexe Dashboards sowie sichere Formulare (Bankkonto/Company Settings).

---

## Backend

| Component | Technology |
|-----------|------------|
| Language | **Python** |
| Framework | **FastAPI** |
| API Style | REST |

**Rationale:** FastAPI liefert hohe Performance, async Support und exzellente API-Dokumentation; ideal für AI-Agenten-Orchestrierung, Event-Driven Workflows und Integration von LLM-Services.

---

## Data Layer

| Component | Technology |
|-----------|------------|
| Primary Database | **PostgreSQL** |
| Cache | Redis |
| Search Engine | Elasticsearch |

**Rationale:** PostgreSQL bietet starke ACID-Garantien für Finanzdaten, Unterstützung für komplexe Abfragen, JSONB für flexible Metadaten sowie Skalierung via Read-Replicas.

---

## Infrastructure

| Component | Technology |
|-----------|------------|
| Cloud Provider | **AWS** |
| Container Runtime | Docker |
| Orchestration | Kubernetes |
| CI/CD | GitHub Actions |

---

## Integration

| Component | Technology |
|-----------|------------|
| Message Queue | Kafka |
| API Gateway | AWS API Gateway |

---

## Alternatives Considered

### Frontend Framework
- Vue.js
- Angular

### Backend Framework
- Spring Boot
- Node.js (NestJS)

---

## Architecture Diagram

See `architecture_diagram.mmd` for the C4 Context diagram.
