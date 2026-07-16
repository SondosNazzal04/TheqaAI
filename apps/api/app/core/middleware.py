import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from fastapi import FastAPI

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

def setup_middlewares(app: FastAPI) -> None:
    # Set up CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], # For dev only, configure properly for prod
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Set up Request ID
    app.add_middleware(RequestIDMiddleware)
