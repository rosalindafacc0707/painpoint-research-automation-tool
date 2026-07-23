from fastapi import FastAPI

from routers.routers import router

app = FastAPI(
    title="Pain-Points Researcher Tool",
    description="FastAPI wrappers around Pain-Points Researcher Tool services.",
    version="0.1.0",
)

app.include_router(router)
