from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Numeric, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PontuacaoTecnicoDia(Base):
    """Fonte: webhook n8n ``aniel-aovivo`` (n8n.proxxima.net).

    Pontuação diária por técnico (equipe) derivada de ``fechSemana``: soma dos
    ``pontos`` dos fechamentos do dia (``encDK``), agrupado por técnico e
    unidade. ``nao_pontua`` indica técnico que não participa da pontuação
    (lista ``naoPontua`` do webhook).
    """

    __tablename__ = "pontuacao_tecnico_dia"
    __table_args__ = (UniqueConstraint("tecnico", "unidade", "data"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tecnico: Mapped[str] = mapped_column(Text, index=True)
    unidade: Mapped[str] = mapped_column(Text, index=True)
    data: Mapped[date] = mapped_column(Date, index=True)
    pontos: Mapped[float | None] = mapped_column(Numeric(6, 2))
    nao_pontua: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )