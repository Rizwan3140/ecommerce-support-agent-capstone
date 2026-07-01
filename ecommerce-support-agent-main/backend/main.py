"""FastAPI app: POST /ingest, POST /query."""

import sys
from pathlib import Path

# Project root on sys.path for `agents`, `rag`, `utils`
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agents.workflow import resolve_support_ticket
from rag.ingest import ingest_policies
from tools.mock_apis import create_return_request, get_order_status, get_refund_policy, search_products
from utils.config import get_settings

app = FastAPI(
    title="E-commerce Support Resolution Agent",
    version="1.0.0",
    description="Multi-agent RAG (Groq + FAISS + HuggingFace embeddings)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    ticket: str = Field(..., description="Customer support ticket text")
    order_context: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON order context",
    )
    top_k: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Retriever top-k (optional)",
    )


class IngestResponse(BaseModel):
    status: str
    detail: dict[str, Any]


class ReturnRequest(BaseModel):
    order_id: str
    reason: str = "customer_request"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest", response_model=IngestResponse)
def ingest():
    """Build FAISS index from data/policies."""
    try:
        detail = ingest_policies()
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return IngestResponse(status="ok", detail=detail)


@app.post("/query")
def query(req: QueryRequest):
    """Process ticket through triage → retrieval → writer → compliance."""
    s = get_settings()
    if not (s.groq_api_key or "").strip():
        raise HTTPException(
            status_code=503,
            detail="GROQ_API_KEY is not set. Add it to .env in the project root and restart uvicorn.",
        )
    try:
        result = resolve_support_ticket(
            req.ticket,
            req.order_context,
            top_k=req.top_k,
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Vector index missing: {e}. Run POST /ingest first.",
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return result


@app.get("/tools/order-status/{order_id}")
def tool_order_status(order_id: str):
    """Mock OMS endpoint."""
    return get_order_status(order_id)


@app.post("/tools/returns")
def tool_create_return(req: ReturnRequest):
    """Mock returns endpoint."""
    return create_return_request(req.order_id, req.reason)


@app.get("/tools/refund-policy")
def tool_refund_policy():
    """Mock refund policy endpoint."""
    return get_refund_policy()


@app.get("/tools/products")
def tool_products(q: str):
    """Mock product catalog search endpoint."""
    return search_products(q)
