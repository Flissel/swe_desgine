"""
OpenAI Fine-Tuning Format Exporter.

Exports training data in the exact format required by OpenAI's
Fine-Tuning API.

Format specification:
- messages: List of message objects with role and content
- tools: Optional list of tool definitions (for function calling)
- tool_choice: Optional tool choice specification

Usage:
    from requirements_engineer.training.exporters import OpenAIFormatExporter

    exporter = OpenAIFormatExporter()
    exporter.export(samples, "fine_tuning.jsonl")

    # Validate format
    errors = exporter.validate(samples)
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple
from dataclasses import asdict

from ..schemas import TrainingSample, LLMCallRecord


class OpenAIFormatExporter:
    """
    Exporter for OpenAI Fine-Tuning format.

    Ensures output conforms to OpenAI's requirements:
    - messages array with role/content
    - Optional tools array
    - Proper handling of tool_calls in assistant messages
    - tool messages for tool responses
    """

    # Supported roles
    VALID_ROLES = {"system", "user", "assistant", "tool"}

    def __init__(self, validate: bool = True):
        """
        Initialize exporter.

        Args:
            validate: Whether to validate format before export
        """
        self.validate_format = validate

    def export(
        self,
        samples: List[TrainingSample],
        output_path: Union[str, Path],
        skip_invalid: bool = True
    ) -> Tuple[int, int]:
        """
        Export samples to OpenAI format.

        Args:
            samples: Training samples to export
            output_path: Output file path
            skip_invalid: Skip invalid samples instead of raising

        Returns:
            Tuple of (exported_count, skipped_count)
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        exported = 0
        skipped = 0

        with open(output_path, "w", encoding="utf-8") as f:
            for sample in samples:
                formatted = self.format_sample(sample)

                if self.validate_format:
                    errors = self._validate_sample(formatted)
                    if errors:
                        if skip_invalid:
                            skipped += 1
                            continue
                        else:
                            raise ValueError(f"Invalid sample: {errors}")

                f.write(json.dumps(formatted, default=str) + "\n")
                exported += 1

        return exported, skipped

    def format_sample(self, sample: TrainingSample) -> Dict[str, Any]:
        """
        Format a single sample for OpenAI.

        Args:
            sample: TrainingSample to format

        Returns:
            Formatted dictionary
        """
        result: Dict[str, Any] = {
            "messages": self._format_messages(sample.messages)
        }

        # Add tools if present
        if sample.tools:
            result["tools"] = self._format_tools(sample.tools)

        # Add tool_choice if specified
        if sample.tool_choice:
            result["tool_choice"] = sample.tool_choice

        return result

    def format_llm_call(self, llm_call: LLMCallRecord) -> Dict[str, Any]:
        """
        Format an LLM call record directly.

        Args:
            llm_call: LLMCallRecord to format

        Returns:
            Formatted dictionary
        """
        messages = []

        # System message
        if llm_call.system_message:
            messages.append({
                "role": "system",
                "content": llm_call.system_message
            })

        # Conversation history
        for msg in llm_call.conversation_history:
            messages.append(self._format_message(msg))

        # User message
        if llm_call.user_message:
            messages.append({
                "role": "user",
                "content": llm_call.user_message
            })

        # Assistant response
        if llm_call.assistant_response or llm_call.has_tool_calls:
            assistant_msg: Dict[str, Any] = {"role": "assistant"}

            if llm_call.assistant_response:
                assistant_msg["content"] = llm_call.assistant_response

            if llm_call.has_tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.tool_name,
                            "arguments": tc.arguments_raw
                        }
                    }
                    for tc in llm_call.tool_calls
                ]

            messages.append(assistant_msg)

        # Tool responses
        for tc in llm_call.tool_calls:
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tc.result_raw or ""
            })

        result: Dict[str, Any] = {"messages": messages}

        if llm_call.function_spec:
            result["tools"] = [{
                "type": "function",
                "function": llm_call.function_spec
            }]

        return result

    def _format_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format messages array."""
        return [self._format_message(msg) for msg in messages]

    def _format_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Format a single message."""
        role = message.get("role", "user")
        formatted: Dict[str, Any] = {"role": role}

        # Content
        if "content" in message:
            formatted["content"] = message["content"]

        # Tool calls (assistant only)
        if role == "assistant" and "tool_calls" in message:
            formatted["tool_calls"] = message["tool_calls"]

        # Tool call ID (tool role only)
        if role == "tool" and "tool_call_id" in message:
            formatted["tool_call_id"] = message["tool_call_id"]

        # Name (optional)
        if "name" in message:
            formatted["name"] = message["name"]

        return formatted

    def _format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format tools array."""
        formatted = []
        for tool in tools:
            if tool.get("type") == "function" and "function" in tool:
                formatted.append({
                    "type": "function",
                    "function": self._format_function(tool["function"])
                })
            else:
                formatted.append(tool)
        return formatted

    def _format_function(self, function: Dict[str, Any]) -> Dict[str, Any]:
        """Format function definition."""
        return {
            "name": function.get("name", ""),
            "description": function.get("description", ""),
            "parameters": function.get("parameters", {
                "type": "object",
                "properties": {},
                "required": []
            })
        }

    def _validate_sample(self, sample: Dict[str, Any]) -> List[str]:
        """
        Validate a formatted sample.

        Args:
            sample: Formatted sample dict

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Must have messages
        if "messages" not in sample:
            errors.append("Missing 'messages' field")
            return errors

        messages = sample["messages"]

        if not isinstance(messages, list):
            errors.append("'messages' must be a list")
            return errors

        if len(messages) == 0:
            errors.append("'messages' must not be empty")
            return errors

        # Validate each message
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                errors.append(f"Message {i}: must be a dict")
                continue

            role = msg.get("role")
            if role not in self.VALID_ROLES:
                errors.append(f"Message {i}: invalid role '{role}'")

            # Content validation
            if role in ("system", "user"):
                if "content" not in msg:
                    errors.append(f"Message {i}: {role} message must have 'content'")
                elif not isinstance(msg["content"], str):
                    errors.append(f"Message {i}: 'content' must be a string")

            if role == "tool":
                if "tool_call_id" not in msg:
                    errors.append(f"Message {i}: tool message must have 'tool_call_id'")
                if "content" not in msg:
                    errors.append(f"Message {i}: tool message must have 'content'")

            # Tool calls validation
            if role == "assistant" and "tool_calls" in msg:
                tool_calls = msg["tool_calls"]
                if not isinstance(tool_calls, list):
                    errors.append(f"Message {i}: 'tool_calls' must be a list")
                else:
                    for j, tc in enumerate(tool_calls):
                        if "id" not in tc:
                            errors.append(f"Message {i}, tool_call {j}: missing 'id'")
                        if "type" not in tc:
                            errors.append(f"Message {i}, tool_call {j}: missing 'type'")
                        if "function" not in tc:
                            errors.append(f"Message {i}, tool_call {j}: missing 'function'")
                        elif not isinstance(tc["function"], dict):
                            errors.append(f"Message {i}, tool_call {j}: 'function' must be dict")
                        else:
                            if "name" not in tc["function"]:
                                errors.append(f"Message {i}, tool_call {j}: function missing 'name'")
                            if "arguments" not in tc["function"]:
                                errors.append(f"Message {i}, tool_call {j}: function missing 'arguments'")

        # Validate tools if present
        if "tools" in sample:
            tools = sample["tools"]
            if not isinstance(tools, list):
                errors.append("'tools' must be a list")
            else:
                for i, tool in enumerate(tools):
                    if not isinstance(tool, dict):
                        errors.append(f"Tool {i}: must be a dict")
                        continue
                    if tool.get("type") != "function":
                        errors.append(f"Tool {i}: type must be 'function'")
                    if "function" not in tool:
                        errors.append(f"Tool {i}: missing 'function'")
                    elif "name" not in tool["function"]:
                        errors.append(f"Tool {i}: function missing 'name'")

        return errors

    def validate(self, samples: List[TrainingSample]) -> Dict[int, List[str]]:
        """
        Validate multiple samples.

        Args:
            samples: Samples to validate

        Returns:
            Dict mapping sample index to list of errors (only for invalid samples)
        """
        errors = {}
        for i, sample in enumerate(samples):
            formatted = self.format_sample(sample)
            sample_errors = self._validate_sample(formatted)
            if sample_errors:
                errors[i] = sample_errors
        return errors

    def validate_file(self, input_path: Union[str, Path]) -> Tuple[int, Dict[int, List[str]]]:
        """
        Validate a JSONL file.

        Args:
            input_path: Path to JSONL file

        Returns:
            Tuple of (total_count, errors_dict)
        """
        errors = {}
        count = 0

        with open(input_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                count += 1
                line = line.strip()
                if not line:
                    continue

                try:
                    sample = json.loads(line)
                    sample_errors = self._validate_sample(sample)
                    if sample_errors:
                        errors[i] = sample_errors
                except json.JSONDecodeError as e:
                    errors[i] = [f"JSON parse error: {e}"]

        return count, errors
