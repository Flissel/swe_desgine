"""
Kilo Integration Agent for Multi-Agent HTML Generation.

This agent interfaces with the Kilocode CLI tool for complex operations
like diagram generation, code analysis, and content transformation.
"""

import logging
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from .base_presentation_agent import (
    BasePresentationAgent,
    AgentRole,
    AgentCapability,
    PresentationContext,
    AgentResult,
    ImprovementType,
)

# Import the Kilocode CLI wrapper
try:
    from requirements_engineer.tools.kilocli_tool import KilocodeCliTool
    KILO_AVAILABLE = True
except ImportError:
    KILO_AVAILABLE = False
    KilocodeCliTool = None

log = logging.getLogger(__name__)


@dataclass
class KiloTaskResult:
    """Result of a Kilo CLI task."""
    task_type: str
    success: bool
    output: str
    generated_files: List[str] = field(default_factory=list)
    error: Optional[str] = None
    duration_seconds: float = 0.0


class KiloIntegrationAgent(BasePresentationAgent):
    """
    Agent that interfaces with Kilocode CLI for complex operations.

    Capabilities:
    - Generate complex Mermaid diagrams
    - Analyze and transform code
    - Generate code snippets
    - Perform complex content transformations

    Uses Kilocode CLI modes:
    - architect: For design and planning
    - code: For code generation and modification
    - ask: For querying and analysis
    - review: For code review
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="KiloIntegration",
            role=AgentRole.KILO_INTEGRATION,
            description="Interfaces with Kilo CLI for complex generation tasks",
            capabilities=[
                AgentCapability.DIAGRAM_GENERATION,
                AgentCapability.CODE_EXECUTION,
                AgentCapability.CONTENT_ENHANCEMENT,
            ],
            config=config
        )

        # Kilo configuration
        self.kilo_mode = config.get("mode", "code") if config else "code"
        self.kilo_timeout = config.get("timeout", 300) if config else 300
        self.kilo_workspace = config.get("workspace") if config else None

        # Initialize Kilo CLI wrapper if available
        self.kilo_cli: Optional[KilocodeCliTool] = None
        self._kilo_available = KILO_AVAILABLE

        if KILO_AVAILABLE:
            try:
                self.kilo_cli = KilocodeCliTool()
                log.info("Kilo CLI initialized successfully")
            except FileNotFoundError as e:
                log.warning(f"Kilo CLI not available: {e}")
                self._kilo_available = False
        else:
            log.warning("Kilo CLI module not imported")

        # Task history
        self._task_history: List[KiloTaskResult] = []

    async def execute(self, context: PresentationContext) -> AgentResult:
        """
        Execute Kilo-based operations.

        Args:
            context: The presentation context

        Returns:
            AgentResult with Kilo task results
        """
        self._is_running = True
        self._current_context = context

        try:
            self._log_progress(f"Starting Kilo integration for project: {context.project_id}")

            if not self._kilo_available:
                return AgentResult(
                    success=False,
                    error_message="Kilo CLI is not available. Install with: npm install -g @kilocode/cli",
                    action_type="KILO_GENERATION",
                    notes="Kilo CLI not installed"
                )

            # Determine what tasks to run based on context
            tasks = self._determine_tasks(context)

            if not tasks:
                return AgentResult(
                    success=True,
                    action_type="KILO_GENERATION",
                    notes="No Kilo tasks needed",
                    stage_complete=True
                )

            # Execute tasks
            results: List[KiloTaskResult] = []
            generated_files: List[str] = []

            for task in tasks:
                result = await self._execute_kilo_task(context, task)
                results.append(result)
                self._task_history.append(result)

                if result.success:
                    generated_files.extend(result.generated_files)

            # Summarize results
            success_count = sum(1 for r in results if r.success)
            success_rate = success_count / len(results) if results else 0

            return AgentResult(
                success=success_count > 0,
                generated_files=generated_files,
                action_type="KILO_GENERATION",
                notes=f"Executed {len(results)} Kilo tasks, {success_count} successful",
                recommendations=[
                    f"Generated {len(generated_files)} files via Kilo",
                    "Review generated content for accuracy"
                ],
                confidence=success_rate,
                needs_review=True
            )

        except Exception as e:
            self._log_error(f"Kilo integration failed: {e}")
            return AgentResult(
                success=False,
                error_message=str(e),
                action_type="KILO_GENERATION",
                notes=f"Kilo integration failed: {e}"
            )

        finally:
            self._is_running = False

    def _determine_tasks(self, context: PresentationContext) -> List[Dict[str, Any]]:
        """Determine what Kilo tasks to run based on context."""
        tasks = []

        # Check for diagram generation needs
        if context.quality_issues:
            for issue in context.quality_issues:
                if issue.get("category") == "diagrams" or "diagram" in issue.get("description", "").lower():
                    tasks.append({
                        "type": "generate_diagram",
                        "description": issue.get("description", ""),
                        "suggestion": issue.get("suggestion", "")
                    })

        # Check for code generation needs
        for issue in context.quality_issues:
            if "code" in issue.get("description", "").lower():
                tasks.append({
                    "type": "generate_code",
                    "description": issue.get("description", ""),
                    "suggestion": issue.get("suggestion", "")
                })

        return tasks[:5]  # Limit to 5 tasks

    async def _execute_kilo_task(
        self,
        context: PresentationContext,
        task: Dict[str, Any]
    ) -> KiloTaskResult:
        """Execute a single Kilo task."""
        task_type = task.get("type", "unknown")
        start_time = datetime.now()

        self._log_progress(f"Executing Kilo task: {task_type}")

        try:
            if task_type == "generate_diagram":
                return await self._generate_diagram(context, task)
            elif task_type == "generate_code":
                return await self._generate_code(context, task)
            elif task_type == "analyze_content":
                return await self._analyze_content(context, task)
            else:
                return KiloTaskResult(
                    task_type=task_type,
                    success=False,
                    output="",
                    error=f"Unknown task type: {task_type}"
                )

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return KiloTaskResult(
                task_type=task_type,
                success=False,
                output="",
                error=str(e),
                duration_seconds=duration
            )

    async def _generate_diagram(
        self,
        context: PresentationContext,
        task: Dict[str, Any]
    ) -> KiloTaskResult:
        """Generate a Mermaid diagram using Kilo."""
        start_time = datetime.now()

        description = task.get("description", "")
        suggestion = task.get("suggestion", "")

        # Build prompt for Kilo
        prompt = f"""Generate a Mermaid diagram based on the following context:

