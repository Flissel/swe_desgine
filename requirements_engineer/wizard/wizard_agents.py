"""
Wizard Agent Teams - AutoGen 0.4+ powered enrichment for each wizard step.

Uses SocietyOfMindAgent wrapping RoundRobinGroupChat inner teams
for complex multi-agent evaluation tasks.

Teams:
    1. StakeholderTeam - generates stakeholders from project context (Step 1)
    2. ContextEnricher - expands terse descriptions (Step 1)
    3. RequirementGapTeam - identifies gaps and suggests requirements (Step 3)
    4. ConstraintTeam - extracts and validates constraints (Step 5)
"""

import os
import re
import json
import time
import logging
import asyncio
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

logger = logging.getLogger("wizard.agents")

# ============================================================
# Lazy imports for AutoGen (graceful fallback for tests)
# ============================================================

_autogen_available = None


def _check_autogen():
    """Lazy-check AutoGen availability."""
    global _autogen_available
    if _autogen_available is not None:
        return _autogen_available
    try:
        from autogen_agentchat.agents import AssistantAgent  # noqa: F401
        from autogen_agentchat.teams import RoundRobinGroupChat  # noqa: F401
        _autogen_available = True
    except ImportError:
        logger.warning("AutoGen not available - wizard agents will use fallback mode")
        _autogen_available = False
    return _autogen_available


# ============================================================
# Result Type
# ============================================================

@dataclass
class WizardTeamResult:
    """Structured result from any agent team."""
    suggestions: List[Dict[str, Any]]
    team_name: str
    duration_ms: int
    success: bool
    error: Optional[str] = None


# ============================================================
# Model Client Factory
# ============================================================

