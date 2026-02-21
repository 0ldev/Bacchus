"""
Chat inference functions for Bacchus.

Handles token estimation, context management, and prompt construction.
Actual model inference is handled by model_manager.py (not covered by unit tests).
"""

from typing import Any, Dict, List, Optional

# Default response buffer (tokens reserved for model output)
DEFAULT_RESPONSE_BUFFER = 512


def estimate_tokens(text: str) -> int:
    """
    Estimate the number of tokens in a text string.

    Uses a conservative estimate of ~4 characters per token.
    This works reasonably well for English and Portuguese.

    Args:
        text: The text to estimate tokens for

    Returns:
        Estimated number of tokens
    """
    if not text:
        return 0

    # Conservative estimate: ~4 characters per token
    return max(1, len(text) // 4)


def calculate_context_size(
    messages: List[Dict[str, Any]],
    system_message: str = "",
    rag_context: Optional[str] = None
) -> int:
    """
    Calculate total context size in tokens.

    Args:
        messages: List of conversation messages
        system_message: System prompt text
        rag_context: Optional RAG context text

    Returns:
        Total estimated tokens
    """
    total = 0

    # System message tokens
    if system_message:
        total += estimate_tokens(system_message)

    # RAG context tokens
    if rag_context:
        total += estimate_tokens(rag_context)

    # Message tokens
    for msg in messages:
        content = msg.get("content", "")
        total += estimate_tokens(content)
        # Add small overhead for role markers
        total += 4  # Approximate overhead per message

    return total


def trim_context_fifo(
    messages: List[Dict[str, Any]],
    max_tokens: int,
    system_tokens: int,
    rag_tokens: int,
    response_buffer: int = DEFAULT_RESPONSE_BUFFER
) -> List[Dict[str, Any]]:
    """
    Trim messages using FIFO strategy to fit within token limit.

    Removes oldest message pairs (user + assistant) first.
    Always keeps at least the newest message pair.

    Args:
        messages: List of conversation messages
        max_tokens: Model's maximum context window
        system_tokens: Tokens used by system message
        rag_tokens: Tokens used by RAG context
        response_buffer: Tokens reserved for model response

    Returns:
        Trimmed list of messages that fits within limit
    """
    if not messages:
        return []

    # Calculate available tokens for conversation history
    available = max_tokens - system_tokens - rag_tokens - response_buffer

    if available <= 0:
        # No room for history, return at least newest messages
        return messages[-2:] if len(messages) >= 2 else messages

    # Calculate tokens for each message
    message_tokens = [estimate_tokens(m.get("content", "")) + 4 for m in messages]

    # Try to fit as many messages as possible, keeping newest
    total_tokens = sum(message_tokens)

    if total_tokens <= available:
        # All messages fit
        return messages

    # Remove oldest pairs until we fit
    result = list(messages)
    result_tokens = list(message_tokens)

    while len(result) > 2 and sum(result_tokens) > available:
        # Remove oldest pair (first 2 messages)
        result = result[2:]
        result_tokens = result_tokens[2:]

    return result


def construct_prompt(
    messages: List[Dict[str, Any]],
    system_message: str,
    rag_context: Optional[str] = None,
    document_name: Optional[str] = None,
    model_folder: Optional[str] = None
) -> str:
    """
    Construct the full prompt to send to the model.

    Different models require different chat templates:
    - Phi-3/Phi-3.5: <|system|>...<|end|><|user|>...<|end|><|assistant|>
    - Qwen/DeepSeek: <|im_start|>system\n...<|im_end|>\n<|im_start|>user\n...
    - Mistral: [INST] ... [/INST]

    Args:
        messages: List of conversation messages
        system_message: System prompt text
        rag_context: Optional RAG context text
        document_name: Optional name of attached document
        model_folder: Model folder name for format selection

    Returns:
        Complete prompt string
    """
    # Determine chat template based on model
    model = model_folder or ""
    model_lower = model.lower()

    if "phi" in model_lower:
        return _construct_phi_prompt(messages, system_message, rag_context, document_name)
    elif "llama" in model_lower:
        return _construct_chatml_prompt(messages, system_message, rag_context, document_name)
    elif "qwen" in model_lower or "deepseek" in model_lower:
        return _construct_chatml_prompt(messages, system_message, rag_context, document_name)
    elif "mistral" in model_lower:
        return _construct_mistral_prompt(messages, system_message, rag_context, document_name)
    elif "gemma" in model_lower:
        return _construct_gemma_prompt(messages, system_message, rag_context, document_name)
    elif "falcon" in model_lower or "gpt-j" in model_lower:
        return _construct_simple_prompt(messages, system_message, rag_context, document_name)
    else:
        # Default to ChatML (widely supported)
        return _construct_chatml_prompt(messages, system_message, rag_context, document_name)


def _construct_phi_prompt(
    messages: List[Dict[str, Any]],
    system_message: str,
    rag_context: Optional[str] = None,
    document_name: Optional[str] = None
) -> str:
    """Construct prompt for Phi-3/Phi-3.5 models."""
    parts = []

    # System message with RAG context
    full_system = system_message
    if rag_context:
        rag_section = _build_rag_section(rag_context, document_name)
        full_system = f"{system_message}\n\n{rag_section}"

    parts.append(f"<|system|>\n{full_system}<|end|>")

    # Conversation history
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "user":
            parts.append(f"\n<|user|>\n{content}<|end|>")
        elif role == "assistant":
            parts.append(f"\n<|assistant|>\n{content}<|end|>")
        elif role == "system":
            parts.append(f"\n<|tool|>\n{content}<|end|>")

    # Final assistant marker for generation
    parts.append("\n<|assistant|>\n")

    return "".join(parts)


def _construct_chatml_prompt(
    messages: List[Dict[str, Any]],
    system_message: str,
    rag_context: Optional[str] = None,
    document_name: Optional[str] = None
) -> str:
    """Construct prompt for Qwen/DeepSeek (ChatML format)."""
    parts = []

    # System message with RAG context
    full_system = system_message
    if rag_context:
        rag_section = _build_rag_section(rag_context, document_name)
        full_system = f"{system_message}\n\n{rag_section}"

    parts.append(f"<|im_start|>system\n{full_system}<|im_end|>")

    # Conversation history
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "user":
            parts.append(f"\n<|im_start|>user\n{content}<|im_end|>")
        elif role == "assistant":
            parts.append(f"\n<|im_start|>assistant\n{content}<|im_end|>")
        elif role == "system":
            # Tool results stored as system messages - present as tool output
            parts.append(f"\n<|im_start|>tool\n{content}<|im_end|>")

    # Final assistant marker for generation
    parts.append("\n<|im_start|>assistant\n")

    return "".join(parts)


def _construct_mistral_prompt(
    messages: List[Dict[str, Any]],
    system_message: str,
    rag_context: Optional[str] = None,
    document_name: Optional[str] = None
) -> str:
    """Construct prompt for Mistral models."""
    parts = []

    # Mistral uses [INST] format, system message goes inside first instruction
    full_system = system_message
    if rag_context:
        rag_section = _build_rag_section(rag_context, document_name)
        full_system = f"{system_message}\n\n{rag_section}"

    # First user message includes system
    first_user = True
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "user":
            if first_user:
                parts.append(f"<s>[INST] {full_system}\n\n{content} [/INST]")
                first_user = False
            else:
                parts.append(f"[INST] {content} [/INST]")
        elif role == "assistant":
            parts.append(f" {content}</s>")

    # If no user messages yet, add system as instruction
    if first_user:
        parts.append(f"<s>[INST] {full_system} [/INST]")

    return "".join(parts)


def _construct_gemma_prompt(
    messages: List[Dict[str, Any]],
    system_message: str,
    rag_context: Optional[str] = None,
    document_name: Optional[str] = None
) -> str:
    """Construct prompt for Gemma models."""
    parts = []

    # Gemma uses <start_of_turn> format
    full_system = system_message
    if rag_context:
        rag_section = _build_rag_section(rag_context, document_name)
        full_system = f"{system_message}\n\n{rag_section}"

    # System as first user turn context
    first_user = True
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "user":
            if first_user:
                parts.append(f"<start_of_turn>user\n{full_system}\n\n{content}<end_of_turn>")
                first_user = False
            else:
                parts.append(f"\n<start_of_turn>user\n{content}<end_of_turn>")
        elif role == "assistant":
            parts.append(f"\n<start_of_turn>model\n{content}<end_of_turn>")

    # If no messages, add system as first user turn
    if first_user:
        parts.append(f"<start_of_turn>user\n{full_system}<end_of_turn>")

    # Final model marker for generation
    parts.append("\n<start_of_turn>model\n")

    return "".join(parts)


def _construct_simple_prompt(
    messages: List[Dict[str, Any]],
    system_message: str,
    rag_context: Optional[str] = None,
    document_name: Optional[str] = None
) -> str:
    """Construct simple prompt for models without special chat templates (GPT-J, Falcon)."""
    parts = []

    # System message
    full_system = system_message
    if rag_context:
        rag_section = _build_rag_section(rag_context, document_name)
        full_system = f"{system_message}\n\n{rag_section}"

    parts.append(f"System: {full_system}\n\n")

    # Conversation history
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "user":
            parts.append(f"User: {content}\n\n")
        elif role == "assistant":
            parts.append(f"Assistant: {content}\n\n")

    # Final assistant marker
    parts.append("Assistant:")

    return "".join(parts)


def _build_rag_section(rag_context: str, document_name: Optional[str] = None) -> str:
    """Build the RAG context section."""
    rag_parts = []
    if document_name:
        rag_parts.append(f'The user has attached a document: "{document_name}"')
    rag_parts.append("Below are relevant excerpts that may help answer the question.")
    rag_parts.append("\n--- DOCUMENT CONTEXT ---\n")
    rag_parts.append(rag_context)
    rag_parts.append("\n--- END DOCUMENT CONTEXT ---\n")
    rag_parts.append(
        "Use the above context if relevant. If the context doesn't contain "
        "relevant information, answer based on your general knowledge."
    )
    return "\n".join(rag_parts)


