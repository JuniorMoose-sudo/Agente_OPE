from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Infracao(Base):
    """Fonte: painel-ope POST /api/analises -> infracoesListaSemana.

    Uma linha por infração de técnico. `payload` guarda o registro bruto de
    origem (nome, data, detalhe, batidas, etc.) para auditoria.
    """

    __tablename__ = "infracao"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    setor: Mapped[str] = mapped_column(Text)
    semana_de: Mapped[date] = mapped_column(Date)
    semana_ate: Mapped[date] = mapped_column(Date)
    tecnico: Mapped[str | None] = mapped_column(Text, index=True)
    unidade: Mapped[str | None] = mapped_column(Text)
    sup: Mapped[str | None] = mapped_column(Text)
    data: Mapped[date | None] = mapped_column(Date)
    motivo: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
