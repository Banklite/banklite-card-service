import logging
from uuid import UUID
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Tarjeta, Autorizacion, Bloqueo
from ..schemas import (
    TarjetaCreate, TarjetaOut,
    BloqueoCreate, BloqueoOut,
    AutorizacionCreate, AutorizacionOut
)
from ..events import publish_event, EVENT_CARD_AUTHORIZED

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cards", tags=["Cards"])

@router.post("/", response_model=TarjetaOut, status_code=status.HTTP_201_CREATED)
def emitir_tarjeta(payload: TarjetaCreate, db: Session = Depends(get_db)):
    tarjeta = Tarjeta(
        id_cuenta=payload.id_cuenta,
        tipo_tarjeta=payload.tipo_tarjeta,
        procesador_externo=payload.procesador_externo,
        estado=payload.estado
    )
    db.add(tarjeta)
    db.commit()
    db.refresh(tarjeta)
    return tarjeta

@router.get("/", response_model=List[TarjetaOut])
def listar_tarjetas(id_cuenta: Optional[UUID] = None, db: Session = Depends(get_db)):
    query = db.query(Tarjeta)
    if id_cuenta:
        query = query.filter(Tarjeta.id_cuenta == id_cuenta)
    return query.order_by(Tarjeta.fecha_emision.desc()).all()

@router.get("/{id_tarjeta}", response_model=TarjetaOut)
def obtener_tarjeta(id_tarjeta: UUID, db: Session = Depends(get_db)):
    tarjeta = db.query(Tarjeta).filter(Tarjeta.id_tarjeta == id_tarjeta).first()
    if not tarjeta:
        raise HTTPException(status_code=404, detail="Tarjeta no encontrada")
    return tarjeta

@router.post("/{id_tarjeta}/bloquear", response_model=BloqueoOut, status_code=status.HTTP_201_CREATED)
def bloquear_tarjeta(id_tarjeta: UUID, payload: BloqueoCreate, db: Session = Depends(get_db)):
    tarjeta = db.query(Tarjeta).filter(Tarjeta.id_tarjeta == id_tarjeta).first()
    if not tarjeta:
        raise HTTPException(status_code=404, detail="Tarjeta no encontrada")

    tarjeta.estado = "bloqueada"
    bloqueo = Bloqueo(
        id_tarjeta=id_tarjeta,
        motivo=payload.motivo,
        fecha_inicio=datetime.utcnow()
    )
    db.add(bloqueo)
    db.commit()
    db.refresh(bloqueo)
    return bloqueo

@router.post("/{id_tarjeta}/desbloquear", response_model=TarjetaOut)
def desbloquear_tarjeta(id_tarjeta: UUID, db: Session = Depends(get_db)):
    tarjeta = db.query(Tarjeta).filter(Tarjeta.id_tarjeta == id_tarjeta).first()
    if not tarjeta:
        raise HTTPException(status_code=404, detail="Tarjeta no encontrada")

    tarjeta.estado = "activa"
    for b in tarjeta.bloqueos:
        if b.fecha_fin is None:
            b.fecha_fin = datetime.utcnow()
    db.commit()
    db.refresh(tarjeta)
    return tarjeta

@router.post("/autorizar", response_model=AutorizacionOut, status_code=status.HTTP_200_OK)
def autorizar_transaccion(payload: AutorizacionCreate, db: Session = Depends(get_db)):
    tarjeta = db.query(Tarjeta).filter(Tarjeta.id_tarjeta == payload.id_tarjeta).first()
    if not tarjeta:
        raise HTTPException(status_code=404, detail="Tarjeta no encontrada")

    resultado = "aprobada" if tarjeta.estado == "activa" else "rechazada"

    auth = Autorizacion(
        id_tarjeta=payload.id_tarjeta,
        monto=payload.monto,
        comercio=payload.comercio,
        resultado=resultado,
        fecha_hora=datetime.utcnow()
    )
    db.add(auth)
    db.commit()
    db.refresh(auth)

    publish_event(EVENT_CARD_AUTHORIZED, {
        "id_autorizacion": str(auth.id_autorizacion),
        "id_tarjeta": str(auth.id_tarjeta),
        "id_cuenta": str(tarjeta.id_cuenta),
        "monto": float(auth.monto),
        "comercio": auth.comercio,
        "resultado": auth.resultado,
        "fecha_hora": auth.fecha_hora.isoformat()
    })

    return auth

@router.get("/{id_tarjeta}/autorizaciones", response_model=List[AutorizacionOut])
def listar_autorizaciones(id_tarjeta: UUID, db: Session = Depends(get_db)):
    return db.query(Autorizacion).filter(Autorizacion.id_tarjeta == id_tarjeta).order_by(Autorizacion.fecha_hora.desc()).all()

@router.get("/all/autorizaciones", response_model=List[AutorizacionOut])
def listar_todas_las_autorizaciones(db: Session = Depends(get_db)):
    return db.query(Autorizacion).order_by(Autorizacion.fecha_hora.desc()).limit(50).all()
