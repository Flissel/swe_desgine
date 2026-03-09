"""
JSONL Exporter for Training Data.

Exports training samples to JSONL format with various options:
- Raw JSONL (one JSON object per line)
- Filtered by quality/stage
- Streaming export for large datasets

Usage:
    from requirements_engineer.training.exporters import JSONLExporter

    exporter = JSONLExporter()
    exporter.export(samples, "output.jsonl")
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Iterator, Union
from dataclasses import asdict

from ..schemas import TrainingSample, LLMCallRecord, ToolCallRecord, ErrorContext


class JSONLExporter:
    """
    JSONL Exporter for training data.

    Supports exporting:
    - TrainingSample objects
    - LLMCallRecord objects
    - ToolCallRecord objects
    - ErrorContext objects
    - Raw dictionaries
    """

    def __init__(self, indent: Optional[int] = None):
        """
        Initialize exporter.

        Args:
            indent: JSON indent level (None for compact, 2 for readable)
        """
        self.indent = indent

    def export(
        self,
        data: List[Any],
        output_path: Union[str, Path],
        format_fn: Optional[callable] = None
    ) -> int:
        """
        Export data to JSONL file.

        Args:
            data: List of objects to export
            output_path: Output file path
            format_fn: Optional function to format each object

        Returns:
            Number of records exported
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        count = 0
        with open(output_path, "w", encoding="utf-8") as f:
            for item in data:
                record = self._to_dict(item)
                if format_fn:
                    record = format_fn(record)
                f.write(json.dumps(record, default=str, indent=self.indent) + "\n")
                count += 1

        return count

    def export_samples(
        self,
        samples: List[TrainingSample],
        output_path: Union[str, Path],
        include_metadata: bool = True
    ) -> int:
        """
        Export training samples to JSONL.

        Args:
            samples: Training samples to export
            output_path: Output file path
            include_metadata: Whether to include metadata fields

        Returns:
            Number of samples exported
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        count = 0
        with open(output_path, "w", encoding="utf-8") as f:
            for sample in samples:
                if include_metadata:
                    record = sample.to_full_format()
                else:
                    record = sample.to_openai_format()
                f.write(json.dumps(record, default=str) + "\n")
                count += 1

        return count

    def export_streaming(
        self,
        data_iterator: Iterator[Any],
        output_path: Union[str, Path],
        format_fn: Optional[callable] = None,
        batch_size: int = 1000
    ) -> int:
        """
        Export data using streaming for memory efficiency.

        Args:
            data_iterator: Iterator yielding objects to export
            output_path: Output file path
            format_fn: Optional format function
            batch_size: Flush every N records

        Returns:
            Number of records exported
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        count = 0
        with open(output_path, "w", encoding="utf-8") as f:
            for item in data_iterator:
                record = self._to_dict(item)
                if format_fn:
                    record = format_fn(record)
                f.write(json.dumps(record, default=str) + "\n")
                count += 1

                if count % batch_size == 0:
                    f.flush()

        return count

    def export_filtered(
        self,
        samples: List[TrainingSample],
        output_path: Union[str, Path],
        min_quality: float = 0.0,
        stages: Optional[List[int]] = None,
        include_tool_calls: Optional[bool] = None,
        max_samples: Optional[int] = None,
        include_metadata: bool = False
    ) -> int:
        """
        Export filtered training samples.

        Args:
            samples: Training samples
            output_path: Output file path
            min_quality: Minimum quality score
            stages: Filter by stage numbers
            include_tool_calls: Filter by tool call presence
            max_samples: Maximum samples to export
            include_metadata: Include full metadata

        Returns:
            Number of samples exported
        """
        filtered = samples

        if min_quality > 0:
            filtered = [s for s in filtered if s.quality_score >= min_quality]

        if stages is not None:
            filtered = [
                s for s in filtered
                if s.metadata.get("stage_number") in stages
            ]

        if include_tool_calls is not None:
            if include_tool_calls:
                filtered = [s for s in filtered if "includes_tool_calls" in s.quality_tags]
            else:
                filtered = [s for s in filtered if "includes_tool_calls" not in s.quality_tags]

        if max_samples is not None:
            filtered = filtered[:max_samples]

        return self.export_samples(filtered, output_path, include_metadata)

    def _to_dict(self, item: Any) -> Dict[str, Any]:
        """Convert item to dictionary."""
        if isinstance(item, dict):
            return item
        elif hasattr(item, "to_dict"):
            return item.to_dict()
        elif hasattr(item, "__dataclass_fields__"):
            return asdict(item)
        else:
            return {"value": item}


class JSONLReader:
    """
    JSONL Reader for loading training data.

    Supports:
    - Full file loading
    - Streaming/iterator loading
    - Filtering during load
    """

    @staticmethod
    def read(
        input_path: Union[str, Path],
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Read JSONL file into list.

        Args:
            input_path: Input file path
            limit: Maximum records to read

        Returns:
            List of dictionaries
        """
        records = []
        with open(input_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if limit and i >= limit:
                    break
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    @staticmethod
    def read_streaming(
        input_path: Union[str, Path]
    ) -> Iterator[Dict[str, Any]]:
        """
        Read JSONL file as iterator for memory efficiency.

        Args:
            input_path: Input file path

        Yields:
            Dictionary for each line
        """
        with open(input_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    @staticmethod
    def read_as_samples(
        input_path: Union[str, Path],
        limit: Optional[int] = None
    ) -> List[TrainingSample]:
        """
        Read JSONL file as TrainingSample objects.

        Args:
            input_path: Input file path
            limit: Maximum samples to read

        Returns:
            List of TrainingSample objects
        """
        samples = []
        for record in JSONLReader.read_streaming(input_path):
            if limit and len(samples) >= limit:
                break

            # Handle both OpenAI format and full format
            if "messages" in record:
                sample = TrainingSample(
                    messages=record.get("messages", []),
                    tools=record.get("tools", []),
                    metadata=record.get("metadata", {}),
                    quality_score=record.get("quality_score", 0.0),
                    quality_tags=record.get("quality_tags", [])
                )
                if "id" in record:
                    sample.id = record["id"]
                samples.append(sample)

        return samples

    @staticmethod
    def count_lines(input_path: Union[str, Path]) -> int:
        """Count lines in JSONL file."""
        count = 0
        with open(input_path, "r", encoding="utf-8") as f:
            for _ in f:
                count += 1
        return count
