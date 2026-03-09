"""
Refinement Loop — main orchestrator for the evaluate -> fix -> re-evaluate cycle.

Follows the TraceWalker pattern: evaluate, fix highest-impact gaps,
check convergence, stop on target reached or stagnation.
"""

import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional

from . import CompletenessReport, RefinementResult
from .artifact_loader import ArtifactLoader
from .completeness_checker import CompletenessChecker
from .gap_classifier import classify_gaps
from .generator_invoker import GeneratorInvoker
from .refinement_report import generate_dry_run_report, generate_report

logger = logging.getLogger(__name__)


class RefinementLoop:
    """Main refinement loop orchestrator."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.max_iterations = self.config.get("max_iterations", 10)
        self.target_score = self.config.get("target_score", 0.85)
        self.stagnation_threshold = self.config.get("stagnation_threshold", 0.005)
        self.stagnation_patience = self.config.get("stagnation_patience", 3)
        self.max_llm_calls = self.config.get("max_llm_calls", 100)
        self.max_cost_usd = self.config.get("max_cost_usd", 10.0)
        self.max_auto_fixes = self.config.get("max_auto_fixes_per_iteration", 200)
        self.max_llm_fixes = self.config.get("max_llm_fixes_per_iteration", 30)
        self.max_gen_calls = self.config.get("max_generator_calls_per_iteration", 10)
        self.backup_originals = self.config.get("backup_originals", True)

    async def run(self, output_dir: str | Path) -> RefinementResult:
        """Run the full refinement loop on an output directory."""
        start_time = time.time()
        output_dir = Path(output_dir)
        result = RefinementResult()

        # Step 1: Load
        print(f"\n[Refinement] Loading artifacts from {output_dir}...")
        loader = ArtifactLoader(output_dir)
        bundle = loader.load_all()

        summary = bundle.summary()
        print(f"[Refinement] Loaded: {', '.join(f'{k}={v}' for k, v in summary.items() if v > 0)}")

        # Step 2: Initial evaluation
        checker = CompletenessChecker(self.config)
        before_report = checker.check_all(bundle)
        result.before_scores = before_report.scores
        result.before_overall = before_report.overall_score

        print(f"[Refinement] Initial score: {before_report.overall_score:.1%}")
        for rr in before_report.rule_results:
            status = "PASS" if rr.passed else "FAIL"
            print(f"   {rr.rule_name:25s} {rr.current_value:6.1%} / {rr.target_value} -> {rr.score:.1%} [{status}]")

        result.gaps_found = len(before_report.all_gaps)

        # Check if already passing
        if before_report.overall_score >= self.target_score:
            print(f"[Refinement] Already at target ({self.target_score:.0%}). No refinement needed.")
            result.after_scores = result.before_scores
            result.after_overall = result.before_overall
            result.gaps_remaining = result.gaps_found
            result.duration_seconds = time.time() - start_time
            self._save_report(output_dir, result, before_report, None)
            return result

        # Step 3: Refinement loop
        invoker = GeneratorInvoker(self.config)
        current_report = before_report
        consecutive_stagnant = 0

        # Build semantic index for RAG-assisted matching
        index_ok = await invoker.build_artifact_index(bundle)
        if index_ok:
            stats = invoker.matcher_stats()
            print(f"[Refinement] Semantic matching: enabled ({stats.get('index_size', 0)} items indexed)")
        else:
            print("[Refinement] Semantic matching: disabled (keyword matching only)")

        for iteration in range(1, self.max_iterations + 1):
            print(f"\n[Refinement] Iteration {iteration}/{self.max_iterations}")

            # Classify gaps
            classified = classify_gaps(current_report.all_gaps)
            print(f"   Gaps: {len(classified.auto_link)} auto_link, "
                  f"{len(classified.llm_extend)} llm_extend, "
                  f"{len(classified.generator)} generator, "
                  f"{len(classified.manual)} manual")

            if classified.fixable_count == 0:
                print("   No fixable gaps remaining.")
                break

            # Backup before modifying
            if self.backup_originals:
                self._backup(output_dir, iteration)

            # Apply fixes in order of cost
            fixed_auto = await invoker.apply_auto_link_fixes(
                classified.auto_link, bundle, max_fixes=self.max_auto_fixes
            )
            print(f"   Auto-link fixes: {fixed_auto}")

            fixed_llm = 0
            if classified.llm_extend and invoker.llm_calls < self.max_llm_calls:
                fixed_llm = await invoker.apply_llm_fixes(
                    classified.llm_extend, bundle, max_fixes=self.max_llm_fixes
                )
                print(f"   LLM fixes: {fixed_llm}")

            fixed_gen = 0
            if classified.generator and invoker.llm_calls < self.max_llm_calls:
                fixed_gen = await invoker.apply_generator_fixes(
                    classified.generator, bundle, max_calls=self.max_gen_calls
                )
                print(f"   Generator fixes: {fixed_gen}")

            total_fixed = fixed_auto + fixed_llm + fixed_gen
            result.gaps_fixed += total_fixed

            # Budget status
            if invoker.llm_calls > 0:
                print(f"   Budget: {invoker.llm_calls} LLM calls, ~${invoker.cost_usd:.3f}")

            # Save modified artifacts
            invoker.save_artifacts(bundle, output_dir)

            # Re-evaluate
            # Refresh derived lists before rebuilding indices
            if bundle.task_breakdown:
                bundle.tasks = bundle.task_breakdown.tasks

            # Rebuild indices after modifications
            bundle.test_by_id.clear()
            bundle.endpoint_by_key.clear()
            bundle.task_by_id.clear()
            loader._build_indices(bundle)

            new_report = checker.check_all(bundle)
            delta = new_report.overall_score - current_report.overall_score
            print(f"   Score: {current_report.overall_score:.1%} -> {new_report.overall_score:.1%} (delta {delta:+.1%})")

            result.iterations = iteration

            # Convergence check
            if new_report.overall_score >= self.target_score:
                print(f"   Target score {self.target_score:.0%} reached!")
                current_report = new_report
                break

            if abs(delta) < self.stagnation_threshold:
                consecutive_stagnant += 1
                if consecutive_stagnant >= self.stagnation_patience:
                    print(f"   Stagnant for {consecutive_stagnant} iterations. Stopping.")
                    current_report = new_report
                    break
            else:
                consecutive_stagnant = 0

            # Budget check
            if invoker.llm_calls >= self.max_llm_calls:
                print(f"   LLM call budget exhausted ({self.max_llm_calls}).")
                current_report = new_report
                break

            current_report = new_report

        # Step 4: Finalize
        result.after_scores = current_report.scores
        result.after_overall = current_report.overall_score
        result.gaps_remaining = len(current_report.all_gaps)
        result.fix_log = invoker.fix_log
        result.total_llm_calls = invoker.llm_calls
        result.total_cost_usd = invoker.cost_usd
        result.duration_seconds = time.time() - start_time

        self._save_report(output_dir, result, before_report, current_report)

        print(f"\n[Refinement] Complete: {result.before_overall:.1%} -> {result.after_overall:.1%}")
        print(f"   Gaps: {result.gaps_found} found, {result.gaps_fixed} fixed, {result.gaps_remaining} remaining")
        print(f"   Duration: {result.duration_seconds:.1f}s")

        # Semantic matcher stats
        m_stats = invoker.matcher_stats()
        if m_stats:
            print(f"   Semantic: {m_stats['embed_calls']} embed calls, "
                  f"{m_stats['cache_hits']} cache hits, ~${m_stats['cost_usd']:.4f}")

        return result

    async def evaluate_only(self, output_dir: str | Path) -> CompletenessReport:
        """Evaluate without fixing (dry-run mode)."""
        output_dir = Path(output_dir)
        print(f"\n[Refinement] Loading artifacts from {output_dir}...")
        loader = ArtifactLoader(output_dir)
        bundle = loader.load_all()

        summary = bundle.summary()
        print(f"[Refinement] Loaded: {', '.join(f'{k}={v}' for k, v in summary.items() if v > 0)}")

        checker = CompletenessChecker(self.config)
        report = checker.check_all(bundle)

        print(f"\n[Refinement] Overall Score: {report.overall_score:.1%}\n")
        for rr in report.rule_results:
            status = "PASS" if rr.passed else "FAIL"
            gaps_str = f" ({len(rr.gaps)} gaps)" if rr.gaps else ""
            # Format value based on whether it's a ratio or percentage
            if rr.target_value > 1.0:
                val_str = f"{rr.current_value:.1f}/{rr.target_value:.1f}"
            else:
                val_str = f"{rr.current_value:.0%}/{rr.target_value:.0%}"
            print(f"   {rr.rule_name:25s} {val_str:>12s} -> {rr.score:.0%} [{status}]{gaps_str}")

        # Save report
        report_md = generate_dry_run_report(report)
        quality_dir = output_dir / "quality"
        quality_dir.mkdir(parents=True, exist_ok=True)
        report_path = quality_dir / "completeness_report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_md)
        print(f"\n[Refinement] Report saved to {report_path}")

        return report

    def _backup(self, output_dir: Path, iteration: int):
        """Backup modified files before an iteration."""
        backup_dir = output_dir / ".backups" / f"iter_{iteration}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Backup files that might be modified
        files_to_backup = [
            "testing/test_documentation.md",
            "tasks/task_list.json",
            "_checkpoints/stage_5.json",
            "_checkpoints/stage_8.json",
        ]
        for rel_path in files_to_backup:
            src = output_dir / rel_path
            if src.exists():
                dst = backup_dir / rel_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

    def _save_report(
        self,
        output_dir: Path,
        result: RefinementResult,
        before_report: CompletenessReport,
        after_report: Optional[CompletenessReport],
    ):
        """Save the refinement report to the output directory."""
        report_md = generate_report(result, before_report, after_report)
        quality_dir = output_dir / "quality"
        quality_dir.mkdir(parents=True, exist_ok=True)
        report_path = quality_dir / "refinement_report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_md)
        logger.info("Refinement report saved to %s", report_path)
