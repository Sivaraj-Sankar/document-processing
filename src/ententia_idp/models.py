from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class DocumentMetadata(BaseModel):
    source_file_name: str
    file_type: str
    total_pages: int


class ExtractedTable(BaseModel):
    page: int
    markdown: str
    csv: str


class ExtractedFigure(BaseModel):
    page: int
    caption: str
    fig_id: str


class ExtractedPage(BaseModel):
    page_number: int
    text: str
    word_count: int
    figure_count: int
    table_count: int


class ExtractedDocument(BaseModel):
    metadata: DocumentMetadata
    pages: List[ExtractedPage]
    tables: List[ExtractedTable]
    figures: List[ExtractedFigure]


class AgentMetrics(BaseModel):
    agent_name: str
    start_time: float
    end_time: float
    latency_seconds: float
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    error: Optional[str] = None


class PipelineMetrics(BaseModel):
    document_id: str
    start_time: float
    end_time: Optional[float] = None
    request_latency_seconds: Optional[float] = None
    total_token_cost_usd: Optional[float] = None
    agent_metrics: List[AgentMetrics] = []
    errors: List[str] = []


class ProcessedOutput(BaseModel):
    classification: str
    tags: List[str]
    extracted_fields: Dict[str, Any]
    summary: str


class ProcessDocumentResponse(BaseModel):
    document_id: str
    output: Optional[ProcessedOutput]
    metrics: PipelineMetrics
    partial: bool = False
    errors: Optional[List[str]] = None
