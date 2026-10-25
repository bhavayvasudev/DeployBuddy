from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from deploy_buddy.api.health import router
from deploy_buddy.api.requests import router as requests_router
from deploy_buddy.db.config import DatabaseSafetyError

app = FastAPI(title="Deploy Buddy", version="0.1.0")
app.include_router(router)
app.include_router(requests_router)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, error: RequestValidationError):
    # Pydantic errors normally echo raw input (including credentials/unknown fields).
    # Never return or log that input, validation messages or exception contexts.
    return JSONResponse(
        status_code=422, content={"detail": "Invalid or unsupported request values."}
    )


@app.exception_handler(DatabaseSafetyError)
@app.exception_handler(SQLAlchemyError)
async def unavailable_database(request: Request, error: Exception):
    return JSONResponse(
        status_code=503, content={"detail": "Local database unavailable. Check local setup."}
    )
