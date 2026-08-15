from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.jobs.sync_proxxima import start_scheduler, stop_scheduler
from app.routers import health, solicitacoes


@asynccontextmanager
async def lifespan(_: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Agente OPE — API de apoio à decisão operacional",
    version="0.1.0",
    description="Backend consultivo que cruza recorrência, produtividade, banco de horas/HE, infrações e inspeção.",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(solicitacoes.router)
