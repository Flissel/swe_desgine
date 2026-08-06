# Evaluation & TODO — RE-Wizard-Flow (2 Systeme)

Stand 2026-08-02, nach Live-E2E-Beweis (Mining → Validate → Improve, echte LLM-Scores).
Die Requirements-Qualitätssicherung besteht aus **zwei getrennten Prozessen**, die
zusammenspielen. Dieses Dokument hält fest, was in jedes System rein- und rausgeht,
und was noch offen ist.

---

## System 1 — RE-Dashboard + Wizard (`:8080`)

**Start:** `cd spaces/shuttles/swe_desgine && python start_dashboard.py`
**UI:** `http://localhost:8080/wizard` · **Code:** `requirements_engineer/dashboard/server.py`

### Input

| Endpoint | Rein | Format |
|---|---|---|
| `POST /api/wizard/extract` | Roh-Dokumente (PDF, DOCX, MD, TXT) | multipart, Feld `documents` |
| `POST /api/wizard/validate-batch` | Requirements-Liste + `threshold` (Default 0.7) | JSON `{requirements: [{id, title, category}], threshold}` |
| `POST /api/wizard/decide` | validierte Requirements | JSON |
| `POST /api/wizard/improve` | Requirements (auch ungeprüfte) | JSON `{requirements: [...]}` |
| `POST /api/wizard/split` | zu komplexe Requirements | JSON |
| `POST /api/wizard/clarify` / `answer-clarification` | Requirements + User-Antworten | JSON |

### Output

| Schritt | Raus |
|---|---|
| extract | atomare Requirements `{id: REQ-<hash>-NNN, title, description, category, priority}` — ChunkMiner (gpt-4o-mini), inkl. Sub-Splits (`-a`, `-b`) |
| validate-batch | pro Requirement `{req_id, score 0..1, verdict pass/fail, evaluation[]}` — delegiert an System 2 |
| improve | Requirement mit `_rewritten: true/false`; bei Rewrite: messbare Formulierung + Gherkin-Akzeptanzkriterien. Gute Requirements bleiben unangetastet |
| Pipeline-Abschluss | Artefakte nach `enterprise_output/{name}_{ts}/` **und** Supabase `swe_design_runs`/`swe_design_artifacts` (Proxmox, seit 2026-08-01 live) |

### Abhängigkeiten
- `external/arch_team`-Submodule (seit 2026-08-01 initialisiert, Pin `70d9856`)
- System 2 auf `:8087` — ohne das liefert validate-batch nur score 0.0/fail
- `.env` (gitignored): OpenAI-Redirect (`OPENROUTER_BASE_URL=https://api.openai.com/v1`)
- Python-Deps über requirements.txt hinaus: `omegaconf`, `funcy` (+ INTEGRATION.md-Liste)

---

## System 2 — arch_team Evaluation-Backend (`:8087`)

**Start:** `cd external/arch_team && python -m backend.main` (NUR als Modul!)
**Code:** `backend/` (FastAPI) · **Check:** `GET /api/runtime-config` → `llm.model` muss `gpt-4o-mini` sein

### Input

| Endpoint | Rein | Format |
|---|---|---|
| `POST /api/v2/evaluate/single` | 1 Requirement-Text | `{text, context?, criteria_keys?, threshold?}` |
| `POST /api/v2/evaluate/batch` | mehrere Texte | analog |
| SQLite `criterion`-Tabelle | 10 IEEE-29148-Kriterien (clarity, testability, measurability, atomic, design_independent, …) | Seed: `python -c "from backend.core.db import init_db; init_db()"` |

### Output

| Raus | Format |
|---|---|
| Bewertung pro Kriterium | `evaluation: [{criterion, score, passed, feedback}]` (deutsches Klartext-Feedback) |
| Aggregat | `score` (gewichtet, 0..1) + `verdict` (pass/fail gegen threshold) |
| Persistenz | SQLite: `evaluation`, `evaluation_detail`, `suggestion`, `rewritten_requirement` |

### Bekannte Fallen (beide 2026-08-02 real erlebt)
1. **Stiller Mock-Fallback:** Ohne LLM-Zugang antwortet das Backend mit Heuristik-Scores
   statt Fehler. Erkennung: alle Scores identisch (~0.65), Feedback „Allgemeine Einschätzung".
