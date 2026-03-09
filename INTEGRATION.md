# SWE Design — Integration Guide

How to set up, configure, and run the SWE Design system in your environment.

---

## 1. Prerequisites

| Tool | Version | Required |
|------|---------|----------|
| Python | 3.10+ | Yes |
| Node.js | 18+ | Only for Electron desktop app |
| Git | 2.x | Yes (submodule support) |
| pip | latest | Yes |

## 2. Clone the Repository

```bash
git clone --recurse-submodules https://github.com/Flissel/swe_desgine.git
cd swe_desgine
```

If you already cloned without `--recurse-submodules`:

```bash
git submodule update --init --recursive
```

## 3. Python Dependencies

```bash
# (Optional) Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

# Install dependencies
pip install -r requirements.txt
```

### Additional packages (not in requirements.txt)

```bash
pip install omegaconf aiohttp websockets fastapi uvicorn
pip install autogen-agentchat autogen-ext  # For wizard AutoGen agents
```

## 4. API Keys

Copy the example and fill in your keys:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Required — at least one LLM provider
OPENROUTER_API_KEY=sk-or-...        # OpenRouter (recommended, routes to all models)

# Optional — direct provider keys
ANTHROPIC_API_KEY=sk-ant-...        # For Claude models directly
OPENAI_API_KEY=sk-...               # For OpenAI models directly

# Optional — additional services
SUPERMEMORY_API_KEY=...             # User story deduplication
S2_API_KEY=...                      # Semantic Scholar literature search
```

**OpenRouter** is the default provider. All models in `re_config.yaml` use OpenRouter routing format (`provider/model`). A single OpenRouter key is sufficient to run the full pipeline.

## 5. Configuration

The main config file is `requirements_engineer/re_config.yaml`. Key sections:

### LLM Models

```yaml
agent:
  code:
    model: openai/gpt-5.2-codex    # Main generation model
  feedback:
    model: google/gemini-3-flash-preview  # Evaluation/review model
```

To use cheaper/faster models, change these to e.g. `openai/gpt-4o-mini` or `google/gemini-3-flash-preview`.

### Enable/Disable Pipeline Features

```yaml
# Tree search refinement (iterative quality improvement)
treesearch:
  enabled: true    # Set false to skip

# Realtime spec (AsyncAPI/WebSocket)
generators:
  realtime_spec:
    enabled: true  # Set false to skip

# Architecture, state machines, component composition
generators:
  architecture:
    enabled: true
  state_machine:
    enabled: true
  component_composition:
    enabled: true
```

### Quality Thresholds

```yaml
validation:
  min_completeness: 0.8
  min_consistency: 0.9
  min_testability: 0.75

quality_gates:
  stage_1_min_requirements: 3
  stage_4_min_quality_score: 0.7
```

## 6. Create a Project Input

Place a JSON file in `re_ideas/`. Minimal format:

```json
{
  "Name": "my_project",
  "Title": "My Project",
  "Domain": "web",
  "Context": {
    "summary": "A brief description of what the software should do.",
    "business": "Business context and goals",
    "domain": "Domain area (e.g. Healthcare, Finance, Retail)",
    "technical": "Technical constraints (e.g. cloud-native, REST APIs)",
    "user": "Target users and scale"
  },
  "Stakeholders": [
    {
      "role": "Product Owner",
      "name": "Jane Doe",
      "concerns": ["ROI", "time-to-market"]
    },
    {
      "role": "End User",
      "persona": "Customer",
      "concerns": ["usability", "performance"],
      "goals": ["easy checkout", "fast search"]
    }
  ],
  "Features": [
    {
      "name": "User Authentication",
      "description": "Login, registration, password reset with OAuth2 support",
      "priority": "must"
    },
    {
      "name": "Product Catalog",
      "description": "Browsable product listing with search and filters",
      "priority": "must"
    }
  ],
  "Constraints": [
    "GDPR compliant",
    "Response time < 200ms for API calls",
    "Support 10k concurrent users"
  ]
}
```

## 7. Run the Pipeline

```bash
# Full enterprise pipeline (17 stages)
python run_re_system.py

# With a specific project file
python run_re_system.py --project re_ideas/my_project.json

