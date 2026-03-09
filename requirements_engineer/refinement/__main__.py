"""
CLI entry point for the post-generation refinement loop.

Usage:
    python -m requirements_engineer.refinement <output_dir>
    python -m requirements_engineer.refinement <output_dir> --dry-run
    python -m requirements_engineer.refinement <output_dir> --max-iterations 3 --target-score 0.90
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Load .env before anything else (OPENAI_API_KEY, OPENROUTER_API_KEY)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .refinement_loop import RefinementLoop


def main():
    parser = argparse.ArgumentParser(
        description="Post-generation evaluation & refinement loop for RE pipeline output"
    )
    parser.add_argument(
        "output_dir",
        help="Path to pipeline output directory (e.g. enterprise_output/project_20260211_025459)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Evaluate only — produce report without applying fixes",
    )
    parser.add_argument(
        "--max-iterations", type=int, default=10,
        help="Maximum refinement iterations (default: 10)",
    )
    parser.add_argument(
        "--target-score", type=float, default=0.85,
        help="Stop when overall score reaches this threshold (default: 0.85)",
    )
    parser.add_argument(
        "--max-llm-calls", type=int, default=100,
        help="Maximum LLM API calls budget (default: 100)",
    )
    parser.add_argument(
        "--max-cost", type=float, default=10.0,
        help="Maximum cost budget in USD (default: 10.0)",
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to re_config.yaml for threshold overrides",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if not output_dir.exists():
        print(f"Error: Output directory does not exist: {output_dir}")
        sys.exit(1)

    # Build config from args
    config = {
        "max_iterations": args.max_iterations,
        "target_score": args.target_score,
        "max_llm_calls": args.max_llm_calls,
        "max_cost_usd": args.max_cost,
    }

    # Load YAML config if provided
    if args.config:
        try:
            from omegaconf import OmegaConf
            yaml_config = OmegaConf.load(args.config)
            refinement_config = OmegaConf.to_container(
                yaml_config.get("refinement", {}), resolve=True
            )
            # CLI args override YAML
            for key, val in config.items():
                refinement_config[key] = val
            config = refinement_config
        except Exception as e:
            print(f"Warning: Could not load config from {args.config}: {e}")

    loop = RefinementLoop(config=config)

    if args.dry_run:
        report = asyncio.run(loop.evaluate_only(output_dir))
        print(f"\nOverall completeness: {report.overall_score:.1%}")
        total_gaps = len(report.all_gaps)
        if total_gaps > 0:
            print(f"Run without --dry-run to fix {total_gaps} gaps automatically.")
    else:
        result = asyncio.run(loop.run(output_dir))
        print(f"\nFinal score: {result.before_overall:.1%} -> {result.after_overall:.1%}")
        print(f"Fixed {result.gaps_fixed}/{result.gaps_found} gaps in {result.iterations} iterations")


if __name__ == "__main__":
    main()
