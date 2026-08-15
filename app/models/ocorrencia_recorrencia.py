from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class OcorrenciaRecorrencia(Base):
    """Fonte: Excel "Analítico" de recorrência (export manual) + join de técnico.

    Uma linha por protocolo. `protocolo` é a chave de join com
    solicitacao_servico.os, de onde vem o `tecnico` resolvido.
    """

    __tablename__ = "ocorrencia_recorrencia"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    protocolo: Mapped[str] = mapped_column(Text, unique=True)
    data_abertura: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_fechamento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    problema_fechamento: Mapped[str | None] = mapped_column(Text)
    cidade: Mapped[str | None] = mapped_column(Text)
    unidade: Mapped[str | None] = mapped_column(Text)
    etiqueta: Mapped[str | None] = mapped_column(Text)
    protocolo_anterior: Mapped[str | None] = mapped_column(
        Text, ForeignKey("ocorrencia_recorrencia.protocolo")
    )
    data_abertura_anterior: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_fechamento_anterior: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    problema_fechamento_anterior: Mapped[str | None] = mapped_column(Text)
    dias_entre_os: Mapped[int | None] = mapped_column(Integer)
    e_recorrencia: Mapped[bool] = mapped_column(Boolean, default=False)
    tecnico: Mapped[str | None] = mapped_column(Text, index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
