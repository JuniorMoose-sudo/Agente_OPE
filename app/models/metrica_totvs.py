from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MetricaTotvs(Base):
    """Fonte: TOTVS Analytics (GoodData) — KPIs e métricas operacionais.

    Snapshot diário dos dados extraídos via API GoodData. O payload bruto
    é armazenado como JSONB para preservar a estrutura original e permitir
    consultas flexíveis.
    """

    __tablename__ = "metrica_totvs"
    __table_args__ = (UniqueConstraint("dashboard_id", "report_id", "data_referencia"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dashboard_id: Mapped[str] = mapped_column(Text)
    report_id: Mapped[str] = mapped_column(Text)
    dashboard_titulo: Mapped[str | None] = mapped_column(Text)
    report_titulo: Mapped[str | None] = mapped_column(Text)
    data_referencia: Mapped[date] = mapped_column(Date)
    payload: Mapped[dict] = mapped_column(JSONB)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
