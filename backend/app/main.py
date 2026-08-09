from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .routers import tasks, ingest, api

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Sales Inbox Task Router", version="1.0.0")

from .config import CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(ingest.router)
app.include_router(api.router)


@app.get("/")
@app.get("/health")
def health():
    return {"status": "ok", "service": "sales-inbox-task-router"}
