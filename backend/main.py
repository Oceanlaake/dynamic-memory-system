"""FastAPI 应用入口：uvicorn backend.main:app --reload"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.api.routes import router
from backend.schemas import ErrorResponse

app = FastAPI(
    title="Dynamic Memory System API",
    version="0.1.0",
    description=(
        "LoCoMo 动态记忆管理原型。接口契约见 APIs/retrieval.schema.json 与 APIs/query.schema.json。"
    ),
)
app.include_router(router)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    """把 FastAPI 默认的 {"detail": ...} 统一成 ErrorResponse。"""
    detail = exc.detail
    if isinstance(detail, dict) and {"code", "message"} <= detail.keys():
        body = ErrorResponse.model_validate({"error": detail})
    else:
        body = ErrorResponse.model_validate(
            {"error": {"code": f"HTTP_{exc.status_code}", "message": str(detail)}}
        )
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    body = ErrorResponse.model_validate(
        {
            "error": {
                "code": "INVALID_REQUEST",
                "message": "Request body failed validation.",
                "detail": {"errors": exc.errors()},
            }
        }
    )
    return JSONResponse(status_code=422, content=body.model_dump())