def _create_openrouter_client(model: str, temperature: float = 0.3):
    """Create an OpenRouter model client via AutoGen's OpenAIChatCompletionClient."""
    from autogen_ext.models.openai import OpenAIChatCompletionClient
    from autogen_core.models import ModelInfo

    api_key = (
        os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("ZAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    )
    base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    return OpenAIChatCompletionClient(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        model_info=ModelInfo(
            vision=False,
            function_calling=True,
            json_output=True,
            family="openrouter",
        ),
    )


# ============================================================
# JSON Extraction (4-strategy, from ScreenGeneratorAgent)
# ============================================================

def _extract_json(text: str) -> Any:
    """Extract JSON from LLM response using multiple strategies."""
    # Strategy 1: Direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Strategy 2: Markdown fence ```json ... ```
    match = re.search(r"```json\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: Generic fence ``` ... ```
    match = re.search(r"```\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 4: Find first [ ... ] or { ... } block
    for pattern in [r"\[[\s\S]*\]", r"\{[\s\S]*\}"]:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

    return None


def _get_final_text(result) -> str:
    """Extract final text from AutoGen team result."""
    if hasattr(result, "messages") and result.messages:
        last = result.messages[-1]
        if hasattr(last, "content"):
            return last.content if isinstance(last.content, str) else str(last.content)
    return str(result)


# ============================================================
# System Prompts
# ============================================================

STAKEHOLDER_GENERATOR_PROMPT = """You are a Stakeholder Analyst for software projects.
Given a project description and domain, identify 3-8 key stakeholders.

For each stakeholder, output a JSON object with:
- role: the stakeholder role (e.g. "Product Owner", "End User", "Developer", "DevOps")
- persona: a short persona name (e.g. "Online Shopper", "Admin User")
- concerns: array of 2-4 key concerns
- goals: array of 2-3 goals
- impact_level: "HIGH" | "MEDIUM" | "LOW"
- confidence: float 0.0-1.0 indicating how certain this stakeholder is relevant

Output ONLY a JSON array. No explanations outside JSON."""

STAKEHOLDER_REVIEWER_PROMPT = """You are a Stakeholder Reviewer. You validate stakeholder lists for completeness.

Check for coverage of:
1. Business stakeholders (sponsors, product owners)
2. End users (different user types/personas)
3. Technical stakeholders (developers, architects, DevOps)
4. Regulatory/compliance stakeholders (if applicable)
5. Support/operations stakeholders

If the list is complete and well-formed, respond with exactly: STAKEHOLDERS_COMPLETE

If not, list specific missing perspectives and ask the generator to add them.
Always respond in English."""

CONTEXT_ENRICHER_PROMPT = """You are a Project Context Analyst. Given a project name, description, and domain,
expand the information into a structured context object.

Output a JSON object with exactly these fields:
- summary: 2-3 sentence project summary
- business: business context (market, target audience, revenue model)
- domain: specific domain areas (e.g. "Retail, Logistics, Payment Processing")
- technical: technical context (architecture style, integration needs)
- user: user context (user types, expected scale, usage patterns)
- confidence: float 0.0-1.0

Output ONLY JSON. No explanations outside JSON."""

GAP_ANALYZER_PROMPT = """You are a Requirements Gap Analyst. Given a list of existing requirements,
project context, and stakeholders, identify missing requirement areas.

Analyze for gaps in:
1. Security & Authentication requirements
2. Performance & Scalability requirements
3. Data management & Privacy requirements
4. Error handling & Recovery requirements
5. Monitoring & Observability requirements
6. Integration & API requirements
7. Usability & Accessibility requirements
8. Deployment & Operations requirements

For each gap found, output a JSON object with:
- area: the gap area name
- severity: "critical" | "important" | "nice_to_have"
- description: why this gap matters
- existing_coverage: brief note on what's already covered (if anything)

Output ONLY a JSON array of gaps. No explanations outside JSON."""

REQUIREMENT_SUGGESTER_PROMPT = """You are a Requirements Engineer. Given identified gaps and project context,
generate specific requirement suggestions to fill those gaps.

For each suggestion, output a JSON object with:
- title: short requirement title (imperative form, e.g. "Implement rate limiting")
- description: detailed requirement description (1-2 sentences)
- type: "functional" | "non_functional" | "constraint"
- priority: "must" | "should" | "could"
- gap_area: which gap this addresses
- confidence: float 0.0-1.0 indicating how certain this requirement is needed

Output ONLY a JSON array. Generate 3-8 requirements addressing the most critical gaps first."""

REQUIREMENT_CRITIC_PROMPT = """You are a Requirements Quality Critic. You evaluate suggested requirements
for quality, overlap, and completeness.

For each suggested requirement, check:
1. Is it specific enough to be testable?
2. Does it overlap with existing requirements?
3. Is the priority appropriate?
4. Is the type classification correct?

If the suggestions are good and address the gaps, respond with exactly: GAPS_ANALYZED

If there are issues, provide specific critique for the suggester to address.
Do NOT suggest new requirements yourself. Only critique the existing suggestions."""

CONSTRAINT_EXTRACTOR_PROMPT = """You are a Constraint Analyst. Given a list of requirements and project context,
extract implicit constraints that aren't explicitly stated.

Look for:
1. Technical constraints implied by requirements (e.g. "real-time" implies WebSocket or SSE)
2. Regulatory constraints implied by data handling (e.g. user data implies GDPR)
3. Performance constraints implied by scale (e.g. "10k users" implies load balancing)
4. Security constraints implied by sensitive data
5. Infrastructure constraints implied by architecture

For each constraint, output a JSON object with:
- category: "technical" | "regulatory" | "performance" | "security" | "infrastructure"
- constraint: the constraint text
- source: which requirement(s) implied this
- confidence: float 0.0-1.0
- reasoning: brief explanation

Output ONLY a JSON array. No explanations outside JSON."""

CONSTRAINT_VALIDATOR_PROMPT = """You are a Constraint Validator. You check constraints for:
1. Internal consistency (no contradictions)
2. Completeness relative to requirements
3. Feasibility (not impossible to satisfy)

If all constraints are valid and consistent, respond with exactly: CONSTRAINTS_VALIDATED

If there are issues, describe each conflict or concern specifically.
Always respond in English."""


# ============================================================
# Team 1: StakeholderTeam (Step 1)
# ============================================================

class StakeholderTeam:
    """SocietyOfMind team that generates stakeholders from project context."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        team_config = self.config.get("agents", {}).get("stakeholder_team", {})
        self.model = team_config.get("model", "google/gemini-2.5-flash-preview")
        self.temperature = team_config.get("temperature", 0.5)
        self.max_messages = self.config.get("max_iterations", {}).get("stakeholder_team", 6)

    async def run(
        self,
        project_name: str,
        description: str,
        domain: str,
        target_users: List[str],
    ) -> WizardTeamResult:
        """Generate stakeholder suggestions using a Generator+Reviewer team."""
        start_time = time.time()

        if not _check_autogen():
            return self._fallback(project_name, description, domain, target_users)

        try:
            from autogen_agentchat.agents import AssistantAgent, SocietyOfMindAgent
            from autogen_agentchat.teams import RoundRobinGroupChat
            from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination

            client = _create_openrouter_client(self.model, self.temperature)

            generator = AssistantAgent(
                "stakeholder_generator",
                model_client=client,
                system_message=STAKEHOLDER_GENERATOR_PROMPT,
            )
            reviewer = AssistantAgent(
                "stakeholder_reviewer",
                model_client=client,
                system_message=STAKEHOLDER_REVIEWER_PROMPT,
            )

            termination = TextMentionTermination("STAKEHOLDERS_COMPLETE") | MaxMessageTermination(self.max_messages)
            inner_team = RoundRobinGroupChat([generator, reviewer], termination_condition=termination)

            som = SocietyOfMindAgent("stakeholder_som", team=inner_team, model_client=client)
            outer_team = RoundRobinGroupChat([som], max_turns=1)

            task = (
                f"Project: {project_name}\n"
                f"Domain: {domain}\n"
                f"Description: {description}\n"
                f"Known target users: {', '.join(target_users) if target_users else 'not specified'}\n\n"
                f"Generate a comprehensive stakeholder list for this project."
            )

            result = await outer_team.run(task=task)
            final_text = _get_final_text(result)
            parsed = _extract_json(final_text)

            suggestions = []
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        suggestions.append({
                            "type": "stakeholder",
                            "content": {
                                "role": item.get("role", "Stakeholder"),
                                "persona": item.get("persona", ""),
                                "concerns": item.get("concerns", []),
                                "goals": item.get("goals", []),
                                "impact_level": item.get("impact_level", "MEDIUM"),
                            },
                            "confidence": float(item.get("confidence", 0.75)),
                            "reasoning": f"Stakeholder '{item.get('role', '')}' identified for {domain} project",
                        })

            duration_ms = int((time.time() - start_time) * 1000)
            return WizardTeamResult(
                suggestions=suggestions,
                team_name="StakeholderTeam",
                duration_ms=duration_ms,
                success=len(suggestions) > 0,
                error=None if suggestions else "No stakeholders parsed from LLM response",
            )

        except Exception as e:
            logger.error("StakeholderTeam error: %s", e)
            duration_ms = int((time.time() - start_time) * 1000)
            return WizardTeamResult(
                suggestions=[],
                team_name="StakeholderTeam",
                duration_ms=duration_ms,
                success=False,
                error=str(e),
            )

    def _fallback(self, project_name, description, domain, target_users) -> WizardTeamResult:
        """Fallback when AutoGen is not available."""
        suggestions = []
        # Always suggest basic stakeholders
        for role, persona, concerns in [
            ("Product Owner", "Business Lead", ["ROI", "time-to-market", "feature completeness"]),
            ("End User", target_users[0] if target_users else "Primary User", ["usability", "performance", "reliability"]),
            ("Developer", "Engineering Team", ["maintainability", "clear specifications", "testability"]),
        ]:
            suggestions.append({
                "type": "stakeholder",
                "content": {
                    "role": role,
                    "persona": persona,
                    "concerns": concerns,
                    "goals": [],
                    "impact_level": "HIGH",
                },
                "confidence": 0.6,
                "reasoning": f"Default {role} stakeholder for {domain} project (fallback mode)",
            })
        return WizardTeamResult(
            suggestions=suggestions, team_name="StakeholderTeam",
            duration_ms=0, success=True,
        )


# ============================================================
# Team 2: ContextEnricher (Step 1)
# ============================================================

class ContextEnricher:
    """Single agent that expands terse project descriptions into structured context."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        team_config = self.config.get("agents", {}).get("context_enricher", {})
        self.model = team_config.get("model", "google/gemini-2.5-flash-preview")
        self.temperature = team_config.get("temperature", 0.4)

    async def run(
        self,
        project_name: str,
        description: str,
        domain: str,
    ) -> WizardTeamResult:
        """Enrich project context using a single agent."""
        start_time = time.time()

        if not _check_autogen():
            return self._fallback(project_name, description, domain)

        try:
            from autogen_agentchat.agents import AssistantAgent
            from autogen_agentchat.teams import RoundRobinGroupChat

            client = _create_openrouter_client(self.model, self.temperature)

            agent = AssistantAgent(
                "context_enricher",
                model_client=client,
                system_message=CONTEXT_ENRICHER_PROMPT,
            )

            team = RoundRobinGroupChat([agent], max_turns=1)
            task = (
                f"Project: {project_name}\n"
                f"Domain: {domain}\n"
                f"Description: {description}\n\n"
                f"Expand this into a structured context object."
            )

            result = await team.run(task=task)
            final_text = _get_final_text(result)
            parsed = _extract_json(final_text)

            suggestions = []
            if isinstance(parsed, dict):
                confidence = float(parsed.pop("confidence", 0.9))
                suggestions.append({
                    "type": "context",
                    "content": {
                        "summary": parsed.get("summary", description),
                        "business": parsed.get("business", ""),
                        "domain": parsed.get("domain", domain),
                        "technical": parsed.get("technical", ""),
                        "user": parsed.get("user", ""),
                    },
                    "confidence": confidence,
                    "reasoning": "Context enriched from project description using domain knowledge",
                })

            duration_ms = int((time.time() - start_time) * 1000)
            return WizardTeamResult(
                suggestions=suggestions, team_name="ContextEnricher",
                duration_ms=duration_ms, success=len(suggestions) > 0,
                error=None if suggestions else "No context parsed from LLM response",
            )

        except Exception as e:
            logger.error("ContextEnricher error: %s", e)
            duration_ms = int((time.time() - start_time) * 1000)
            return WizardTeamResult(
                suggestions=[], team_name="ContextEnricher",
                duration_ms=duration_ms, success=False, error=str(e),
            )

    def _fallback(self, project_name, description, domain) -> WizardTeamResult:
        """Fallback when AutoGen is not available."""
        return WizardTeamResult(
            suggestions=[{
                "type": "context",
                "content": {
                    "summary": description or f"{project_name} - a {domain} project",
                    "business": "", "domain": domain, "technical": "", "user": "",
                },
                "confidence": 0.5,
                "reasoning": "Basic context from project description (fallback mode)",
            }],
            team_name="ContextEnricher", duration_ms=0, success=True,
        )


# ============================================================
# Team 3: RequirementGapTeam (Step 3)
# ============================================================

class RequirementGapTeam:
    """SocietyOfMind team for gap analysis and requirement suggestions."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        team_config = self.config.get("agents", {}).get("requirement_gap_team", {})
        self.model = team_config.get("model", "anthropic/claude-opus-4.6")
        self.temperature = team_config.get("temperature", 0.4)
        self.max_messages = self.config.get("max_iterations", {}).get("requirement_gap_team", 8)

    async def run(
        self,
        requirements: List[Dict[str, Any]],
        stakeholders: List[Dict[str, Any]],
        domain: str,
        description: str,
    ) -> WizardTeamResult:
        """Analyze requirement gaps and suggest new requirements."""
        start_time = time.time()

        if not _check_autogen():
            return WizardTeamResult(
                suggestions=[], team_name="RequirementGapTeam",
                duration_ms=0, success=True,
            )

        try:
            from autogen_agentchat.agents import AssistantAgent, SocietyOfMindAgent
            from autogen_agentchat.teams import RoundRobinGroupChat
            from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination

            client = _create_openrouter_client(self.model, self.temperature)

            analyzer = AssistantAgent(
                "gap_analyzer",
                model_client=client,
                system_message=GAP_ANALYZER_PROMPT,
            )
            suggester = AssistantAgent(
                "requirement_suggester",
                model_client=client,
                system_message=REQUIREMENT_SUGGESTER_PROMPT,
            )
            critic = AssistantAgent(
                "requirement_critic",
                model_client=client,
                system_message=REQUIREMENT_CRITIC_PROMPT,
            )

            termination = TextMentionTermination("GAPS_ANALYZED") | MaxMessageTermination(self.max_messages)
            inner_team = RoundRobinGroupChat([analyzer, suggester, critic], termination_condition=termination)

            som = SocietyOfMindAgent("gap_analysis_som", team=inner_team, model_client=client)
            outer_team = RoundRobinGroupChat([som], max_turns=1)

            # Format existing requirements for context
            req_summary = "\n".join(
                f"- {r.get('title', r.get('name', 'Untitled'))}: {r.get('description', '')}"
                for r in requirements[:30]  # Limit to avoid token overflow
            ) or "No requirements yet"

            stakeholder_summary = "\n".join(
                f"- {s.get('role', 'Unknown')}: concerns={s.get('concerns', [])}"
                for s in stakeholders[:10]
            ) or "No stakeholders defined"

            task = (
                f"Domain: {domain}\n"
                f"Description: {description}\n\n"
                f"Existing Requirements ({len(requirements)}):\n{req_summary}\n\n"
                f"Stakeholders:\n{stakeholder_summary}\n\n"
                f"Analyze gaps in the existing requirements and suggest new ones."
            )

            result = await outer_team.run(task=task)
            final_text = _get_final_text(result)
            parsed = _extract_json(final_text)

            suggestions = []
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and "title" in item:
                        suggestions.append({
                            "type": "requirement",
                            "content": {
                                "title": item.get("title", ""),
                                "description": item.get("description", ""),
                                "type": item.get("type", "functional"),
                                "priority": item.get("priority", "should"),
                                "gap_area": item.get("gap_area", ""),
                            },
                            "confidence": float(item.get("confidence", 0.7)),
                            "reasoning": f"Gap: {item.get('gap_area', 'unspecified')}",
                        })

            duration_ms = int((time.time() - start_time) * 1000)
            return WizardTeamResult(
                suggestions=suggestions, team_name="RequirementGapTeam",
                duration_ms=duration_ms, success=True,
            )

        except Exception as e:
            logger.error("RequirementGapTeam error: %s", e)
            duration_ms = int((time.time() - start_time) * 1000)
            return WizardTeamResult(
                suggestions=[], team_name="RequirementGapTeam",
                duration_ms=duration_ms, success=False, error=str(e),
            )


# ============================================================
# Team 4: ConstraintTeam (Step 5)
# ============================================================

class ConstraintTeam:
    """SocietyOfMind team for constraint extraction and validation."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        team_config = self.config.get("agents", {}).get("constraint_team", {})
        self.model = team_config.get("model", "google/gemini-2.5-flash-preview")
        self.temperature = team_config.get("temperature", 0.3)
        self.max_messages = self.config.get("max_iterations", {}).get("constraint_team", 6)

    async def run(
        self,
        requirements: List[Dict[str, Any]],
        existing_constraints: Dict[str, Any],
        domain: str,
    ) -> WizardTeamResult:
        """Extract implicit constraints from requirements."""
        start_time = time.time()

        if not _check_autogen():
            return WizardTeamResult(
                suggestions=[], team_name="ConstraintTeam",
                duration_ms=0, success=True,
            )

        try:
            from autogen_agentchat.agents import AssistantAgent, SocietyOfMindAgent
            from autogen_agentchat.teams import RoundRobinGroupChat
            from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination

            client = _create_openrouter_client(self.model, self.temperature)

            extractor = AssistantAgent(
                "constraint_extractor",
                model_client=client,
                system_message=CONSTRAINT_EXTRACTOR_PROMPT,
            )
            validator = AssistantAgent(
                "constraint_validator",
                model_client=client,
                system_message=CONSTRAINT_VALIDATOR_PROMPT,
            )

            termination = TextMentionTermination("CONSTRAINTS_VALIDATED") | MaxMessageTermination(self.max_messages)
            inner_team = RoundRobinGroupChat([extractor, validator], termination_condition=termination)

            som = SocietyOfMindAgent("constraint_som", team=inner_team, model_client=client)
            outer_team = RoundRobinGroupChat([som], max_turns=1)

            req_summary = "\n".join(
                f"- {r.get('title', r.get('name', 'Untitled'))}: {r.get('description', '')}"
                for r in requirements[:30]
            ) or "No requirements"

            existing_summary = json.dumps(existing_constraints, indent=2) if existing_constraints else "None"

            task = (
                f"Domain: {domain}\n\n"
                f"Requirements ({len(requirements)}):\n{req_summary}\n\n"
                f"Existing constraints:\n{existing_summary}\n\n"
                f"Extract implicit constraints from the requirements."
            )

            result = await outer_team.run(task=task)
            final_text = _get_final_text(result)
            parsed = _extract_json(final_text)

            suggestions = []
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        category = item.get("category", "technical")
                        constraint_text = item.get("constraint", "")
                        if not constraint_text:
                            continue

                        suggestions.append({
                            "type": "constraint",
                            "content": {
                                "category": category,
                                "constraint": constraint_text,
                                "source": item.get("source", ""),
                            },
                            "confidence": float(item.get("confidence", 0.7)),
                            "reasoning": item.get("reasoning", f"Extracted {category} constraint from requirements"),
                        })

            duration_ms = int((time.time() - start_time) * 1000)
            return WizardTeamResult(
                suggestions=suggestions, team_name="ConstraintTeam",
                duration_ms=duration_ms, success=True,
            )

        except Exception as e:
            logger.error("ConstraintTeam error: %s", e)
            duration_ms = int((time.time() - start_time) * 1000)
            return WizardTeamResult(
                suggestions=[], team_name="ConstraintTeam",
                duration_ms=duration_ms, success=False, error=str(e),
            )
