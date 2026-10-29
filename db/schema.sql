-- Esquema de card-service (PostgreSQL). Generado a partir de los modelos SQLAlchemy.
-- Tambien se crea solo al arrancar el servicio (Base.metadata.create_all).

CREATE TABLE tarjeta (
	id_tarjeta UUID NOT NULL, 
	numero_tarjeta VARCHAR(16), 
	id_cuenta UUID NOT NULL, 
	tipo_tarjeta VARCHAR(50) NOT NULL, 
	procesador_externo VARCHAR(100) NOT NULL, 
	bin_marca VARCHAR(50), 
	bin_banco VARCHAR(120), 
	bin_pais VARCHAR(60), 
	bin_tipo VARCHAR(30), 
	estado VARCHAR(20) NOT NULL, 
	fecha_emision TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id_tarjeta), 
	CONSTRAINT chk_tarjeta_estado CHECK (estado IN ('activa', 'bloqueada', 'vencida', 'congelada')), 
	UNIQUE (numero_tarjeta)
);
CREATE INDEX ix_tarjeta_id_cuenta ON tarjeta (id_cuenta);

CREATE TABLE autorizacion (
	id_autorizacion UUID NOT NULL, 
	id_tarjeta UUID NOT NULL, 
	monto NUMERIC(12, 2) NOT NULL, 
	comercio VARCHAR(150) NOT NULL, 
	resultado VARCHAR(20) NOT NULL, 
	fecha_hora TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id_autorizacion), 
	CONSTRAINT chk_autorizacion_monto_positivo CHECK (monto > 0), 
	CONSTRAINT chk_autorizacion_resultado CHECK (resultado IN ('aprobada', 'rechazada')), 
	FOREIGN KEY(id_tarjeta) REFERENCES tarjeta (id_tarjeta)
);
CREATE INDEX idx_autorizacion_fecha ON autorizacion (fecha_hora);
CREATE INDEX idx_autorizacion_tarjeta ON autorizacion (id_tarjeta);

CREATE TABLE bloqueo (
	id_bloqueo UUID NOT NULL, 
	id_tarjeta UUID NOT NULL, 
	motivo VARCHAR(255) NOT NULL, 
	fecha_inicio TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	fecha_fin TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id_bloqueo), 
	FOREIGN KEY(id_tarjeta) REFERENCES tarjeta (id_tarjeta)
);
CREATE INDEX idx_bloqueo_tarjeta ON bloqueo (id_tarjeta);
