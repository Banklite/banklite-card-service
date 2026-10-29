# Card Service — BankLite

Emision y administracion de tarjetas (fisicas y virtuales), autorizacion de compras contra el ledger, bloqueos y consulta de BIN en proveedor externo.

Parte del proyecto **BankLite** (banca digital con microservicios) de *Arquitectura y Modelamiento de Software*, Universidad Cooperativa de Colombia. Cada microservicio tiene su propio repositorio y su propia base de datos (`card_db`).

## Responsabilidad en la arquitectura

Emision y administracion de tarjetas (fisicas y virtuales), autorizacion de compras contra el ledger, bloqueos y consulta de BIN en proveedor externo. Se comunica con los demas servicios por **REST** (operaciones que necesitan respuesta inmediata) y por **eventos** en RabbitMQ (exchange `banklite.events`, tipo topic).

| Eventos publicados | Eventos consumidos |
|---|---|
| `card.transaction.authorized` | — |

## Tecnologias

FastAPI, SQLAlchemy, PostgreSQL, RabbitMQ (pika). Externo: handyapi / binlist (consulta de BIN). Python 3.12, Docker.

## Despliegue

- URL publica: <https://banklite-card-service.onrender.com>
- Salud: <https://banklite-card-service.onrender.com/health>
- Documentacion interactiva (Swagger): <https://banklite-card-service.onrender.com/docs>

Desplegado en Render (plan gratuito: tarda hasta ~1 minuto en responder si estuvo inactivo). Las credenciales se configuran como variables de entorno en la plataforma, no en el codigo.

## Endpoints principales

| Metodo | Ruta | Descripcion |
|---|---|---|
| `POST` | `/cards/solicitar` | Solicita una tarjeta (requiere KYC aprobado) |
| `GET` | `/cards` | Lista tarjetas |
| `GET` | `/cards/{id}` | Detalle de una tarjeta |
| `POST` | `/cards/{id}/bloquear` | Bloqueo de la tarjeta |
| `POST` | `/cards/{id}/desbloquear` | Desbloqueo |
| `PATCH` | `/cards/{id}/toggle-freeze` | Congelar / descongelar |
| `POST` | `/cards/autorizar` | Autoriza una compra (debita el ledger) |
| `GET` | `/cards/{id}/autorizaciones` | Historial de autorizaciones |
| `GET` | `/health` | Estado del servicio |
| `GET` | `/stats` | Contadores del servicio |

La lista completa esta en `/docs`.

## Variables de entorno

Copia `.env.example` a `.env` y completa los valores.

| Variable | Descripcion |
|---|---|
| `DATABASE_URL` | Conexion PostgreSQL |
| `ACCOUNT_SERVICE_URL` | URL de account-service |
| `IDENTITY_SERVICE_URL` | URL de identity-service |
| `LEDGER_SERVICE_URL` | URL de ledger-service |
| `CARD_BIN_PREFIX` | Prefijo BIN al emitir |
| `RABBITMQ_URL` | URL del bus de eventos |
| `ENABLE_EVENTS` | Publicar eventos |

## Base de datos

Motor: PostgreSQL. Base: `card_db`.

- `db/schema.sql`: creacion de tablas, indices y restricciones.
- `db/seed.sql`: datos de ejemplo.

El servicio tambien crea las tablas solo al arrancar (`create_all`). Para restaurar a mano:

```bash
createdb card_db
psql -d card_db -f db/schema.sql
psql -d card_db -f db/seed.sql
```

Respaldo completo (para entregar o restaurar): `pg_dump -Fc card_db > card_db.dump` y `pg_restore -d card_db card_db.dump`.

## Instalacion y ejecucion

Con Docker:

```bash
docker build -t banklite-card-service .
docker run --env-file .env -p 8005:8005 -e PORT=8005 banklite-card-service
```

Sin Docker:

```bash
python -m venv .venv && source .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8005
```

Prueba: abre <http://localhost:8005/docs>.

## Repositorios del proyecto

`banklite-identity-service`, `banklite-account-service`, `banklite-ledger-service`, `banklite-transfer-service`, `banklite-card-service`, `banklite-fraud-service`, `banklite-notification-service`, `banklite-compliance-service`. Panel web: `services/web-panel` en el repositorio `banklite-microservicios`.
