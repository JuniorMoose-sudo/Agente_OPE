from datetime import date, datetime

from sqlalchemy import Date, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RosterTecnico(Base):
    """Fonte: painel-ope POST /api/semanatec (validador de nomes).

    Lista de técnicos ativos por setor — usado para validar que qualquer nome
    gravado no sistema bate com o roster antes de persistir.
    """

    __tablename__ = "roster_tecnico"

    tecnico: Mapped[str] = mapped_column(Text, primary_key=True)
    setor: Mapped[str] = mapped_column(Text)
    ultimo_visto: Mapped[date] = mapped_column(Date)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
