"""
Token Manager - Manages context size and chunking for LLM calls.

Keeps token usage around a target (default 100k) by:
1. Estimating token counts for text
2. Chunking requirements into batches
3. Aggregating results from batches
"""

import logging
import re
from typing import List, Dict, Any, Tuple, Generator
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TokenBudget:
    """Token budget configuration."""
    max_context: int = 100000  # Target max context tokens
    max_output: int = 4000     # Max output tokens per call
    system_prompt_reserve: int = 2000  # Reserve for system prompt
    safety_margin: float = 0.85  # Use only 85% of budget for safety

    @property
    def effective_input_budget(self) -> int:
        """Available tokens for input content."""
        return int((self.max_context - self.max_output - self.system_prompt_reserve) * self.safety_margin)


class TokenEstimator:
    """Estimates token counts for text."""

    # Average chars per token (conservative estimate)
    CHARS_PER_TOKEN = 3.5

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """Estimate token count for text."""
        if not text:
            return 0
        return int(len(text) / cls.CHARS_PER_TOKEN)

    @classmethod
    def estimate_json_tokens(cls, obj: Any) -> int:
        """Estimate tokens for JSON-serializable object."""
        import json
        try:
            text = json.dumps(obj, ensure_ascii=False)
            return cls.estimate_tokens(text)
        except (TypeError, ValueError) as e:
            logger.debug(f"Failed to serialize object for token estimation: {e}")
            return 0

    @classmethod
    def estimate_requirement_tokens(cls, req: Any) -> int:
        """Estimate tokens for a requirement object."""
        # Estimate based on key fields
        text_parts = [
            getattr(req, 'requirement_id', ''),
            getattr(req, 'title', ''),
            getattr(req, 'description', ''),
            getattr(req, 'type', ''),
            getattr(req, 'priority', ''),
        ]
        total_text = ' '.join(str(p) for p in text_parts if p)
        return cls.estimate_tokens(total_text)


class RequirementChunker:
    """Chunks requirements into batches that fit within token budget."""

    def __init__(self, budget: TokenBudget = None):
        self.budget = budget or TokenBudget()
        self.estimator = TokenEstimator()

    def chunk_requirements(
        self,
        requirements: List[Any],
        prompt_template_tokens: int = 500
    ) -> Generator[List[Any], None, None]:
        """
        Yield batches of requirements that fit within token budget.

        Args:
            requirements: List of requirement objects
            prompt_template_tokens: Estimated tokens for prompt template

        Yields:
            Batches of requirements
        """
        available_tokens = self.budget.effective_input_budget - prompt_template_tokens

        current_batch = []
        current_tokens = 0

        for req in requirements:
            req_tokens = self.estimator.estimate_requirement_tokens(req)

            # If single requirement exceeds budget, yield it alone (will be summarized)
            if req_tokens > available_tokens:
                if current_batch:
                    yield current_batch
                    current_batch = []
                    current_tokens = 0
                yield [req]
                continue

            # Check if adding this requirement exceeds budget
            if current_tokens + req_tokens > available_tokens:
                yield current_batch
                current_batch = [req]
                current_tokens = req_tokens
            else:
                current_batch.append(req)
                current_tokens += req_tokens

        # Yield remaining batch
        if current_batch:
            yield current_batch

    def get_batch_info(self, requirements: List[Any]) -> Dict[str, Any]:
        """Get information about how requirements will be batched."""
        batches = list(self.chunk_requirements(requirements))
        return {
            "total_requirements": len(requirements),
            "num_batches": len(batches),
            "batch_sizes": [len(b) for b in batches],
            "estimated_tokens_per_batch": [
                sum(self.estimator.estimate_requirement_tokens(r) for r in b)
                for b in batches
            ]
        }


