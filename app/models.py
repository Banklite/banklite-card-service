import uuid
from datetime import datetime
from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .database import Base

class Tarjeta(Base):
    __tablename__ = "tarjeta"

    id_tarjeta = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_cuenta = Column(UUID(as_uuid=True), nullable=False, index=True)
    tipo_tarjeta = Column(String(50), nullable=False)
    procesador_externo = Column(String(100), nullable=False)
    estado = Column(String(20), nullable=False, default="activa")
    fecha_emision = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("estado IN ('activa', 'bloqueada', 'vencida')", name="chk_tarjeta_estado"),
    )

    autorizaciones = relationship("Autorizacion", back_populates="tarjeta", cascade="all, delete-orphan")
    bloqueos = relationship("Bloqueo", back_populates="tarjeta", cascade="all, delete-orphan")


class Autorizacion(Base):
    __tablename__ = "autorizacion"

    id_autorizacion = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_tarjeta = Column(UUID(as_uuid=True), ForeignKey("tarjeta.id_tarjeta"), nullable=False)
    monto = Column(Numeric(12, 2), nullable=False)
    comercio = Column(String(150), nullable=False)
    resultado = Column(String(20), nullable=False)
    fecha_hora = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("monto > 0", name="chk_autorizacion_monto_positivo"),
        CheckConstraint("resultado IN ('aprobada', 'rechazada')", name="chk_autorizacion_resultado"),
        Index("idx_autorizacion_tarjeta", "id_tarjeta"),
        Index("idx_autorizacion_fecha", "fecha_hora"),
    )

    tarjeta = relationship("Tarjeta", back_populates="autorizaciones")


class Bloqueo(Base):
    __tablename__ = "bloqueo"

    id_bloqueo = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_tarjeta = Column(UUID(as_uuid=True), ForeignKey("tarjeta.id_tarjeta"), nullable=False)
    motivo = Column(String(255), nullable=False)
    fecha_inicio = Column(DateTime, default=datetime.utcnow, nullable=False)
    fecha_fin = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_bloqueo_tarjeta", "id_tarjeta"),
    )

    tarjeta = relationship("Tarjeta", back_populates="bloqueos")
