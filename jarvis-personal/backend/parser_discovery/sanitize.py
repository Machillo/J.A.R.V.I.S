"""Remove personal data from a bank email sample while keeping its layout.

Allow-list design: only generic banking vocabulary survives. Every other word
(names, merchants, free-text details, addresses, domains) becomes "<w>" and
every digit becomes 9, so layout and labels remain but no real value does.
"""
from __future__ import annotations

import re
import unicodedata

EMAIL_RE = re.compile(r"[\w.+\-]+\s*(?:@|\[at\]|\(at\))\s*[\w\-]+(?:\s*\.\s*[\w\-]+)+", re.I)
URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.I)
WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")
SANITIZED_SUFFIX = ".sanitized.txt"

# Generic labels and connectors seen in Costa Rican bank notifications. Never
# add a proper name, merchant or bank-customer word here.
KEEP_WORDS = frozenset("""
a al le les lo la las el los de del en y o u con sin por para que se su sus tu tus es fue ha han hay
un una uno este esta estos estas ese esa usted ustedes nuestro nuestra
hola estimado estimada estimados cliente
banco bac credomatic popular multimoney bn nacional sinpe movil móvil
monto montos total totales saldo saldos disponible cargo cargos abono abonos
compra compras pago pagos transferencia transferencias transaccion transacción transacciones
retiro retiros deposito depósito depositos depósitos debito débito debitos débitos credito crédito creditos créditos
devolucion devolución reversion reversión comision comisión intereses interes interés
fecha fechas hora horas dia día mes año periodo período corte vencimiento
referencia autorizacion autorización comprobante numero número codigo código
comercio ciudad pais país tipo detalle concepto descripcion descripción
nombre remitente destinatario beneficiario tarjetahabiente cedula cédula telefono teléfono
cuenta cuentas origen destino tarjeta tarjetas titular iban
colones colon colón dolares dólares crc usd moneda tipo cambio
estado estados notificacion notificación aviso alerta informa informamos realizada realizado realizo realizó
aplicada aplicado rechazada rechazado exitosa exitoso correspondiente
visa mastercard amex
enero febrero marzo abril mayo junio julio agosto setiembre septiembre octubre noviembre diciembre
ene feb mar abr may jun jul ago set sep oct nov dic
am pm
""".split())


def _fold(word: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", word.lower()) if unicodedata.category(ch) != "Mn")


KEEP_FOLDED = frozenset(_fold(word) for word in KEEP_WORDS)


def sanitize_sample(text: str) -> str:
    """Idempotent: sanitize_sample(sanitize_sample(x)) == sanitize_sample(x)."""
    clean = URL_RE.sub("<url>", text or "")
    clean = EMAIL_RE.sub("<email>", clean)
    clean = re.sub(r"\d", "9", clean)

    def word(match: re.Match) -> str:
        value = match.group(0)
        return value if _fold(value) in KEEP_FOLDED or value in {"url", "email", "w"} else "<w>"

    # Keep the placeholders produced above untouched.
    parts = re.split(r"(<url>|<email>|<w>)", clean)
    return "".join(part if part in {"<url>", "<email>", "<w>"} else WORD_RE.sub(word, part) for part in parts)


def is_sanitized(text: str) -> bool:
    return sanitize_sample(text) == text


def residual_risks(text: str) -> list[str]:
    """A sample may be sent only if sanitizing it again changes nothing."""
    return [] if is_sanitized(text) else ["not produced by sanitize_sample (run the dry run and send its output)"]
