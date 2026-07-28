import os
import tempfile
import time
from pathlib import Path
import uvicorn
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from .config import Settings
from .extractor import DocumentExtractor
from .pipeline import DocumentPipeline
from .logger import logger
from .metrics import registry, request_latency_seconds, requests_total


def create_app() -> FastAPI:
    app = FastAPI(title="Ententia IDP Service", version="0.1.0")
    settings = Settings()
    extractor = DocumentExtractor()
    pipeline = DocumentPipeline()
    ui_path = Path(__file__).resolve().parent / "static" / "index.html"

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    @app.get("/ui", include_in_schema=False)
    def ui():
        if not ui_path.exists():
            raise HTTPException(status_code=404, detail="UI not found")
        return FileResponse(path=ui_path)

    @app.post("/process_document")
    async def process_document(file: UploadFile = File(...)):
        requests_total.inc()
        request_start = time.perf_counter()
        if file.content_type not in {
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "text/plain",
        }:
            raise HTTPException(status_code=415, detail="Unsupported file type")

        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        try:
            extracted = extractor.extract(tmp_path)
            response = pipeline.run(extracted)
            return JSONResponse(status_code=200, content=response.dict())
        except Exception as exc:
            logger.exception("Document processing failed")
            raise HTTPException(status_code=500, detail=str(exc))
        finally:
            request_latency_seconds.observe(time.perf_counter() - request_start)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    @app.get("/metrics")
    def metrics():
        return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    @app.get("/pipeline_graph")
    def pipeline_graph():
        try:
            return {"mermaid": pipeline.get_graph_mermaid()}
        except Exception as exc:
            logger.exception("Failed to generate pipeline graph")
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/pipeline_graph.png")
    def pipeline_graph_png():
        try:
            return Response(content=pipeline.get_graph_png(), media_type="image/png")
        except Exception as exc:
            logger.exception("Failed to generate pipeline graph image")
            raise HTTPException(status_code=503, detail=str(exc))

    return app


app = create_app()


if __name__ == "__main__":
    settings = Settings()
    uvicorn.run(
        "ententia_idp.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        log_level="info",
        reload=False,
    )
