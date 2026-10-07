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
    TarjetaSolicitudCliente,
    BloqueoCreate, BloqueoOut,
    AutorizacionCreate, AutorizacionOut
)
from ..events import publish_event, EVENT_CARD_AUTHORIZED
from ..clients import get_account, get_user, registrar_bono_bienvenida

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cards", tags=["Cards"])


@router.post("/", response_model=TarjetaOut, status_code=status.HTTP_201_CREATED)
def emitir_tarjeta(payload: TarjetaCreate, db: Session = Depends(get_db)):
    """Emite una tarjeta asociada a una cuenta.
    Usado exclusivamente por el administrador.
    """
    import random
    numero_aleatorio = "".join([str(random.randint(0, 9)) for _ in range(16)])
    tarjeta = Tarjeta(
        id_cuenta=payload.id_cuenta,
        numero_tarjeta=numero_aleatorio,
        tipo_tarjeta=payload.tipo_tarjeta,
        procesador_externo=payload.procesador_externo,
        estado=payload.estado
    )
    db.add(tarjeta)
    db.commit()
    db.refresh(tarjeta)
    return tarjeta


@router.post("/solicitar", response_model=TarjetaOut, status_code=status.HTTP_201_CREATED)
def solicitar_tarjeta_cliente(payload: TarjetaSolicitudCliente, db: Session = Depends(get_db)):
    """Endpoint para que el PROPIO USUARIO solicite su tarjeta.

    Reglas de seguridad (validadas en BACKEND, nunca en frontend):
    1. El usuario debe estar completamente verificado (estado == 'verificado').
    2. La cuenta debe existir y estar activa.
    3. La cuenta debe pertenecer al usuario indicado.
    4. No debe existir una tarjeta activa ya asociada a esa cuenta (no duplicados).
    5. Los datos sensibles (número, CVV, estado) los genera el backend.
    6. La operación es idempotente si ya existe una tarjeta activa.
    """
    # ── REGLA 1: Usuario verificado ────────────────────────────────────────────
    usuario = get_user(str(payload.id_usuario))
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )
    if usuario.get("estado") != "verificado":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes solicitar una tarjeta hasta completar la verificación de identidad.",
        )

    # ── REGLA 2 y 3: Cuenta activa y pertenece al usuario ───────────────────
    cuenta = get_account(str(payload.id_cuenta))
    if cuenta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Necesitas tener una cuenta bancaria activa para solicitar una tarjeta.",
        )
    if cuenta.get("estado") != "activa":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Necesitas tener una cuenta bancaria activa para solicitar una tarjeta.",
        )
    if str(cuenta.get("id_usuario")) != str(payload.id_usuario):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta indicada no pertenece a este usuario.",
        )

    # ── REGLA 4: No tarjeta activa duplicada ──────────────────────────────
    tarjeta_existente = (
        db.query(Tarjeta)
        .filter(Tarjeta.id_cuenta == payload.id_cuenta, Tarjeta.estado == "activa")
        .first()
    )
    if tarjeta_existente:
        # Idempotente: devuelve la tarjeta existente en lugar de crear otra
        return tarjeta_existente

    # ── Verificar si es la PRIMERA tarjeta de esta cuenta (cualquier estado) ─
    cantidad_tarjetas_previas = (
        db.query(Tarjeta)
        .filter(Tarjeta.id_cuenta == payload.id_cuenta)
        .count()
    )
    es_primera_tarjeta = cantidad_tarjetas_previas == 0

    # ── REGLA 5: Datos sensibles generados por backend ──────────────────────
    import random
    numero_tarjeta = "".join([str(random.randint(0, 9)) for _ in range(16)])

    tarjeta = Tarjeta(
        id_cuenta=payload.id_cuenta,
        numero_tarjeta=numero_tarjeta,
        tipo_tarjeta=payload.tipo_tarjeta or "virtual",
        procesador_externo="Visa Direct / BankLite",
        estado="activa",
    )
    db.add(tarjeta)
    db.commit()
    db.refresh(tarjeta)

    # ── BONO DE BIENVENIDA: Solo la primera tarjeta emitida ──────────────────
    if es_primera_tarjeta:
        logger.info(
            "Primera tarjeta emitida para cuenta %s – registrando bono de bienvenida de $2,000,000 COP",
            payload.id_cuenta,
        )
        registrar_bono_bienvenida(str(payload.id_cuenta))

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


@router.get("/{id_tarjeta}/numero")
def revelar_numero_tarjeta(
    id_tarjeta: UUID,
    id_usuario: str,
    db: Session = Depends(get_db)
):
    """Devuelve el número completo de la tarjeta SOLO al propietario autorizado.

    Valida en backend:
    - La tarjeta existe
    - La cuenta a la que pertenece la tarjeta es del id_usuario solicitante
    (tarjeta -> id_cuenta -> account-service -> id_usuario)
    No confía en el frontend: el id_usuario debe coincidir con el dueño real.
    """
    tarjeta = db.query(Tarjeta).filter(Tarjeta.id_tarjeta == id_tarjeta).first()
    if not tarjeta:
        raise HTTPException(status_code=404, detail="Tarjeta no encontrada")

    # Validar que la cuenta pertenece al usuario solicitante
    cuenta = get_account(str(tarjeta.id_cuenta))
    if cuenta is None:
        raise HTTPException(status_code=404, detail="Cuenta asociada no encontrada")
    if str(cuenta.get("id_usuario")) != str(id_usuario):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para ver el número de esta tarjeta.",
        )

    numero = tarjeta.numero_tarjeta or ""
    return {
        "id_tarjeta": str(tarjeta.id_tarjeta),
        "numero_tarjeta": numero,
        "numero_formateado": f"{numero[:4]} {numero[4:8]} {numero[8:12]} {numero[12:]}" if len(numero) == 16 else numero,
    }


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


@router.delete("/{id_tarjeta}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_tarjeta(id_tarjeta: UUID, db: Session = Depends(get_db)):
    """Elimina / anula una tarjeta (solo administrador). Pone estado vencida."""
    tarjeta = db.query(Tarjeta).filter(Tarjeta.id_tarjeta == id_tarjeta).first()
    if not tarjeta:
        raise HTTPException(status_code=404, detail="Tarjeta no encontrada")
    tarjeta.estado = "vencida"
    db.commit()


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