Project: {context.project_id}
Description: {description}
Suggestion: {suggestion}

Requirements:
1. Use valid Mermaid syntax
2. Include clear labels and descriptions
3. Keep the diagram focused and readable
4. Output ONLY the Mermaid code, no explanations

Respond with the Mermaid diagram code only."""

        try:
            # Run Kilo in code mode
            result = self.kilo_cli.run_autonomous(
                prompt=prompt,
                workspace=context.output_dir,
                mode="code",
                timeout=self.kilo_timeout,
                json_output=True,
                yolo=True
            )

            duration = (datetime.now() - start_time).total_seconds()

            if result.get("success"):
                output = result.get("stdout", "")

                # Try to extract Mermaid code from output
                mermaid_code = self._extract_mermaid(output)

                if mermaid_code:
                    # Save diagram to file
                    diagram_path = self._save_diagram(context, mermaid_code)

                    return KiloTaskResult(
                        task_type="generate_diagram",
                        success=True,
                        output=mermaid_code,
                        generated_files=[str(diagram_path)] if diagram_path else [],
                        duration_seconds=duration
                    )

            return KiloTaskResult(
                task_type="generate_diagram",
                success=False,
                output=result.get("stdout", ""),
                error=result.get("stderr", "Diagram generation failed"),
                duration_seconds=duration
            )

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return KiloTaskResult(
                task_type="generate_diagram",
                success=False,
                output="",
                error=str(e),
                duration_seconds=duration
            )

    async def _generate_code(
        self,
        context: PresentationContext,
        task: Dict[str, Any]
    ) -> KiloTaskResult:
        """Generate code snippets using Kilo."""
        start_time = datetime.now()

        description = task.get("description", "")
        suggestion = task.get("suggestion", "")

        prompt = f"""Generate code based on the following context:

Project: {context.project_id}
Description: {description}
Suggestion: {suggestion}

