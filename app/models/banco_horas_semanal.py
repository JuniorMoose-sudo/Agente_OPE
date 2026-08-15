from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class BancoHorasSemanal(Base):
    """Fonte: painel-ope POST /api/analises (job diário).

    Snapshot semanal do payload completo por setor (rankings já calculados na
    origem). Os campos internos são extraídos/derivados numa etapa posterior,
    preservando sempre o payload bruto.
    """

    __tablename__ = "banco_horas_semanal"
    __table_args__ = (UniqueConstraint("setor", "semana_de", "semana_ate"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    setor: Mapped[str] = mapped_column(Text)
    semana_de: Mapped[date] = mapped_column(Date)
    semana_ate: Mapped[date] = mapped_column(Date)
    payload: Mapped[dict] = mapped_column(JSONB)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
