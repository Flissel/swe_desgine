# SWE Design

An AI-powered **Software Engineering Design** system that transforms natural-language project ideas into complete, production-ready software specifications.

## What It Does

Give it a project description — get back a full requirements package:

- **Requirements** — structured, traceable, acceptance-criteria-ready
- **User Stories** — persona-driven with priority and effort estimates
- **Test Cases** — mapped to stories with boundary and negative-path coverage
- **API Specs** — OpenAPI 3.0 + AsyncAPI 2.6 (WebSocket)
- **Data Dictionary** — entities, relationships, ER diagrams
- **UI/UX Design** — screen specs with ASCII wireframes, navigation maps, responsive layouts
- **Architecture** — tech stack selection, component composition, state machines
- **Project Scaffold** — directory structure generated from epics

All artifacts are **cross-linked** and **traceable** end-to-end (requirement → story → test → API → screen → entity).

## Pipeline

17-stage enterprise pipeline with quality gates and self-critique at each boundary:

```
Discovery → Analysis → Specification → Validation → Presentation
```

Each stage runs iterative refinement (tree search with evaluate → refine → expand → re-evaluate loops) and auto-fixes issues before advancing.

## Dashboard

Real-time web dashboard with three views:

- **Canvas** — Interactive graph visualization of all artifacts and their links
- **Wizard** — Step-by-step requirement mining with AI-assisted enrichment
- **Pipeline** — Live stage progress, I/O tracking, quality gate badges

Includes an **Electron desktop app** for standalone use.

## Architecture Review (Submodule)

`external/arch_team/` — Full-stack architecture review tool with:
- AutoGen multi-agent teams (clarification, planning, evaluation)
- FastAPI backend + React frontend
- MCP server integration
- Qdrant vector store for knowledge graphs

## Quick Start

```bash
# Clone with submodules
git clone --recurse-submodules https://github.com/Flissel/swe_desgine.git
cd swe_desgine

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys (OpenRouter, etc.)

# Run the pipeline
python run_re_system.py

# Or start the dashboard
python start_dashboard.py
```

## Configuration

Edit `requirements_engineer/re_config.yaml` to customize:

- LLM models and providers (OpenRouter)
- Pipeline stages (enable/disable individually)
- Quality gate thresholds
- Tree search depth and iteration limits
- Wizard agent settings

## Project Structure

```
swe_desgine/
├── requirements_engineer/     # Core system
│   ├── core/                  # Journal, agent manager, draft engine
│   ├── stages/                # 5-stage pipeline + agents
│   ├── generators/            # 10+ artifact generators
│   ├── critique/              # Self-critique with auto-fix
│   ├── gates/                 # Quality gates
│   ├── treesearch/            # Iterative tree-search refinement
│   ├── dashboard/             # Web dashboard (FastAPI + WebSocket)
│   ├── dashboard-electron/    # Electron desktop app
│   ├── wizard/                # AI-assisted requirement mining
│   ├── training/              # Training data collection
│   ├── tools/                 # Kilo CLI, Mermaid tools
│   └── testing/               # Stage evaluators
├── external/
│   └── arch_team/             # Architecture review (git submodule)
├── enterprise_output/         # Example pipeline output
├── re_ideas/                  # Project input files
├── run_re_system.py           # Entry point: pipeline
├── start_dashboard.py         # Entry point: dashboard
└── requirements.txt
```

## License

[Apache License 2.0](LICENSE)
