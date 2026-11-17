"""Pruebas de INTEGRACION de card-service: endpoint + reglas de negocio + base de datos.

La base es SQLite en memoria. Los otros microservicios (identity, account, ledger),
el proveedor de BIN y RabbitMQ se reemplazan con mocks.
"""
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.ledger_client import LedgerRejected, LedgerUnavailable
from app.models import Autorizacion, Bloqueo, Tarjeta

ID_USUARIO, ID_CUENTA = uuid.uuid4(), uuid.uuid4()
BIN = {"marca": "visa", "banco": "BankLite", "pais": "Colombia", "tipo": "debit"}


@pytest.fixture(autouse=True)
def externos():
    """Mocks de todo lo que queda fuera de card-service."""
    with (
        patch("app.routers.cards.get_user", return_value={"estado": "verificado"}) as get_user,
        patch("app.routers.cards.get_account", return_value={"estado": "activa", "id_usuario": str(ID_USUARIO)}) as get_account,
        patch("app.routers.cards.consultar_bin", return_value=BIN),
        patch("app.routers.cards.saldo_cuenta", return_value=Decimal("500000")) as saldo,
        patch("app.routers.cards.cobrar_compra") as cobrar,
        patch("app.routers.cards.publish_event", return_value=True) as publicar,
    ):
        yield {"get_user": get_user, "get_account": get_account, "saldo": saldo, "cobrar": cobrar, "publicar": publicar}


def _solicitar(client):
    return client.post("/cards/solicitar", json={"id_usuario": str(ID_USUARIO), "id_cuenta": str(ID_CUENTA)})


# --- Solicitud de tarjeta por el cliente -----------------------------------------------------

def test_cliente_verificado_recibe_tarjeta_y_queda_en_la_base(client, sesiones):
    r = _solicitar(client)

    assert r.status_code == 201
    tarjeta = r.json()
    assert tarjeta["estado"] == "activa" and tarjeta["tipo_tarjeta"] == "virtual"
    assert len(tarjeta["numero_tarjeta"]) == 16 and tarjeta["numero_tarjeta"].startswith("441119")
    assert tarjeta["bin_marca"] == "visa"
    with sesiones() as db:
        assert db.query(Tarjeta).filter(Tarjeta.id_cuenta == ID_CUENTA).count() == 1


def test_solicitar_dos_veces_devuelve_la_misma_tarjeta(client, sesiones):
    primera = _solicitar(client).json()
    segunda = _solicitar(client).json()

    assert primera["id_tarjeta"] == segunda["id_tarjeta"]
    with sesiones() as db:
        assert db.query(Tarjeta).count() == 1


def test_usuario_sin_kyc_no_puede_pedir_tarjeta(client, externos, sesiones):
    externos["get_user"].return_value = {"estado": "pendiente", "estado_kyc": "pendiente"}

    r = _solicitar(client)

    assert r.status_code == 403
    with sesiones() as db:
        assert db.query(Tarjeta).count() == 0


def test_no_se_emite_tarjeta_sobre_la_cuenta_de_otro_usuario(client, externos):
    externos["get_account"].return_value = {"estado": "activa", "id_usuario": str(uuid.uuid4())}
    assert _solicitar(client).status_code == 403


@pytest.mark.parametrize(
    "usuario, cuenta, esperado",
    [
        (None, {"estado": "activa"}, 404),                              # usuario inexistente
        ({"estado": "verificado"}, None, 404),                          # cuenta inexistente
        ({"estado": "verificado"}, {"estado": "suspendida"}, 409),      # cuenta no activa
    ],
)
def test_validaciones_de_usuario_y_cuenta(client, externos, usuario, cuenta, esperado):
    externos["get_user"].return_value = usuario
    externos["get_account"].return_value = cuenta
    assert _solicitar(client).status_code == esperado


# --- Autorizacion de compras -----------------------------------------------------------------

def _autorizar(client, id_tarjeta, monto=120000):
    return client.post("/cards/autorizar", json={"id_tarjeta": id_tarjeta, "monto": monto, "comercio": "Exito Monteria"})


def test_compra_con_saldo_se_aprueba_se_cobra_y_se_publica_el_evento(client, externos, sesiones):
    id_tarjeta = _solicitar(client).json()["id_tarjeta"]

    r = _autorizar(client, id_tarjeta)

    assert r.status_code == 200 and r.json()["resultado"] == "aprobada"
    # Se cobro en el ledger con la referencia de la autorizacion
    referencia, cuenta, monto = externos["cobrar"].call_args.args
    assert referencia == r.json()["id_autorizacion"] and cuenta == ID_CUENTA and monto == Decimal("120000")
    # Se aviso al resto del sistema (comunicacion asincrona)
    evento, datos = externos["publicar"].call_args.args
    assert evento == "card.transaction.authorized" and datos["resultado"] == "aprobada"
    with sesiones() as db:
        assert db.query(Autorizacion).one().resultado == "aprobada"


def test_compra_sin_fondos_se_rechaza_y_no_se_cobra(client, externos):
    externos["saldo"].return_value = Decimal("1000")
    id_tarjeta = _solicitar(client).json()["id_tarjeta"]

    r = _autorizar(client, id_tarjeta)

    assert r.json()["resultado"] == "rechazada"
    externos["cobrar"].assert_not_called()


