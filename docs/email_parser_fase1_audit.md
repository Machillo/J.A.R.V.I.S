# J.A.R.V.I.S — Email Parser Fase 1

## Objetivo
Convertir correos reales de BAC/MultiMoney/Banco Popular en candidatos financieros verificables, sin guardar transacciones automáticas y sin confundir estados de cuenta/promos/login con gastos.

## Cambios aplicados

### 1. Limpieza real de HTML Gmail
- Se eliminan bloques `<style>`, `<script>`, `<head>` y CSS antes de parsear.
- Esto evita que correos de MultiMoney empiecen con cientos de líneas de CSS y no lleguen a `Monto`, `Fecha` o `Concepto`.

### 2. Clasificación correcta de estados de cuenta
- `email_ingested_messages.status` ahora queda como `statement` para estados de cuenta.
- Se guardan en `email_statement_documents`.
- No generan candidates ni transacciones.

### 3. Auditoría completa
`email_parser_logs` ahora soporta:
- `email_message_id`
- `result`
- `reason`
- `extracted_payload` JSONB

Resultados esperados:
- `pending`
- `duplicate`
- `ignored`
- `statement`
- `error`

### 4. Tarjetas BAC
El parser ya extrae:
- `card_owner` desde saludo: Kenneth / Emily / Sidey
- `card_last4` desde máscara de tarjeta
- `billing_cycle_start` / `billing_cycle_end` usando corte 21 → 21

### 5. Montos cero
Autorizaciones BAC con monto cero se ignoran con razón explícita:
`Autorización BAC con monto cero; no se genera candidato financiero.`

### 6. Dedupe inteligente
Se mantiene:
- dedupe por `dedupe_key`
- dedupe cross-bank para transferencias espejo BAC SINPE ↔ MultiMoney
- `duplicate_of` cuando existe candidato principal

## Flujo esperado

```txt
Gmail
→ decode body limpio
→ email_ingested_messages
→ parse_financial_email
   movement | statement | ignored
→ email_statement_documents si es estado
→ email_transaction_candidates si es movimiento
→ email_parser_logs siempre
```

## Archivos modificados
- `backend/email_monitor/parser.py`
- `backend/email_monitor/service.py`
- `database/schema.sql`

## Validación local realizada
```bash
python -m compileall -q backend
```

También se probaron ejemplos manuales de:
- compra BAC OpenAI
- estado de cuenta BAC
- SINPE BAC
- transferencia MultiMoney