2. **Orphan-Worker (Windows):** Uvicorn-Reload spawnt Worker via `multiprocessing.spawn`;
   Kill des Parents lässt Worker **mit alter Env am Port** weiterleben → Config-Änderungen
   scheinen wirkungslos. Fix: `multiprocessing.spawn`-Python-Kinder mit toter PPID gezielt killen.
3. `no such table: criterion` (400) → init_db vergessen.

---

## Datenfluss (Gesamtbild)

```
Dokument (PDF/DOCX/MD)
   │  multipart
   ▼
[System 1] /api/wizard/extract ── ChunkMiner (gpt-4o-mini) ──► Requirements-JSON
   │
   ▼
[System 1] /api/wizard/validate-batch
   │  {text, criteria_keys} pro Requirement, parallel (max 5)
   ▼
[System 2] /api/v2/evaluate/single ── LLM + 10 Kriterien ──► {score, verdict, feedback[]}
   │
   ▼
[System 1] decide ──► ACCEPT ─────────────────────────────► RE-Pipeline (Stages)
             │                                                   │
             ├─► REWRITE ─ improve (Gherkin-Kriterien) ─┐        ▼
             └─► SPLIT ── split (atomar) ───────────────┴─► enterprise_output/
                                                             + Supabase swe_design_runs/artifacts
```

---

## TODO (Stand 2026-08-06, Abarbeitung live verifiziert)

- [x] **P1 — Direkter Import validiert nicht** — ERLEDIGT: `ArchTeamImporter` fährt nach dem
      Mining den Validate→Decide→Rewrite-Loop (`_validate_and_improve`, RequirementsOrchestrator
      AUTO). Config `importers.arch_team.validate_on_import`/`validate_threshold` (Default an/0.7),
      Env-Override `RE_VALIDATE_ON_IMPORT`; Backend down → lauter Skip, Summary in
      `ImportResult.metadata.validation`. Live: 5 Reqs, pass-rate 1.0. (swe_desgine-Commits s. git log)
- [x] **P1 — Mock-Fallback laut machen** — ERLEDIGT: `_heuristic_mock_evaluation` loggt immer
      WARNING (`llm.evaluate.mock_fallback`) und markiert jedes Detail mit `mock: true`
      (EvalDetailV2-Feld). arch_team `186cba8`.
- [x] **P2 — `init_db()` beim Backend-Start** — ERLEDIGT: startup-Hook in backend/main.py,
      idempotent. arch_team `186cba8`.
- [x] **P2 — `_score: null` im improve-Response** — ERLEDIGT: Orchestrator stempelt
      `_validation_score`/`_validation_verdict` auf die Requirement-Dicts. Live: 0.87 (unangetastet)
      bzw. 1.0 (nach Rewrite). arch_team `186cba8`.
- [x] **P3 — Autostart beider Prozesse** — ERLEDIGT: `start_wizard_stack.ps1` (pwsh) killt
      Orphan-Worker, startet Backend `:8087` + Dashboard `:8080`, verifiziert runtime-config.
- [x] **P4 — Desktop-Kopie gesichert** — ERLEDIGT: 5 AutoGen-4.7.2-Agenten + Tests als Branch
      `backup/autogen-472-agents` (`486bb14`) auf Flissel/-req-orchestrator gepusht (Worktree
      unverändert). Pin-Bump-Entscheidung weiter offen (Agenten sind nirgends verdrahtet).
- [ ] **P3 — Wizard-Ergebnisse persistieren:** validate/improve-Resultate landen weiterhin
      nur in der System-2-SQLite lokal. Kandidat: `swe_design_artifacts` (artifact_type
      `validation_report`), Schema seit 2026-08-01 auf Proxmox — braucht Design-Entscheidung
      zum Run-Kontext (Wizard-Session ≠ Pipeline-Run).
- [ ] **P3 — OpenRouter-Rückbau dokumentiert lassen:** bei neuem Guthaben `.env`s
      (swe_desgine/ + external/arch_team/) löschen und `a40a924` reverten → Multi-Vendor-
      Modelle (Gemini Flash/Opus) wieder aktiv.
