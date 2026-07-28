import uuid
import time
import operator
from typing import Any, Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from .agents import (
    ClassificationAgent,
    FieldExtractionAgent,
    SummaryAgent,
    TaggingAgent,
    AgentResult,
)
from .logger import logger
from .metrics import AgentMetricTracker
from .models import ExtractedDocument, PipelineMetrics, ProcessDocumentResponse, ProcessedOutput


class PipelineState(TypedDict):
    extracted_document: ExtractedDocument
    classification: str
    tags: list[str]
    extracted_fields: dict[str, Any]
    summary: str
    partial: Annotated[bool, operator.or_]
    errors: Annotated[list[str], operator.add]
    agent_metrics: Annotated[list[dict[str, Any]], operator.add]


class DocumentPipeline:
    def __init__(self):
        self.classification_agent = ClassificationAgent()
        self.tagging_agent = TaggingAgent()
        self.field_extraction_agent = FieldExtractionAgent()
        self.summary_agent = SummaryAgent()
        self.graph = self._build_graph()

    def _run_agent_node(self, agent: Any, state: PipelineState) -> PipelineState:
        tracker = AgentMetricTracker(agent.agent_name)
        context = {
            "classification": state["classification"],
            "tags": state["tags"],
            "extracted_fields": state["extracted_fields"],
            "summary": state["summary"],
        }

        try:
            result: AgentResult = agent.run(state["extracted_document"], context)
            tracker.finish(
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                error=result.error,
            )
            if result.error:
                return {
                    "partial": True,
                    "errors": [result.error],
                    "agent_metrics": [tracker.to_dict()],
                }
            return {**result.output, "agent_metrics": [tracker.to_dict()], "partial": False}
        except Exception as exc:
            error_message = f"{agent.agent_name} failed: {exc}"
            logger.exception(error_message)
            tracker.finish(error=error_message)
            return {"errors": [error_message], "partial": True, "agent_metrics": [tracker.to_dict()]}

    def _build_graph(self):
        workflow = StateGraph(PipelineState)
        workflow.add_node(
            "classification",
            lambda state: self._run_agent_node(self.classification_agent, state),
        )
        workflow.add_node(
            "tagging",
            lambda state: self._run_agent_node(self.tagging_agent, state),
        )
        workflow.add_node(
            "field_extraction",
            lambda state: self._run_agent_node(self.field_extraction_agent, state),
        )
        workflow.add_node(
            "summary",
            lambda state: self._run_agent_node(self.summary_agent, state),
        )

        workflow.add_edge(START, "classification")
        workflow.add_edge("classification", "tagging")
        workflow.add_edge("classification", "field_extraction")
        workflow.add_edge("classification", "summary")
        workflow.add_edge("tagging", END)
        workflow.add_edge("field_extraction", END)
        workflow.add_edge("summary", END)
        return workflow.compile()

    def get_graph_mermaid(self) -> str:
        return self.graph.get_graph().draw_mermaid()

    def get_graph_png(self) -> bytes:
        draw_mermaid_png = getattr(self.graph.get_graph(), "draw_mermaid_png", None)
        if not callable(draw_mermaid_png):
            raise RuntimeError("LangGraph PNG rendering is not available in this environment")

        png_bytes = draw_mermaid_png()
        if not isinstance(png_bytes, (bytes, bytearray)):
            raise RuntimeError("LangGraph did not return PNG bytes")
        return bytes(png_bytes)

    def run(self, extracted_document: ExtractedDocument) -> ProcessDocumentResponse:
        document_id = str(uuid.uuid4())
        logger.info("Starting document pipeline %s", document_id)
        pipeline_metrics = PipelineMetrics(document_id=document_id, start_time=time.perf_counter())

        initial_state: PipelineState = {
            "extracted_document": extracted_document,
            "classification": "UNKNOWN",
            "tags": [],
            "extracted_fields": {},
            "summary": "",
            "partial": False,
            "errors": [],
            "agent_metrics": [],
        }
        final_state = self.graph.invoke(initial_state)
        classification = final_state["classification"]
        tags = final_state["tags"]
        extracted_fields = final_state["extracted_fields"]
        summary = final_state["summary"]
        partial = final_state["partial"]
        errors = final_state["errors"]
        pipeline_metrics.agent_metrics = final_state["agent_metrics"]

        end_time = time.perf_counter()
        pipeline_metrics.end_time = end_time
        pipeline_metrics.request_latency_seconds = end_time - pipeline_metrics.start_time
        pipeline_metrics.total_token_cost_usd = sum(
            metric.get("cost_usd", 0.0) for metric in pipeline_metrics.agent_metrics
        )
        pipeline_metrics.errors = errors

        output = ProcessedOutput(
            classification=classification,
            tags=tags,
            extracted_fields=extracted_fields,
            summary=summary,
        )

        return ProcessDocumentResponse(
            document_id=document_id,
            output=output,
            metrics=pipeline_metrics,
            partial=partial,
            errors=errors if errors else None,
        )
