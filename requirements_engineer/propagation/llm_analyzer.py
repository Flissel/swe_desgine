"""
LLM Analyzer - LLM integration for semantic analysis.

Uses existing ai_scientist/treesearch/backend for LLM calls.
Provides analysis for change propagation and link discovery.
"""

import json
import os
from typing import Dict, List, Optional, Any
import asyncio

from .models import PropagationAnalysis, LinkAnalysis


# Try to import the existing LLM backend
try:
    from ai_scientist.treesearch.backend import query, FunctionSpec
    BACKEND_AVAILABLE = True
except ImportError:
    BACKEND_AVAILABLE = False
    print("[LLMAnalyzer] ai_scientist.treesearch.backend not available")


class LLMAnalyzer:
    """
    LLM-powered analysis for change propagation and link discovery.

    Uses existing ai_scientist/treesearch/backend for LLM calls.
    """

    def __init__(self, model: str = None, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the LLM analyzer.

        Args:
            model: Model to use (overrides config)
            config: Configuration dict with propagation.llm_analyzer section
        """
        self.config = config or {}
        prop_config = self.config.get("propagation", {}).get("llm_analyzer", {})

        self.model = model or prop_config.get("model") or os.environ.get(
            "OPENROUTER_MODEL",
            "anthropic/claude-haiku-4.5"
        )
        self.temperature = prop_config.get("temperature", 0.3)
        self.max_tokens = prop_config.get("max_tokens", 4000)

        # Function specs for structured outputs
        self._propagation_spec = self._create_propagation_spec()
        self._link_spec = self._create_link_spec()

    def _create_propagation_spec(self):
        """Create FunctionSpec for propagation analysis."""
        if not BACKEND_AVAILABLE:
            return None

        return FunctionSpec(
            name="propagation_analysis",
            description="Analysiert ob ein verlinkter Node aktualisiert werden muss",
            json_schema={
                "type": "object",
                "properties": {
                    "needs_update": {
                        "type": "boolean",
                        "description": "Ob der verlinkte Node aktualisiert werden muss"
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Begründung auf Deutsch"
                    },
                    "suggested_changes": {
                        "type": "string",
                        "description": "Konkrete Änderungsvorschläge auf Deutsch"
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "description": "Konfidenz der Analyse (0.0 - 1.0)"
                    }
                },
                "required": ["needs_update", "reasoning", "confidence"]
            }
        )

    def _create_link_spec(self):
        """Create FunctionSpec for link suggestions."""
        if not BACKEND_AVAILABLE:
            return None

        return FunctionSpec(
            name="link_suggestions",
            description="Schlägt Verlinkungen für einen verwaisten Node vor",
            json_schema={
                "type": "object",
                "properties": {
                    "suggestions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "target_id": {
                                    "type": "string",
                                    "description": "ID des Ziel-Nodes"
                                },
                                "link_type": {
                                    "type": "string",
                                    "enum": ["dependency", "related", "parent", "child"],
                                    "description": "Art der Verlinkung"
                                },
                                "reasoning": {
                                    "type": "string",
                                    "description": "Begründung auf Deutsch"
                                },
                                "confidence": {
                                    "type": "number",
                                    "minimum": 0,
                                    "maximum": 1
                                }
                            },
                            "required": ["target_id", "link_type", "reasoning", "confidence"]
                        }
                    }
                },
                "required": ["suggestions"]
            }
        )

    async def analyze_propagation_need(
        self,
        changed_node: dict,
        linked_node: dict,
        link_type: str,
        change_summary: str = ""
    ) -> PropagationAnalysis:
        """
        Analyze if a linked node needs updating after a change.

        Args:
            changed_node: Data of the changed node
            linked_node: Data of the linked node
            link_type: Type of link between nodes
            change_summary: Summary of what changed

        Returns:
            PropagationAnalysis with results
        """
        if not BACKEND_AVAILABLE:
            return self._fallback_propagation_analysis(changed_node, linked_node)

        prompt = self._build_propagation_prompt(
            changed_node, linked_node, link_type, change_summary
        )

        try:
            # Run LLM query in thread pool to avoid blocking
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: query(
                    system_message=prompt,
                    user_message=None,
                    func_spec=self._propagation_spec,
                    model=self.model,
                    temperature=0.3
                )
            )

            return PropagationAnalysis(
                needs_update=result.get("needs_update", False),
                reasoning=result.get("reasoning", ""),
                suggested_changes=result.get("suggested_changes", ""),
                confidence=result.get("confidence", 0.0)
            )

        except Exception as e:
            print(f"[LLMAnalyzer] Propagation analysis error: {e}")
            return self._fallback_propagation_analysis(changed_node, linked_node)

    def _build_propagation_prompt(
        self,
        changed_node: dict,
        linked_node: dict,
        link_type: str,
        change_summary: str
    ) -> str:
        """Build the prompt for propagation analysis."""
        # Extract relevant info from nodes
        changed_info = self._extract_node_info(changed_node)
        linked_info = self._extract_node_info(linked_node)

        return f"""Du bist ein Requirements Engineering Assistent für ein deutschsprachiges Projekt.

## Aufgabe
Analysiere ob ein verknüpfter Node aktualisiert werden muss, nachdem ein anderer Node geändert wurde.

## Geänderter Node
- ID: {changed_info.get('id', 'unbekannt')}
- Typ: {changed_info.get('type', 'unbekannt')}
- Titel: {changed_info.get('title', 'unbekannt')}
- Beschreibung: {changed_info.get('description', '')[:500]}

## Änderungszusammenfassung
{change_summary or 'Keine Details verfügbar'}

## Verknüpfter Node (Verknüpfungstyp: {link_type})
- ID: {linked_info.get('id', 'unbekannt')}
- Typ: {linked_info.get('type', 'unbekannt')}
- Titel: {linked_info.get('title', 'unbekannt')}
- Beschreibung: {linked_info.get('description', '')[:500]}

## Analysiere
1. Steht der verknüpfte Node in direktem Zusammenhang mit der Änderung?
2. Könnte die Änderung Inkonsistenzen verursachen?
3. Müssen Abhängigkeiten, Beschreibungen oder Akzeptanzkriterien angepasst werden?

Antworte auf Deutsch."""

    def _extract_node_info(self, node: dict) -> dict:
        """Extract relevant information from a node."""
        return {
            "id": node.get("id") or node.get("requirement_id") or node.get("node_id", ""),
            "type": node.get("type", ""),
            "title": node.get("title", ""),
            "description": node.get("description", ""),
        }

    def _fallback_propagation_analysis(self, changed_node: dict, linked_node: dict) -> PropagationAnalysis:
        """Fallback analysis when LLM is not available."""
        # Simple heuristic: check if nodes share keywords
        changed_text = json.dumps(changed_node, ensure_ascii=False).lower()
        linked_text = json.dumps(linked_node, ensure_ascii=False).lower()

        # Count shared words (simple overlap)
        changed_words = set(changed_text.split())
        linked_words = set(linked_text.split())
        overlap = len(changed_words & linked_words)

        needs_update = overlap > 10  # Arbitrary threshold

        return PropagationAnalysis(
            needs_update=needs_update,
            reasoning="Automatische Analyse (LLM nicht verfügbar). Basiert auf Textähnlichkeit.",
            suggested_changes="Manuelle Überprüfung empfohlen.",
            confidence=0.3 if needs_update else 0.5
        )

    async def suggest_links(
        self,
        orphan_node: dict,
        candidate_nodes: List[dict],
        max_suggestions: int = 5
    ) -> List[LinkAnalysis]:
        """
        Suggest links for an orphan node.

        Args:
            orphan_node: Data of the orphan node
            candidate_nodes: List of potential target nodes
            max_suggestions: Maximum number of suggestions

        Returns:
            List of LinkAnalysis suggestions
        """
        print(f"[LLMAnalyzer] suggest_links called with {len(candidate_nodes)} candidates, BACKEND_AVAILABLE={BACKEND_AVAILABLE}")

        if not BACKEND_AVAILABLE:
            print("[LLMAnalyzer] Using fallback (backend not available)")
            return self._fallback_link_suggestions(orphan_node, candidate_nodes)

        # Limit candidates to avoid token limits
        candidates = candidate_nodes[:20]

        prompt = self._build_link_prompt(orphan_node, candidates, max_suggestions)
        print(f"[LLMAnalyzer] Calling LLM with model: {self.model}")

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: query(
                    system_message=prompt,
                    user_message=None,
                    func_spec=self._link_spec,
                    model=self.model,
                    temperature=0.3
                )
            )
            print(f"[LLMAnalyzer] LLM result: {result}")

            suggestions = []
            for s in result.get("suggestions", [])[:max_suggestions]:
                suggestions.append(LinkAnalysis(
                    target_id=s.get("target_id", ""),
                    link_type=s.get("link_type", "related"),
                    reasoning=s.get("reasoning", ""),
                    confidence=s.get("confidence", 0.0)
                ))

            print(f"[LLMAnalyzer] Returning {len(suggestions)} suggestions")
            return suggestions

        except Exception as e:
            import traceback
            print(f"[LLMAnalyzer] Link suggestion error: {e}")
            traceback.print_exc()
            return self._fallback_link_suggestions(orphan_node, candidate_nodes)

    def _build_link_prompt(
        self,
        orphan_node: dict,
        candidate_nodes: List[dict],
        max_suggestions: int
    ) -> str:
        """Build the prompt for link suggestions."""
        orphan_info = self._extract_node_info(orphan_node)

        candidates_text = ""
        for i, node in enumerate(candidate_nodes):
            info = self._extract_node_info(node)
            candidates_text += f"\n{i+1}. ID: {info['id']}, Typ: {info['type']}, Titel: {info['title']}"

        return f"""Du bist ein Requirements Engineering Assistent.

## Aufgabe
Analysiere den verwaisten Node (ohne Verknüpfungen) und schlage passende Verlinkungen zu anderen Nodes vor.

## Verwaister Node
- ID: {orphan_info.get('id', 'unbekannt')}
- Typ: {orphan_info.get('type', 'unbekannt')}
- Titel: {orphan_info.get('title', 'unbekannt')}
- Beschreibung: {orphan_info.get('description', '')[:500]}

## Mögliche Ziel-Nodes
{candidates_text}

## Anweisungen
1. Wähle bis zu {max_suggestions} passende Verlinkungen
2. Bestimme den Verknüpfungstyp:
   - "dependency": Node hängt vom Ziel ab
   - "related": Thematisch verwandt
   - "parent": Ziel ist übergeordnet
   - "child": Ziel ist untergeordnet
3. Gib nur Vorschläge mit Konfidenz > 0.5

Antworte auf Deutsch."""

    def _fallback_link_suggestions(
        self,
        orphan_node: dict,
        candidate_nodes: List[dict]
    ) -> List[LinkAnalysis]:
        """Fallback link suggestions when LLM is not available."""
        suggestions = []
        orphan_text = json.dumps(orphan_node, ensure_ascii=False).lower()
        orphan_words = set(orphan_text.split())

        for node in candidate_nodes[:5]:
            node_text = json.dumps(node, ensure_ascii=False).lower()
            node_words = set(node_text.split())

            overlap = len(orphan_words & node_words)
            confidence = min(overlap / 50, 0.8)  # Scale overlap to confidence

            if confidence > 0.3:
                info = self._extract_node_info(node)
                suggestions.append(LinkAnalysis(
                    target_id=info.get("id", ""),
                    link_type="related",
                    reasoning="Automatische Analyse (LLM nicht verfügbar). Basiert auf Textähnlichkeit.",
                    confidence=confidence
                ))

        # Sort by confidence
        suggestions.sort(key=lambda x: x.confidence, reverse=True)
        return suggestions[:3]

    async def generate_updated_content(
        self,
        original_content: str,
        change_context: str,
        node_type: str
    ) -> str:
        """
        Generate suggested updated content for a node.

        Args:
            original_content: Current content of the node
            change_context: Context about what changed
            node_type: Type of the node

        Returns:
            Suggested updated content
        """
        if not BACKEND_AVAILABLE:
            return original_content

        prompt = f"""Du bist ein Requirements Engineering Assistent.

## Aufgabe
Aktualisiere den folgenden Inhalt basierend auf den Änderungen.

## Ursprünglicher Inhalt
{original_content[:1000]}

## Änderungskontext
{change_context}

## Node-Typ
{node_type}

## Anweisungen
1. Passe den Inhalt an die Änderungen an
2. Behalte den Stil und die Struktur bei
3. Füge keine neuen Abschnitte hinzu, die nicht nötig sind
4. Antworte nur mit dem aktualisierten Inhalt, keine Erklärungen

Antworte auf Deutsch."""

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: query(
                    system_message=prompt,
                    user_message=None,
                    model=self.model,
                    temperature=0.5
                )
            )

            return result if isinstance(result, str) else original_content

        except Exception as e:
            print(f"[LLMAnalyzer] Content generation error: {e}")
            return original_content
