"""Modelo para relatórios gerados (.docx).

Cada relatório é salvo em disco e registrado no banco com metadados
para download posterior.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Relatorio(Base):
    __tablename__ = "relatorio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    titulo: Mapped[str] = mapped_column(String(255))
    unidade: Mapped[str] = mapped_column(String(100))
    periodo_de: Mapped[str] = mapped_column(String(10))
    periodo_ate: Mapped[str] = mapped_column(String(10))
    nome_arquivo: Mapped[str] = mapped_column(String(255))
    caminho: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