# With custom config
python run_re_system.py --config requirements_engineer/re_config.yaml
```

### Output

Results are written to `enterprise_output/<ProjectName>_<timestamp>/`:

```
enterprise_output/My_Project_20260226_143022/
├── MASTER_DOCUMENT.md          # Complete consolidated document
├── requirements/               # REQ-001, REQ-002, ...
├── user_stories/               # User stories with acceptance criteria
├── test_documentation.md       # Test cases mapped to stories
├── api/
│   ├── api_documentation.md    # REST API spec
│   └── openapi_spec.yaml       # OpenAPI 3.0
├── data/
│   ├── data_dictionary.md      # Entities, relationships
│   └── er_diagram.mmd          # ER diagram (Mermaid)
├── design/
│   ├── ui_design.md            # Screen specs + ASCII wireframes
│   ├── ux_design.md            # UX flows, personas
│   └── tech_stack.md           # Technology selection
├── diagrams/                   # Mermaid diagrams (flowchart, sequence, class, ER, state, C4)
├── presentation/               # HTML pages for stakeholder review
├── project_scaffold/           # Generated directory structure
├── quality/                    # Quality reports, critique results
│   ├── quality_report.md
│   ├── traceability_matrix.md
│   └── trace_refinement_report.md
├── tasks/                      # Work breakdown / task list
├── training_data/              # LLM call logs (for fine-tuning)
└── pipeline_manifest.json      # Stage I/O, durations, costs
```

## 8. Run the Dashboard

Interactive web UI for visualizing artifacts and running the wizard.

```bash
python start_dashboard.py
```

Opens at `http://localhost:8765`. Three views:

- **Canvas** — Graph of all artifacts with cross-links
- **Wizard** — Step-by-step requirement mining
- **Pipeline** — Live progress, quality gates, costs

### Electron Desktop App (optional)

```bash
cd requirements_engineer/dashboard-electron
npm install
npm run dev    # Development mode
npm run build  # Production build
```

## 9. Architecture Review Tool (Submodule)

The `external/arch_team/` submodule is a standalone full-stack app for architecture reviews.

```bash
cd external/arch_team

# Backend
pip install -r requirements_fastapi.txt
cd backend && uvicorn main:app --reload

# Frontend (separate terminal)
npm install
npm run dev
```

See `external/arch_team/README.md` for full setup.

## 10. Integrate into Your Own Pipeline

### As a Python module

```python
from requirements_engineer.run_re_system import run_enterprise_mode, load_config

config = load_config()
results = run_enterprise_mode(config, project_path="re_ideas/my_project.json")
```

### Individual generators

```python
from requirements_engineer.generators.api_spec_generator import ApiSpecGenerator
from requirements_engineer.generators.data_dictionary_generator import DataDictionaryGenerator
from requirements_engineer.generators.user_story_generator import UserStoryGenerator

# Each generator takes (requirements, config) and returns structured output
api_gen = ApiSpecGenerator(config)
api_spec = api_gen.generate(requirements)
```

### Training data collection

The pipeline automatically collects LLM call data for fine-tuning:

```python
from requirements_engineer.training.collector import TrainingDataCollector

collector = TrainingDataCollector(config)
collector.start_run(project_name="my_project")
# ... run pipeline ...
collector.end_run()
# Exports to output_dir/training_data/
```

## 11. Troubleshooting

| Problem | Solution |
|---------|----------|
| `OPENROUTER_API_KEY not set` | Add key to `.env` or export as environment variable |
| `ModuleNotFoundError: omegaconf` | `pip install omegaconf` |
| `Connection refused on :8765` | Dashboard not running — `python start_dashboard.py` |
| Pipeline hangs at a stage | Check `re_config.yaml` — reduce `stage_timeout_seconds` or lower `max_iters` |
| Empty output / low quality | Use stronger models (e.g. `claude-opus-4.6` instead of flash) |
| Submodule empty after clone | `git submodule update --init --recursive` |

## 12. Cost Estimation

The pipeline tracks costs per stage in `pipeline_manifest.json`. Rough estimates per full run:

| Model tier | Approx. cost per project |
|------------|--------------------------|
| Budget (gemini-flash, gpt-4o-mini) | $0.50 – $2.00 |
| Standard (gpt-4o, claude-sonnet) | $5.00 – $15.00 |
| Premium (gpt-5.2-codex, claude-opus) | $15.00 – $40.00 |

Disable expensive stages (`treesearch`, `scaffold`, `screen_design`) to reduce costs.