class ResultAggregator:
    """Aggregates results from multiple batches."""

    @staticmethod
    def aggregate_endpoints(batch_results: List[List[Dict]]) -> List[Dict]:
        """Aggregate API endpoints from multiple batches."""
        all_endpoints = []
        seen_paths = set()

        for batch in batch_results:
            for endpoint in batch:
                # Deduplicate by path+method
                key = f"{endpoint.get('method', '')}:{endpoint.get('path', '')}"
                if key not in seen_paths:
                    seen_paths.add(key)
                    all_endpoints.append(endpoint)

        return all_endpoints

    @staticmethod
    def aggregate_entities(batch_results: List[List[Dict]]) -> List[Dict]:
        """Aggregate data dictionary entities from multiple batches."""
        all_entities = []
        seen_names = set()

        for batch in batch_results:
            for entity in batch:
                name = entity.get('name', '')
                if name and name not in seen_names:
                    seen_names.add(name)
                    all_entities.append(entity)

        return all_entities

    @staticmethod
    def aggregate_user_stories(batch_results: List[List[Dict]]) -> List[Dict]:
        """Aggregate user stories from multiple batches."""
        all_stories = []
        seen_ids = set()

        for batch in batch_results:
            for story in batch:
                story_id = story.get('id', '')
                if story_id and story_id not in seen_ids:
                    seen_ids.add(story_id)
                    all_stories.append(story)

        return all_stories

    @staticmethod
    def merge_json_responses(responses: List[Dict], key: str) -> Dict:
        """
        Merge multiple JSON responses that have a common array key.

        Example: merge [{"endpoints": [...]}, {"endpoints": [...]}]
        """
        merged = {key: []}

        for response in responses:
            if key in response and isinstance(response[key], list):
                merged[key].extend(response[key])

        return merged


class ContextSlicer:
    """Slices large text content to fit within token budget."""

    def __init__(self, max_tokens: int = 50000):
        self.max_tokens = max_tokens
        self.estimator = TokenEstimator()

    def slice_text(self, text: str, overlap_chars: int = 200) -> Generator[str, None, None]:
        """
        Slice text into chunks that fit within token budget.

        Args:
            text: Text to slice
            overlap_chars: Characters to overlap between chunks

        Yields:
            Text chunks
        """
        max_chars = int(self.max_tokens * TokenEstimator.CHARS_PER_TOKEN)

        if len(text) <= max_chars:
            yield text
            return

        start = 0
        while start < len(text):
            end = start + max_chars

            # Try to break at sentence boundary
            if end < len(text):
                # Look for sentence end within last 500 chars
                search_start = max(end - 500, start)
                last_period = text.rfind('. ', search_start, end)
                if last_period > start:
                    end = last_period + 1

            yield text[start:end]
            start = end - overlap_chars if end < len(text) else end

    def summarize_if_too_large(
        self,
        text: str,
        max_tokens: int = None,
        summary_ratio: float = 0.3
    ) -> Tuple[str, bool]:
        """
        Return text as-is if within budget, or a truncated version.

        Returns:
            Tuple of (text, was_truncated)
        """
        max_tokens = max_tokens or self.max_tokens
        estimated = self.estimator.estimate_tokens(text)

        if estimated <= max_tokens:
            return text, False

        # Truncate to fit
        target_chars = int(max_tokens * TokenEstimator.CHARS_PER_TOKEN * summary_ratio)
        truncated = text[:target_chars]

        # Try to end at sentence
        last_period = truncated.rfind('. ')
        if last_period > target_chars * 0.5:
            truncated = truncated[:last_period + 1]

        truncated += "\n\n[Content truncated to fit token budget]"
        return truncated, True


# Convenience functions
def estimate_tokens(text: str) -> int:
    """Quick token estimation."""
    return TokenEstimator.estimate_tokens(text)


def chunk_for_processing(
    items: List[Any],
    max_tokens: int = 80000,
    item_token_fn = None
) -> Generator[List[Any], None, None]:
    """
    Generic chunking function for any list of items.

    Args:
        items: Items to chunk
        max_tokens: Max tokens per chunk
        item_token_fn: Function to estimate tokens for an item (default: str length / 3.5)

    Yields:
        Batches of items
    """
    if item_token_fn is None:
        item_token_fn = lambda x: int(len(str(x)) / 3.5)

    current_batch = []
    current_tokens = 0

    for item in items:
        item_tokens = item_token_fn(item)

        if current_tokens + item_tokens > max_tokens and current_batch:
            yield current_batch
            current_batch = []
            current_tokens = 0

        current_batch.append(item)
        current_tokens += item_tokens

    if current_batch:
        yield current_batch
