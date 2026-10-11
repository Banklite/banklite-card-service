import logging
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import Base, engine, get_db
from .models import Tarjeta
from .routers import cards

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(settings.service_name)

from sqlalchemy import text

def _rellenar_numeros_tarjeta() -> None:
    """Asigna numero_tarjeta (16 digitos unicos) a tarjetas antiguas con NULL."""
    import random
    from .database import SessionLocal
    from .models import Tarjeta

    with SessionLocal() as db:
        pendientes = db.query(Tarjeta).filter(Tarjeta.numero_tarjeta.is_(None)).all()
        usados = {n for (n,) in db.query(Tarjeta.numero_tarjeta).filter(Tarjeta.numero_tarjeta.isnot(None))}
        for t in pendientes:
            while True:
                n = "".join(str(random.randint(0, 9)) for _ in range(16))
                if n not in usados:
                    usados.add(n)
                    t.numero_tarjeta = n
                    break
        db.commit()
        if pendientes:
            logger.info("Numero asignado a %d tarjetas antiguas", len(pendientes))


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    # Migración idempotente: agregar numero_tarjeta si no existe
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE tarjeta ADD COLUMN IF NOT EXISTS numero_tarjeta VARCHAR(16);"))
    # Migración idempotente: permitir el estado 'congelada' en el CHECK de estado
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE tarjeta DROP CONSTRAINT IF EXISTS chk_tarjeta_estado;"))
        conn.execute(text(
            "ALTER TABLE tarjeta ADD CONSTRAINT chk_tarjeta_estado CHECK "
            "(estado IN ('activa','bloqueada','vencida','congelada'));"
        ))
    _rellenar_numeros_tarjeta()
    logger.info("%s iniciado en puerto %d", settings.service_name, settings.api_port)
    yield

app = FastAPI(
    title="BankLite - Card Service",
    description="Microservicio de Emisión y Administración de Tarjetas (Físicas/Virtuales) y Autorizaciones de Transacciones.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cards.router)

@app.get("/health", tags=["infra"])
def health():
    return {"status": "ok", "service": settings.service_name}


@app.get("/stats", tags=["infra"])
def stats(db: Session = Depends(get_db)):
    return {
        "total_tarjetas": db.execute(select(func.count()).select_from(Tarjeta)).scalar(),
        "tarjetas_activas": db.execute(
            select(func.count()).select_from(Tarjeta).where(Tarjeta.estado == "activa")
        ).scalar(),
    }


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Error no controlado en %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Error interno en Card Service"},
    )
