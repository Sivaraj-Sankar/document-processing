"""
Multi-agent pipeline — each agent makes its own dedicated Bedrock tool-use call.

Execution order (enforced by pipeline.py):
  1. ClassificationAgent   → classification
  2. TaggingAgent          → tags           (uses classification)
  3. FieldExtractionAgent  → extracted_fields (uses classification to guide field selection)
  4. SummaryAgent          → summary        (uses classification)
"""

from typing import Any, Optional

from .llm import invoke_bedrock_tool, serialize_document
from .logger import logger
from .models import ExtractedDocument


# ── Shared result type ────────────────────────────────────────────────────────


class AgentResult:
    def __init__(
        self,
        name: str,
        output: dict,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        error: Optional[str] = None,
    ):
        self.name = name
        self.output = output
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cost_usd = cost_usd
        self.error = error


class BaseAgent:
    def __init__(self, agent_name: str):
        self.agent_name = agent_name

    def run(self, doc: ExtractedDocument, context: dict[str, Any]) -> AgentResult:
        raise NotImplementedError()


# ── 1. ClassificationAgent ────────────────────────────────────────────────────

_CLASSIFY_TOOL: dict[str, Any] = {
    "name": "classify_document",
    "description": "Classify the document type based on its content.",
    "input_schema": {
        "type": "object",
        "properties": {
            "classification": {
                "type": "string",
                "enum": ["Invoice", "Support Ticket", "Statement of Work", "Vendor Contract", "UNKNOWN"],
                "description": "The document type.",
            },
        },
        "required": ["classification"],
    },
}

_CLASSIFY_SYSTEM = """You are a document classification specialist.
Analyse the document content and identify its type.

Definitions:
- Invoice: a bill or payment request listing line items and amounts due
- Support Ticket: an IT/customer incident record with a ticket ID, priority, and resolution
- Statement of Work: a project contract specifying scope, milestones, deliverables, and payment schedule
- Vendor Contract: a legal services agreement covering terms, renewal, and liability between parties
- UNKNOWN: does not clearly match any of the above"""


class ClassificationAgent(BaseAgent):
    def __init__(self):
        super().__init__("ClassificationAgent")

    def run(self, doc: ExtractedDocument, context: dict[str, Any]) -> AgentResult:
        logger.info("Running ClassificationAgent")
        content = serialize_document(doc)
        tool_input, in_tok, out_tok = invoke_bedrock_tool(
            user_message=f"Classify this document:\n\n{content}",
            system_prompt=_CLASSIFY_SYSTEM,
            tool=_CLASSIFY_TOOL,
            max_tokens=128,
        )
        classification = tool_input.get("classification", "UNKNOWN")
        logger.info("ClassificationAgent → %s", classification)
        return AgentResult(
            name=self.agent_name,
            output={"classification": classification},
            input_tokens=in_tok,
            output_tokens=out_tok,
        )


# ── 2. TaggingAgent ───────────────────────────────────────────────────────────

_TAG_TOOL: dict[str, Any] = {
    "name": "tag_document",
    "description": "Generate semantic tags for a document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3–7 lowercase hyphen-separated semantic tags.",
                "minItems": 3,
                "maxItems": 7,
            },
        },
        "required": ["tags"],
    },
}

_TAG_SYSTEM = """You are a document tagging specialist.
Generate 3–7 lowercase hyphen-separated semantic tags that reflect the document's
main themes, industry, and key attributes. Tags must be grounded in the document content.

Examples by document type:
- Invoice: milestone-payment, net-30, gst, change-order, b2b
- Support Ticket: p1, production-down, ldap, erp, access, resolved
- Statement of Work: milestone-based, ocr, ai, fintech, multi-party
- Vendor Contract: saas, cloud-infrastructure, auto-renewal, liability-cap, indemnity"""


class TaggingAgent(BaseAgent):
    def __init__(self):
        super().__init__("TaggingAgent")

    def run(self, doc: ExtractedDocument, context: dict[str, Any]) -> AgentResult:
        logger.info("Running TaggingAgent")
        content = serialize_document(doc)
        classification = context.get("classification", "")
        tool_input, in_tok, out_tok = invoke_bedrock_tool(
            user_message=f"Document type: {classification}\n\nGenerate tags for this document:\n\n{content}",
            system_prompt=_TAG_SYSTEM,
            tool=_TAG_TOOL,
            max_tokens=256,
        )
        tags = tool_input.get("tags", [])
        logger.info("TaggingAgent → %s", tags)
        return AgentResult(
            name=self.agent_name,
            output={"tags": tags},
            input_tokens=in_tok,
            output_tokens=out_tok,
        )


