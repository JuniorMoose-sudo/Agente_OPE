from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SolicitacaoServico(Base):
    """Fonte: Proxxima Painel_ServicosApi/GetAll (job de sync, ~30 min).

    Cada linha é um serviço com atribuição de técnico. `os` é o protocolo
    normalizado (ex.: "12345/2026" -> "12345") e é a chave de join com
    ocorrencia_recorrencia.protocolo.
    """

    __tablename__ = "solicitacao_servico"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    os: Mapped[str] = mapped_column(Text, unique=True)
    os_original: Mapped[str | None] = mapped_column(Text)
    unidade: Mapped[str] = mapped_column(Text)
    natureza: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    tecnico: Mapped[str | None] = mapped_column(Text, index=True)
    abertura: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    venc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_status: Mapped[str | None] = mapped_column(Text)
    relatos: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
