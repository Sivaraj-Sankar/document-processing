# Ententia IDP Architecture

## Purpose
This architecture defines a single-service, FastAPI-based document intelligence pipeline for Ententia IDP. It uses Docling for document extraction and a LangGraph-aligned multi-agent orchestration pattern to produce:

- document classification
- semantic tags
- extracted key fields
- a short summary

This implementation intentionally avoids Kafka, microservices, event brokers, and external object storage.

## Core Constraints
- Single FastAPI service
- No external storage services (MinIO, S3, etc.)
- In-memory document flow per request
- Docling for extraction only
- LangGraph-compatible agent orchestration pattern
- Full observability and per-agent metrics
- Token and cost capture for LLM-based agents
- Robust error handling and partial output support

## High-Level Architecture

1. FastAPI request receives a document upload.
2. Startup event initializes Docling and preloads model configuration.
3. Uploaded data is extracted by `DoclingExtractor`.
4. The extracted content enters a multi-agent pipeline.
5. The pipeline produces classification, tags, fields, and summary.
6. Metrics are recorded for each agent and aggregated per document.
7. The response is returned without persisting intermediate data externally.

## Component Overview

### FastAPI Service
- `POST /process_document` for document uploads
- `GET /health` for service health
- `GET /metrics` for Prometheus-compatible metrics

### Docling Extractor
- Initializes a `DocumentConverter` on startup
- Supports PDF, DOCX, and plain text
- Extracts page text, tables, and figure metadata
- Uses temp files for request-local extraction

### Agent Pipeline
- `ClassificationAgent`
- `TaggingAgent`
- `FieldExtractionAgent`
- `SummaryAgent`

The pipeline is designed as a directed graph of agent stages and can be extended into a full LangGraph `StateGraph` workflow.

### Metrics and Observability
- Per-agent latency
- Per-agent input/output tokens
- Total token cost per document
- Request-level latency
- Error counts and partial output diagnostics
- Prometheus exporter on `/metrics`

## Docling Model Startup
- On FastAPI startup, the service pre-creates the Docling converter.
- First run may download models into `~/.cache/docling/` (~750MB).
- The architecture marks startup model readiness before accepting requests.
- A clear note is included in the service docs and README.

## LangGraph-Oriented Orchestration Pattern

The pipeline uses an agent orchestration design that can be mapped to LangGraph:

- `StateGraph` defines the workflow state and agent transitions
- Each agent stage is a graph node
- The workflow can be extended with parallel branches and retry logic
- Outputs are aggregated into a final structured response

This implementation executes agents through a LangGraph `StateGraph` with explicit node-to-node transitions.

## Error Handling

- Agent-level exceptions capture diagnostics and allow partial responses
- Missing expected extraction fields are returned as `null`
- Global FastAPI exception handler returns structured error info
- Transient LLM failures can be retried inside the agent implementation
- Unsupported document formats are rejected with clear validation messages

## Metrics Capture

Metrics include:
- `ententia_idp_requests_total`
- `ententia_idp_request_latency_seconds`
- `ententia_idp_agent_latency_seconds`
- `ententia_idp_agent_tokens_total`
- `ententia_idp_document_cost_usd`

Where possible, the service records:
- agent name
- agent start/end latency
- token counts for LLM-based agents
- total cost for the document run

## Scalability Notes

This implementation is horizontally scalable using multiple Uvicorn worker processes.

- CPU-heavy Docling extraction is bounded by a thread pool
- LLM work is asynchronous and rate-limited in the agent layer
- FastAPI lifecycle holds one in-memory pipeline per request
- Shared startup state keeps model initialization warm

## Deployment Strategy

- Run using `uvicorn ententia_idp.main:app --host 0.0.0.0 --port 8000`
- Use process managers or container orchestration to scale workers
- Monitor `/metrics` with Prometheus
- Ensure the service has enough local disk for Docling model cache

## Next Steps

1. Extend the LangGraph workflow with conditional routing, retries, and parallel branches where useful.
2. Replace heuristic agents with actual LLM prompts and structured output models.
3. Add request tracing and distributed tracing if needed.
4. Add integration tests for the document processing endpoint.
