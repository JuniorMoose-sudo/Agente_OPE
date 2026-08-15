from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Inspecao(Base):
    """Fonte: Google Sheets (aba Inspecao) — ingestão manual.

    `criterios_reprovados` guarda a lista de critérios reprovados como JSONB.
    """

    __tablename__ = "inspecao"
    __table_args__ = (UniqueConstraint("tecnico", "data_inspecao"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tecnico: Mapped[str] = mapped_column(Text)
    data_inspecao: Mapped[date] = mapped_column(Date)
    pontuacao: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    criterios_reprovados: Mapped[list | None] = mapped_column(JSONB)
    inspetor: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
