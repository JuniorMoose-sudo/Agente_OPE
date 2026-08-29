from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import Base, engine
from app.jobs.sync_painel_ope import start_scheduler as start_scheduler_ope
from app.jobs.sync_painel_ope import stop_scheduler as stop_scheduler_ope
from app.jobs.sync_pontuacao import start_scheduler as start_scheduler_pontuacao
from app.jobs.sync_pontuacao import stop_scheduler as stop_scheduler_pontuacao
from app.jobs.sync_proxxima import start_scheduler, stop_scheduler
from app.jobs.sync_recorrencia_painel import start_scheduler as start_scheduler_recorrencia
from app.jobs.sync_recorrencia_painel import stop_scheduler as stop_scheduler_recorrencia
from app.jobs.sync_totvs import start_scheduler as start_scheduler_totvs
from app.jobs.sync_totvs import stop_scheduler as stop_scheduler_totvs
from app.routers import banco_horas, diagnostico, health, planilha, recorrencia, relatorio, solicitacoes, totvs


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    start_scheduler()
    start_scheduler_ope()
    start_scheduler_totvs()
    start_scheduler_recorrencia()
    start_scheduler_pontuacao()
    yield
    stop_scheduler()
    stop_scheduler_ope()
    stop_scheduler_totvs()
    stop_scheduler_recorrencia()
    stop_scheduler_pontuacao()


app = FastAPI(
    title="Agente OPE — API de apoio à decisão operacional",
    version="0.1.0",
    description="Backend consultivo que cruza recorrência, produtividade, banco de horas/HE, infrações e inspeção.",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(solicitacoes.router)
app.include_router(banco_horas.router)
app.include_router(recorrencia.router)
app.include_router(diagnostico.router)
app.include_router(planilha.router)
app.include_router(relatorio.router)
app.include_router(totvs.router)
