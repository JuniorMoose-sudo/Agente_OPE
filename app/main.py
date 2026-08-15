from fastapi import FastAPI

from app.routers import health

app = FastAPI(
    title="Agente OPE — API de apoio à decisão operacional",
    version="0.1.0",
    description="Backend consultivo que cruza recorrência, produtividade, banco de horas/HE, infrações e inspeção.",
)

app.include_router(health.router)
