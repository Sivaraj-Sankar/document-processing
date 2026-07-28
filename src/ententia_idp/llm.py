"""LLM integration — Bedrock / Claude tool-use invocation shared by all agents."""

import logging
from typing import Any

import anthropic
from anthropic.types import ToolUseBlock

from .config import settings
from .models import ExtractedDocument

logger = logging.getLogger(__name__)

# ── Singleton Bedrock client ──────────────────────────────────────────────────

_client: anthropic.AnthropicBedrock | None = None


def _get_client() -> anthropic.AnthropicBedrock:
    global _client
    if _client is None:
        logger.info(
            "Initialising Bedrock client (aws_profile=%s, aws_region=%s)",
            settings.aws_profile_name,
            settings.aws_region,
        )
        _client = anthropic.AnthropicBedrock(
            aws_region=settings.aws_region,
            aws_profile=settings.aws_profile_name,
        )
    return _client


# ── Document serialiser ───────────────────────────────────────────────────────


def serialize_document(doc: ExtractedDocument) -> str:
    """Convert an ExtractedDocument to a structured text block for LLM input."""
    parts: list[str] = [
        f"File: {doc.metadata.source_file_name}  |  Type: {doc.metadata.file_type}  |  Pages: {doc.metadata.total_pages}"
    ]

    for page in doc.pages:
        if page.text.strip():
            parts.append(f"--- PAGE {page.page_number} ---\n{page.text.strip()}")

    for table in doc.tables:
        parts.append(f"--- TABLE (page {table.page}) ---\n{table.markdown}")

    if doc.figures:
        fig_lines = [
            f"  • {f.fig_id} on page {f.page}" + (f": {f.caption}" if f.caption else "")
            for f in doc.figures
        ]
        parts.append("--- FIGURES ---\n" + "\n".join(fig_lines))

    return "\n\n".join(parts)


# ── Generic Bedrock tool-use invocation ───────────────────────────────────────


def invoke_bedrock_tool(
    user_message: str,
    system_prompt: str,
    tool: dict[str, Any],
    max_tokens: int,
) -> tuple[dict[str, Any], int, int]:
    """
    Call Bedrock with tool use and return (tool_input_dict, input_tokens, output_tokens).

    Forces the model to call `tool` via tool_choice so the response is always a
    validated ToolUseBlock — no manual JSON parsing needed.
    """
    client = _get_client()
    tool_name = tool["name"]

    try:
        response = client.messages.create(
            model=settings.bedrock_model_id,
            max_tokens=max_tokens,
            system=system_prompt,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.RateLimitError:
        logger.error("Bedrock rate limit hit (%s)", tool_name)
        raise RuntimeError("Bedrock rate limit exceeded") from None
    except anthropic.APITimeoutError:
        logger.error("Bedrock timeout (%s)", tool_name)
        raise RuntimeError("Bedrock request timed out") from None
    except anthropic.APIConnectionError:
        logger.error("Bedrock connection error (%s)", tool_name)
        raise RuntimeError("Failed to connect to Bedrock") from None
    except anthropic.APIError:
        logger.exception("Bedrock API error (%s)", tool_name)
        raise RuntimeError("Bedrock API error") from None

    tool_block = next((b for b in response.content if isinstance(b, ToolUseBlock)), None)
    if tool_block is None:
        raise RuntimeError(f"Model did not call tool '{tool_name}'")

    logger.debug(
        "%s — tokens(in/out)=%d/%d",
        tool_name,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )
    return tool_block.input, response.usage.input_tokens, response.usage.output_tokens  # type: ignore[return-value]
