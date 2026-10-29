-- Datos de ejemplo de card-service. Ejecutar despues de schema.sql.
INSERT INTO tarjeta (id_tarjeta, numero_tarjeta, id_cuenta, tipo_tarjeta, procesador_externo, estado, fecha_emision) VALUES
 ('70000000-0000-0000-0000-000000000001','4411190000000001','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1','virtual','Visa Direct / BankLite','activa',now())
ON CONFLICT DO NOTHING;
INSERT INTO autorizacion (id_autorizacion, id_tarjeta, monto, comercio, resultado, fecha_hora) VALUES
 ('71000000-0000-0000-0000-000000000001','70000000-0000-0000-0000-000000000001',35000,'Tienda de ejemplo','aprobada',now())
ON CONFLICT DO NOTHING;
INSERT INTO bloqueo (id_bloqueo, id_tarjeta, motivo, fecha_inicio, fecha_fin) VALUES
 ('72000000-0000-0000-0000-000000000001','70000000-0000-0000-0000-000000000001','Bloqueo temporal de ejemplo',now() - interval '2 days',now() - interval '1 day')
ON CONFLICT DO NOTHING;
