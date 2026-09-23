from uuid import UUID
from datetime import datetime
from typing import Optional, Literal, List
from pydantic import BaseModel, Field

class TarjetaCreate(BaseModel):
    id_cuenta: UUID
    tipo_tarjeta: str = Field(default="virtual", description="virtual o fisica")
    procesador_externo: str = Field(default="Visa Direct / Marqeta")
    estado: Literal["activa", "bloqueada", "vencida"] = "activa"

class BloqueoCreate(BaseModel):
    motivo: str = Field(..., min_length=3, max_length=255)

class AutorizacionCreate(BaseModel):
    id_tarjeta: UUID
    monto: float = Field(..., gt=0)
    comercio: str = Field(..., min_length=2, max_length=150)

class BloqueoOut(BaseModel):
    id_bloqueo: UUID
    id_tarjeta: UUID
    motivo: str
    fecha_inicio: datetime
    fecha_fin: Optional[datetime] = None

    class Config:
        from_attributes = True

class AutorizacionOut(BaseModel):
    id_autorizacion: UUID
    id_tarjeta: UUID
    monto: float
    comercio: str
    resultado: str
    fecha_hora: datetime

    class Config:
        from_attributes = True

class TarjetaOut(BaseModel):
    id_tarjeta: UUID
    id_cuenta: UUID
    tipo_tarjeta: str
    procesador_externo: str
    estado: str
    fecha_emision: datetime
    bloqueos: List[BloqueoOut] = []

    class Config:
        from_attributes = True
