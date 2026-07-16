from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

def setup_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        # We would log this exception with request ID here
        request_id = getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=500,
            content={
                "type": "server_error",
                "title": "Internal Server Error",
                "status": 500,
                "detail": str(exc),
                "request_id": request_id
            }
        )