# ── 3. FieldExtractionAgent ───────────────────────────────────────────────────

_FIELD_TOOL: dict[str, Any] = {
    "name": "extract_fields",
    "description": "Extract all key business fields from a document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "fields": {
                "type": "object",
                "description": (
                    "All key business fields for this specific document type. "
                    "Use snake_case keys. Values may be strings, numbers, or arrays. "
                    "Extract every field present — do not use a fixed schema or omit anything."
                ),
                "additionalProperties": True,
            },
        },
        "required": ["fields"],
    },
}

_FIELD_SYSTEM = """You are a document field extraction specialist.
Extract ALL key business fields found in the document. Use snake_case keys.
Do NOT apply a fixed field list — extract whatever is actually present.

Field guidance by document type:

Invoice:
  invoice_number, invoice_date, due_date, payment_terms, vendor, client,
  line_items (array — each with description, quantity, rate, amount),
  subtotal, tax_rate, tax_amount, total_amount, payment_instructions, reference_sow

Support Ticket:
  ticket_id, submitted_by, submitted_date, priority, status, category,
  affected_system, assigned_to, description, root_cause,
  resolved_by, resolution_time, resolution_notes

Statement of Work:
  project_name, sow_number, client, vendor, start_date, end_date,
  total_budget, deliverables (array), milestones (array — each with name, amount, due_date),
  key_contacts (array — each with name, role, email)

Vendor Contract:
  parties (array), effective_date, expiry_date, contract_value, payment_terms,
  auto_renewal, auto_renewal_notice_period, termination_notice_convenience,
  termination_notice_for_cause, governing_law, dispute_resolution, liability_cap

Omit fields that are absent from the document."""


class FieldExtractionAgent(BaseAgent):
    def __init__(self):
        super().__init__("FieldExtractionAgent")

    def run(self, doc: ExtractedDocument, context: dict[str, Any]) -> AgentResult:
        logger.info("Running FieldExtractionAgent")
        content = serialize_document(doc)
        classification = context.get("classification", "UNKNOWN")
        tool_input, in_tok, out_tok = invoke_bedrock_tool(
            user_message=(
                f"Document type: {classification}\n\n"
                f"Extract all key business fields from this document:\n\n{content}"
            ),
            system_prompt=_FIELD_SYSTEM,
            tool=_FIELD_TOOL,
            max_tokens=4096,
        )
        fields = tool_input.get("fields", {})
        logger.info("FieldExtractionAgent → %d fields extracted", len(fields))
        return AgentResult(
            name=self.agent_name,
            output={"extracted_fields": fields},
            input_tokens=in_tok,
            output_tokens=out_tok,
        )


# ── 4. SummaryAgent ───────────────────────────────────────────────────────────

_SUMMARY_TOOL: dict[str, Any] = {
    "name": "summarize_document",
    "description": "Generate a concise summary of a document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "A 2–3 sentence plain-language description of the document's purpose and key details.",
            },
        },
        "required": ["summary"],
    },
}

_SUMMARY_SYSTEM = """You are a document summarization specialist.
Write a concise 2–3 sentence plain-language summary that captures:
- The document's purpose and type
- The key parties, amounts, dates, or actions involved
- Any important outcome or context

Be specific — reference actual values from the document (names, amounts, dates)."""


class SummaryAgent(BaseAgent):
    def __init__(self):
        super().__init__("SummaryAgent")

    def run(self, doc: ExtractedDocument, context: dict[str, Any]) -> AgentResult:
        logger.info("Running SummaryAgent")
        content = serialize_document(doc)
        classification = context.get("classification", "")
        tool_input, in_tok, out_tok = invoke_bedrock_tool(
            user_message=f"Document type: {classification}\n\nSummarise this document:\n\n{content}",
            system_prompt=_SUMMARY_SYSTEM,
            tool=_SUMMARY_TOOL,
            max_tokens=512,
        )
        summary = tool_input.get("summary", "")
        logger.info("SummaryAgent complete")
        return AgentResult(
            name=self.agent_name,
            output={"summary": summary},
            input_tokens=in_tok,
            output_tokens=out_tok,
        )
