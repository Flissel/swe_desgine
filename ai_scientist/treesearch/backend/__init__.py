import json
import logging
from typing import Optional

from . import backend_anthropic, backend_openai
from .utils import FunctionSpec, OutputType, PromptType, compile_prompt_to_md

logger = logging.getLogger(__name__)

# Training data collection flag - can be disabled globally
TRAINING_COLLECTION_ENABLED = True


def _get_training_collector():
    """Get training data collector if available and enabled."""
    if not TRAINING_COLLECTION_ENABLED:
        return None
    try:
        from requirements_engineer.training.collector import TrainingDataCollector
        return TrainingDataCollector.get_instance()
    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"Could not get training collector: {e}")
        return None


def get_ai_client(model: str, **model_kwargs):
    """
    Get the appropriate AI client based on the model string.

    Args:
        model (str): string identifier for the model to use (e.g. "gpt-4-turbo")
        **model_kwargs: Additional keyword arguments for model configuration.
    Returns:
        An instance of the appropriate AI client.
    """
    import os

    # OpenRouter models use provider/model format (e.g. google/gemini-3-flash-preview)
    # Route through OpenAI-compatible OpenRouter API when key is available
    if model.startswith("openrouter/") or model.startswith("ollama/"):
        return backend_openai.get_ai_client(model=model, **model_kwargs)
    elif "/" in model and os.environ.get("OPENROUTER_API_KEY"):
        # Provider/model format with OpenRouter key → route through OpenRouter
        return backend_openai.get_ai_client(model=model, **model_kwargs)
    elif "claude-" in model:
        return backend_anthropic.get_ai_client(model=model, **model_kwargs)
    else:
        return backend_openai.get_ai_client(model=model, **model_kwargs)

def query(
    system_message: PromptType | None,
    user_message: PromptType | None,
    model: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
    func_spec: FunctionSpec | None = None,
    # Training data context (optional)
    stage: str = "",
    stage_number: int = 0,
    iteration: int = 0,
    component: str = "",
    node_id: str = "",
    collect_training_data: bool = True,
    **model_kwargs,
) -> OutputType:
    """
    General LLM query for various backends with a single system and user message.
    Supports function calling for some backends.

    Args:
        system_message (PromptType | None): Uncompiled system message (will generate a message following the OpenAI/Anthropic format)
        user_message (PromptType | None): Uncompiled user message (will generate a message following the OpenAI/Anthropic format)
        model (str): string identifier for the model to use (e.g. "gpt-4-turbo")
        temperature (float | None, optional): Temperature to sample at. Defaults to the model-specific default.
        max_tokens (int | None, optional): Maximum number of tokens to generate. Defaults to the model-specific max tokens.
        func_spec (FunctionSpec | None, optional): Optional FunctionSpec object defining a function call. If given, the return value will be a dict.
        stage (str, optional): Stage name for training data context (e.g., "discovery", "analysis").
        stage_number (int, optional): Stage number (1-5) for training data context.
        iteration (int, optional): Iteration number for training data context.
        component (str, optional): Component name for training data context (e.g., "draft_engine").
        node_id (str, optional): Node ID for training data context.
        collect_training_data (bool, optional): Whether to collect training data for this call. Defaults to True.

    Returns:
        OutputType: A string completion if func_spec is None, otherwise a dict with the function call details.
    """
    # Store original messages for training data
    original_system_message = system_message
    original_user_message = user_message

    model_kwargs = model_kwargs | {
        "model": model,
        "temperature": temperature,
    }

    # Handle models with beta limitations
    # ref: https://platform.openai.com/docs/guides/reasoning/beta-limitations
    if model.startswith("o1"):
        if system_message and user_message is None:
            user_message = system_message
        elif system_message is None and user_message:
            pass
        elif system_message and user_message:
            system_message["Main Instructions"] = {}
            system_message["Main Instructions"] |= user_message
            user_message = system_message
        system_message = None
        # model_kwargs["temperature"] = 0.5
        model_kwargs["reasoning_effort"] = "high"
        model_kwargs["max_completion_tokens"] = 100000  # max_tokens
        # remove 'temperature' from model_kwargs
        model_kwargs.pop("temperature", None)
    else:
        model_kwargs["max_tokens"] = max_tokens

    # OpenRouter models use OpenAI-compatible API
    import os
    if model.startswith("openrouter/") or model.startswith("ollama/"):
        query_func = backend_openai.query
    elif "/" in model and os.environ.get("OPENROUTER_API_KEY"):
        # Provider/model format (e.g. anthropic/claude-opus-4.6) → OpenRouter
        query_func = backend_openai.query
    elif "claude-" in model:
        query_func = backend_anthropic.query
    else:
        query_func = backend_openai.query

    # Execute query
    output, req_time, in_tok_count, out_tok_count, info = query_func(
        system_message=compile_prompt_to_md(system_message) if system_message else None,
        user_message=compile_prompt_to_md(user_message) if user_message else None,
        func_spec=func_spec,
        **model_kwargs,
    )

    # Collect training data if enabled
    if collect_training_data:
        collector = _get_training_collector()
        if collector:
            try:
                # Compile messages for training data
                system_msg_str = compile_prompt_to_md(original_system_message) if original_system_message else ""
                user_msg_str = compile_prompt_to_md(original_user_message) if original_user_message else ""

                # Format response
                if isinstance(output, str):
                    response_str = output
                elif isinstance(output, dict):
                    response_str = json.dumps(output, default=str)
                else:
                    response_str = str(output)

                # Record the LLM call
                collector.record_llm_call(
                    system_message=system_msg_str,
                    user_message=user_msg_str,
                    response=response_str,
                    model=model,
                    stage=stage,
                    stage_number=stage_number,
                    iteration=iteration,
                    component=component,
                    node_id=node_id,
                    input_tokens=in_tok_count,
                    output_tokens=out_tok_count,
                    latency_ms=int(req_time * 1000),
                    temperature=temperature or 0.7,
                    max_tokens=max_tokens or 0,
                    function_spec=func_spec.as_openai_tool_dict if func_spec else None,
                    function_result=output if func_spec else None,
                    success=True
                )
            except Exception as e:
                logger.debug(f"Failed to record training data: {e}")

    return output


def query_with_full_response(
    system_message: PromptType | None,
    user_message: PromptType | None,
    model: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
    func_spec: FunctionSpec | None = None,
    **model_kwargs,
) -> tuple:
    """
    Query with full response including timing and token counts.

    Returns:
        Tuple of (output, req_time, in_tok_count, out_tok_count, info)
    """
    model_kwargs = model_kwargs | {
        "model": model,
        "temperature": temperature,
    }

    if model.startswith("o1"):
        if system_message and user_message is None:
            user_message = system_message
        elif system_message is None and user_message:
            pass
        elif system_message and user_message:
            system_message["Main Instructions"] = {}
            system_message["Main Instructions"] |= user_message
            user_message = system_message
        system_message = None
        model_kwargs["reasoning_effort"] = "high"
        model_kwargs["max_completion_tokens"] = 100000
        model_kwargs.pop("temperature", None)
    else:
        model_kwargs["max_tokens"] = max_tokens

    if model.startswith("openrouter/") or model.startswith("ollama/"):
        query_func = backend_openai.query
    elif "claude-" in model:
        query_func = backend_anthropic.query
    else:
        query_func = backend_openai.query

    return query_func(
        system_message=compile_prompt_to_md(system_message) if system_message else None,
        user_message=compile_prompt_to_md(user_message) if user_message else None,
        func_spec=func_spec,
        **model_kwargs,
    )
