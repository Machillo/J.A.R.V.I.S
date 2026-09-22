# Fase 1 — contrato de cierre

La Fase 1 termina cuando un hallazgo financiero pasa por esta secuencia:

1. Gmail/PDF se ingiere bajo consentimiento y retención limitada.
2. Un parser determinista produce un candidato canónico.
3. Identidad financiera y deduplicación resuelven cuenta y coincidencias.
4. El usuario confirma, corrige o rechaza el candidato.
5. Una confirmación crea exactamente una fila en `transactions`.
6. La misma transacción publica `transaction_confirmed` con contrato
   `financial-input-v1` y crea una notificación idempotente.

`financial-input-v1` contiene únicamente hechos normalizados. No incluye cuerpo
del correo, remitente, asunto, texto de adjuntos ni evidencia cruda del parser.
Las fases posteriores deben consumir este contrato o `transactions`, nunca las
tablas de ingestión Gmail.