def test_tarjeta_bloqueada_rechaza_la_compra_sin_consultar_saldo(client, externos, sesiones):
    id_tarjeta = _solicitar(client).json()["id_tarjeta"]
    bloqueo = client.post(f"/cards/{id_tarjeta}/bloquear", json={"motivo": "Reporte de robo"})
    assert bloqueo.status_code == 201

    r = _autorizar(client, id_tarjeta)

    assert r.json()["resultado"] == "rechazada"
    externos["saldo"].assert_not_called()
    with sesiones() as db:
        assert db.query(Bloqueo).one().motivo == "Reporte de robo"


def test_si_el_ledger_no_responde_no_se_aprueba_ni_se_guarda(client, externos, sesiones):
    id_tarjeta = _solicitar(client).json()["id_tarjeta"]
    externos["cobrar"].side_effect = LedgerUnavailable("timeout")

    r = _autorizar(client, id_tarjeta)

    assert r.status_code == 503
    with sesiones() as db:
        assert db.query(Autorizacion).count() == 0
    externos["publicar"].assert_not_called()


def test_rechazo_del_ledger_se_propaga_con_su_codigo(client, externos):
    id_tarjeta = _solicitar(client).json()["id_tarjeta"]
    externos["cobrar"].side_effect = LedgerRejected(409, "La cuenta no esta activa")
    assert _autorizar(client, id_tarjeta).status_code == 409


def test_saldo_no_disponible_responde_503(client, externos):
    id_tarjeta = _solicitar(client).json()["id_tarjeta"]
    externos["saldo"].side_effect = LedgerUnavailable("sin red")
    assert _autorizar(client, id_tarjeta).status_code == 503


def test_autorizar_tarjeta_inexistente_responde_404(client):
    assert _autorizar(client, str(uuid.uuid4())).status_code == 404


def test_historial_de_autorizaciones(client):
    id_tarjeta = _solicitar(client).json()["id_tarjeta"]
    _autorizar(client, id_tarjeta, 1000)
    _autorizar(client, id_tarjeta, 2000)

    assert len(client.get(f"/cards/{id_tarjeta}/autorizaciones").json()) == 2
    assert len(client.get("/cards/all/autorizaciones").json()) == 2


# --- Ciclo de vida de la tarjeta -------------------------------------------------------------

def test_bloquear_y_desbloquear_cierra_el_bloqueo(client):
    id_tarjeta = _solicitar(client).json()["id_tarjeta"]
    client.post(f"/cards/{id_tarjeta}/bloquear", json={"motivo": "Sospecha de fraude"})
    assert client.get(f"/cards/{id_tarjeta}").json()["estado"] == "bloqueada"

    r = client.post(f"/cards/{id_tarjeta}/desbloquear")

    assert r.json()["estado"] == "activa"
    assert r.json()["bloqueos"][0]["fecha_fin"] is not None


def test_congelar_y_descongelar(client):
    id_tarjeta = _solicitar(client).json()["id_tarjeta"]
    assert client.patch(f"/cards/{id_tarjeta}/toggle-freeze").json()["estado"] == "congelada"
    assert client.patch(f"/cards/{id_tarjeta}/toggle-freeze").json()["estado"] == "activa"


def test_anular_tarjeta_la_deja_vencida_y_ya_no_se_puede_congelar(client):
    id_tarjeta = _solicitar(client).json()["id_tarjeta"]

    assert client.delete(f"/cards/{id_tarjeta}").status_code == 204

    assert client.get(f"/cards/{id_tarjeta}").json()["estado"] == "vencida"
    assert client.patch(f"/cards/{id_tarjeta}/toggle-freeze").status_code == 400


def test_solo_el_dueno_puede_ver_el_numero_completo(client, externos):
    tarjeta = _solicitar(client).json()

    propio = client.get(f"/cards/{tarjeta['id_tarjeta']}/numero", params={"id_usuario": str(ID_USUARIO)})
    ajeno = client.get(f"/cards/{tarjeta['id_tarjeta']}/numero", params={"id_usuario": str(uuid.uuid4())})

    assert propio.status_code == 200 and propio.json()["numero_tarjeta"] == tarjeta["numero_tarjeta"]
    assert len(propio.json()["numero_formateado"].split()) == 4
    assert ajeno.status_code == 403


def test_emision_por_administrador_y_listado_por_cuenta(client):
    otra_cuenta = str(uuid.uuid4())
    r = client.post("/cards/", json={"id_cuenta": otra_cuenta, "tipo_tarjeta": "fisica"})
    _solicitar(client)

    assert r.status_code == 201 and r.json()["tipo_tarjeta"] == "fisica"
    assert len(client.get("/cards/").json()) == 2
    assert len(client.get("/cards/", params={"id_cuenta": otra_cuenta}).json()) == 1
    assert client.get("/stats").json() == {"total_tarjetas": 2, "tarjetas_activas": 2}


@pytest.mark.parametrize("ruta, metodo", [
    ("/cards/{id}", "get"), ("/cards/{id}/desbloquear", "post"), ("/cards/{id}/toggle-freeze", "patch"), ("/cards/{id}", "delete"),
])
def test_tarjeta_inexistente_responde_404(client, ruta, metodo):
    r = getattr(client, metodo)(ruta.format(id=uuid.uuid4()))
    assert r.status_code == 404