Requirements:
1. Write clean, well-documented code
2. Include relevant imports and dependencies
3. Follow best practices for the target language
4. Output the code with appropriate file extension"""

        try:
            result = self.kilo_cli.run_autonomous(
                prompt=prompt,
                workspace=context.output_dir,
                mode="code",
                timeout=self.kilo_timeout,
                json_output=True,
                yolo=True
            )

            duration = (datetime.now() - start_time).total_seconds()

            return KiloTaskResult(
                task_type="generate_code",
                success=result.get("success", False),
                output=result.get("stdout", ""),
                error=result.get("stderr") if not result.get("success") else None,
                duration_seconds=duration
            )

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return KiloTaskResult(
                task_type="generate_code",
                success=False,
                output="",
                error=str(e),
                duration_seconds=duration
            )

    async def _analyze_content(
        self,
        context: PresentationContext,
        task: Dict[str, Any]
    ) -> KiloTaskResult:
        """Analyze content using Kilo's ask mode."""
        start_time = datetime.now()

        description = task.get("description", "")

        prompt = f"""Analyze the following content and provide insights:

Project: {context.project_id}
Task: {description}

Provide:
1. Key findings
2. Recommendations
3. Potential improvements"""

        try:
            result = self.kilo_cli.run_autonomous(
                prompt=prompt,
                workspace=context.output_dir,
                mode="ask",
                timeout=self.kilo_timeout,
                json_output=True
            )

            duration = (datetime.now() - start_time).total_seconds()

            return KiloTaskResult(
                task_type="analyze_content",
                success=result.get("success", False),
                output=result.get("stdout", ""),
                error=result.get("stderr") if not result.get("success") else None,
                duration_seconds=duration
            )

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return KiloTaskResult(
                task_type="analyze_content",
                success=False,
                output="",
                error=str(e),
                duration_seconds=duration
            )

    def _extract_mermaid(self, output: str) -> Optional[str]:
        """Extract Mermaid code from Kilo output."""
        import re

        # Try to find Mermaid code block
        mermaid_patterns = [
            r'```mermaid\s*(.*?)\s*```',
            r'```\s*(graph\s+.*?)\s*```',
            r'```\s*(sequenceDiagram.*?)\s*```',
            r'```\s*(classDiagram.*?)\s*```',
            r'```\s*(flowchart.*?)\s*```',
            r'```\s*(erDiagram.*?)\s*```',
            r'```\s*(stateDiagram.*?)\s*```',
        ]

        for pattern in mermaid_patterns:
            match = re.search(pattern, output, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Check if output itself looks like Mermaid
        mermaid_keywords = ['graph ', 'sequenceDiagram', 'classDiagram', 'flowchart ', 'erDiagram', 'stateDiagram']
        for keyword in mermaid_keywords:
            if keyword in output:
                # Clean up the output
                lines = output.strip().split('\n')
                mermaid_lines = []
                in_diagram = False

                for line in lines:
                    if any(kw in line for kw in mermaid_keywords):
                        in_diagram = True
                    if in_diagram:
                        mermaid_lines.append(line)

                if mermaid_lines:
                    return '\n'.join(mermaid_lines)

        return None

    def _save_diagram(self, context: PresentationContext, mermaid_code: str) -> Optional[Path]:
        """Save Mermaid diagram to file."""
        try:
            output_dir = Path(context.output_dir) if context.output_dir else Path(".")
            diagrams_dir = output_dir / "diagrams"
            diagrams_dir.mkdir(parents=True, exist_ok=True)

            # Generate unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"diagram_{timestamp}.mmd"
            filepath = diagrams_dir / filename

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(mermaid_code)

            self._log_progress(f"Saved diagram to {filepath}")
            return filepath

        except Exception as e:
            log.error(f"Failed to save diagram: {e}")
            return None

    async def generate_diagram_direct(
        self,
        diagram_type: str,
        description: str,
        context: Optional[PresentationContext] = None
    ) -> KiloTaskResult:
        """
        Direct method to generate a specific diagram type.

        Args:
            diagram_type: Type of diagram (flowchart, sequence, class, etc.)
            description: Description of what the diagram should show
            context: Optional presentation context

        Returns:
            KiloTaskResult with the generated diagram
        """
        if not self._kilo_available:
            return KiloTaskResult(
                task_type="generate_diagram",
                success=False,
                output="",
                error="Kilo CLI not available"
            )

        start_time = datetime.now()

        prompt = f"""Generate a {diagram_type} Mermaid diagram.

Description: {description}

Requirements:
1. Use valid Mermaid {diagram_type} syntax
2. Include clear, descriptive labels
3. Keep it focused and readable
4. Output ONLY the Mermaid code

Start with the appropriate diagram declaration."""

        try:
            result = self.kilo_cli.run_autonomous(
                prompt=prompt,
                workspace=context.output_dir if context else None,
                mode="code",
                timeout=self.kilo_timeout,
                json_output=True,
                yolo=True
            )

            duration = (datetime.now() - start_time).total_seconds()
            mermaid_code = self._extract_mermaid(result.get("stdout", ""))

            return KiloTaskResult(
                task_type="generate_diagram",
                success=bool(mermaid_code),
                output=mermaid_code or "",
                error=None if mermaid_code else "Failed to extract Mermaid code",
                duration_seconds=duration
            )

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return KiloTaskResult(
                task_type="generate_diagram",
                success=False,
                output="",
                error=str(e),
                duration_seconds=duration
            )

    def is_available(self) -> bool:
        """Check if Kilo CLI is available."""
        return self._kilo_available

    def get_task_history(self) -> List[KiloTaskResult]:
        """Get history of executed tasks."""
        return self._task_history
