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

## TODO (offen, priorisiert)

- [ ] **P1 — Direkter Import validiert nicht:** `ArchTeamImporter` (server.py ~2670) ruft
      ChunkMiner roh, ohne validate/improve-Loop. Ungeprüfte Requirements landen in der
      Pipeline. → Nach Mining denselben Validate→Decide→Rewrite-Pfad fahren (Config-Flag).
- [ ] **P1 — Mock-Fallback laut machen:** `_heuristic_mock_evaluation` (backend/core/llm.py)
      sollte im Response ein `"mock": true`-Flag setzen und WARNING loggen — sonst sehen
      Fake-Scores wie echte aus (Ground-Truth-Prinzip verletzt).
- [ ] **P2 — `init_db()` beim Backend-Start automatisch** aufrufen (lifespan-Hook), statt
      manuellem Seed; idempotent ist es schon.
- [ ] **P2 — `_score: null` im improve-Response:** Rewrite-Entscheidung fällt ohne sichtbaren
      Score; Score aus der Validierung durchreichen, damit UI/Aufrufer nachvollziehen können,
      warum (nicht) umgeschrieben wurde.
- [ ] **P3 — Wizard-Ergebnisse persistieren:** validate/improve-Resultate landen aktuell
      nirgends dauerhaft (nur System-2-SQLite lokal). Kandidat: `swe_design_artifacts`
      (artifact_type `validation_report`), Schema existiert seit 2026-08-01 auf Proxmox.
- [ ] **P3 — Autostart beider Prozesse** (ein Startscript oder Launcher-Sidecar), inkl.
      Port-Check gegen Orphan-Worker (Falle 2).
- [ ] **P3 — OpenRouter-Rückbau dokumentiert lassen:** bei neuem Guthaben `.env`s
      (swe_desgine/ + external/arch_team/) löschen und `a40a924` reverten → Multi-Vendor-
      Modelle (Gemini Flash/Opus) wieder aktiv.
- [ ] **P4 — Submodule vs. Desktop-Kopie:** 5 neue AutoGen-4.7.2-Agenten (+Tests) liegen
      uncommitted NUR in `C:/Users/User/Desktop/-req-orchestrator` (Cross-Chunk-Extraktion,
      LLM-KG, Mermaid, OutputValidator). Committen/pushen, dann entscheiden ob Pin-Bump.
