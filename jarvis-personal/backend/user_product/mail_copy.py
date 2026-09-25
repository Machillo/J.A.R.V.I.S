"""English presentation of the reasons stored with each imported email.

Parsers store their explanation in Spanish (``finva_email_messages.parse_reason``),
often from background syncs that have no request language. The stored value
stays canonical; English responses translate it here, deterministically.
"""
from __future__ import annotations

import re

from backend.core.i18n import current_language

ENGLISH_REASONS = {
    "Ambos extremos pertenecen al mismo workspace.": "Both ends belong to the same workspace.",
    "Autorización BAC con monto cero; no se genera candidato financiero.": "BAC authorization for zero; no financial candidate is created.",
    "BAC SINPE Móvil: ingreso, pagador, monto, fecha y referencia extraídos por plantilla exacta.": "BAC SINPE Móvil: income, payer, amount, date, and reference extracted with an exact template.",
    "BAC SINPE: dirección, monto, referencia, cuentas y fecha extraídos por plantilla exacta.": "BAC SINPE: direction, amount, reference, accounts, and date extracted with an exact template.",
    "BAC compra: comercio, fecha, tipo, tarjeta, ciclo y monto extraídos por plantilla exacta.": "BAC purchase: merchant, date, type, card, cycle, and amount extracted with an exact template.",
    "BAC depósito: monto, fecha y remitente extraídos por plantilla alerta.": "BAC deposit: amount, date, and sender extracted with the alert template.",
    "BAC pago de servicio: monto, fecha y servicio extraídos por plantilla alerta.": "BAC bill payment: amount, date, and service extracted with the alert template.",
    "Comprobante SINPE oficial; pendiente confirmar contraparte o cuenta propia.": "Official SINPE receipt; the counterparty or own account still needs confirmation.",
    "Comprobante oficial de cuota Popular; requiere revisar posible rebajo de planilla.": "Official Banco Popular payment receipt; check for a possible payroll deduction.",
    "Correo bancario sin plantilla confiable. No se genera candidato.": "Bank email without a reliable template. No candidate is created.",
    "Correo promocional/login/seguridad/informativo; no es movimiento de dinero.": "Promotional, sign-in, security, or informational email; not a money movement.",
    "Depósito salarial aplicado: ingreso bancario con referencia explícita a salario/planilla/nómina.": "Salary deposit applied: bank income with an explicit salary or payroll reference.",
    "Estado de cuenta detectado, pero el formato todavía no tiene filas firmadas compatibles.": "Statement detected, but its format doesn’t have compatible signed rows yet.",
    "Estado de cuenta detectado; pendiente de lectura/conciliación de PDF.": "Statement detected; PDF reading or reconciliation is pending.",
    "Estado de cuenta listo para procesar.": "Statement ready to process.",
    "Movimiento MultiMoney rechazado/no aplicado; no afecta finanzas.": "MultiMoney transaction rejected or not applied; it doesn’t affect your finances.",
    "Movimiento entre cuentas propias detectado en alerta BAC; no se genera candidato financiero.": "Transfer between your own accounts detected in a BAC alert; no financial candidate is created.",
    "Movimiento espejo de una transferencia interna ya detectada; no se genera candidato financiero.": "Mirror of an internal transfer already detected; no financial candidate is created.",
    "Movimiento interno BAC/MultiMoney o inversión propia detectada; no se genera candidato financiero.": "Internal BAC/MultiMoney movement or own investment detected; no financial candidate is created.",
    "Movimiento interno entre cuentas propias detectado; no se genera candidato financiero.": "Internal transfer between your own accounts detected; no financial candidate is created.",
    "MultiMoney: concepto, monto, fecha, dirección y cuentas extraídos por plantilla exacta.": "MultiMoney: description, amount, date, direction, and accounts extracted with an exact template.",
    "No es un correo de BAC, Banco Popular o MultiMoney.": "Not an email from BAC, Banco Popular, or MultiMoney.",
    "No se pudo procesar este aviso. Quedó registrado y se reintenta si vuelve a aparecer en una sincronización.": "We couldn’t process this notice. It was recorded and is retried if it shows up again in a sync.",
    "Pago de tarjeta BAC detectado; se ignora para evitar doble conteo porque las compras individuales ya son los gastos.": "BAC card payment detected; ignored to avoid double counting because the individual purchases are already the expenses.",
    "Pago/depósito BAC rechazado/no aplicado; no afecta finanzas.": "BAC payment or deposit rejected or not applied; it doesn’t affect your finances.",
    "Salario bruto oficial guardado desde Orden Patronal CCSS.": "Official gross salary saved from a CCSS payroll order.",
    "Transferencia SINPE Móvil rechazada/no aplicada; no afecta finanzas.": "SINPE Móvil transfer rejected or not applied; it doesn’t affect your finances.",
    "Transferencia SINPE rechazada/no aplicada; no afecta finanzas.": "SINPE transfer rejected or not applied; it doesn’t affect your finances.",
    "Transferencia entre cuentas propias reconocida por el perfil privado.": "Transfer between your own accounts recognized by your private profile.",
}
_PAYROLL = re.compile(r"^Orden patronal CCSS (\d{4}-\d{2}) procesada\.$")
_STATEMENT = re.compile(r"^Estado de cuenta procesado: (\d+) movimiento\(s\) listos para revisión\.$")
UNKNOWN_REASON = "DINCR processed this email."


def localized_parse_reason(value: str | None) -> str | None:
    """Stored parse reason in the response language (canonical Spanish is kept)."""
    if not value or current_language() == "es":
        return value
    if value in ENGLISH_REASONS:
        return ENGLISH_REASONS[value]
    if match := _PAYROLL.match(value):
        return f"CCSS payroll order {match.group(1)} processed."
    if match := _STATEMENT.match(value):
        count = int(match.group(1))
        return f"Statement processed: {count} {'transaction' if count == 1 else 'transactions'} ready for review."
    return UNKNOWN_REASON
