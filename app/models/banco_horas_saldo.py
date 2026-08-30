from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Numeric, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class BancoHorasSaldo(Base):
    """Fonte: Google Sheets publicada (web) — "Banco de Horas" por técnico/dia.

    Aba ``HISTORICO_REG03`` (unidades CAMPINA GRANDE e LAGOA SECA), export CSV
    público (sem cookie). Cada linha é o SALDO do banco de horas de um técnico
    numa data. Sync diário via ``sync_banco_horas_saldo`` — substitui o painel-ope
    como fonte de banco de horas/HE (a coluna ``SALDO`` é o saldo acumulado).
    """

    __tablename__ = "banco_horas_saldo"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tecnico: Mapped[str] = mapped_column(Text, index=True)
    unidade: Mapped[str] = mapped_column(Text)
    data: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    saldo: Mapped[float | None] = mapped_column(Numeric(10, 2))
    cargo: Mapped[str | None] = mapped_column(Text)
    tipo: Mapped[str | None] = mapped_column(Text)
    coordenador: Mapped[str | None] = mapped_column(Text)
    supervisor: Mapped[str | None] = mapped_column(Text)
    variacao: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # uma linha por técnico+unidade+dia — chave do upsert do sync
        UniqueConstraint("tecnico", "unidade", "data", name="uq_banco_horas_saldo_tec_uni_dia"),
    )