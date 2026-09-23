# DINCR: auditoría previa a las tiendas

Estado de referencia: `main` del 23 de septiembre de 2026. Esta lista separa las pruebas del repositorio de las verificaciones con cuentas y dispositivos reales. No equivale a aprobación de Google ni Apple.

## Comprobado en el repositorio

- `PYTHONPATH=. python -m pytest backend -q`: 190 pruebas aprobadas en la revisión inicial.
- `npm run build`, `npm run test:navigation`, `npm run test:native-navigation`, `npm run test:product-analytics`: aprobados.
- La eliminación autenticada existe para los planes Free, Basic y VIP. La página pública `/delete-account` documenta cómo solicitarla desde la versión web e incluye la política de privacidad; `npm run test:store-readiness` comprueba el contrato y corre en CI.
- Android configura `targetSdkVersion = 36`. El identificador Android y el de iOS DINCR son `com.finva.app`.
- El escaneo inicial de Gmail cubre el año calendario actual en páginas de 50 correos; no se debe anunciar como análisis automático de los últimos 12 meses.

## Pendiente antes de pagar o abrir las cuentas de desarrollador

1. **Prueba financiera real:** usuario VIP de prueba con Gmail, candidatos, confirmación/rechazo, deduplicación, saldos y estrategia. Registrar casos en los que faltan correos, el parser se equivoca o la distribución no coincide. No usar datos de terceros en capturas ni tickets.
2. **Privacidad pública:** publicar el frontend y abrir desde navegador privado `/privacy`, `/terms` y `/delete-account`; iniciar sesión desde la última página y completar el borrado con una cuenta de prueba prescindible. Verificar la eliminación efectiva de sus datos y el plazo aplicable a copias de respaldo.
3. **Idioma e interfaz:** el auditor de idioma marca 700 textos potenciales en el frontend compartido; revisar primero las pantallas visibles de DINCR Free, Basic y VIP en ambos idiomas, teléfonos pequeños y lector de pantalla. No cerrar el hallazgo por el solo resultado de `npm run build`.
4. **Datos y seguridad:** comprobar en el entorno desplegado las migraciones, aislamiento entre workspaces, consentimientos, desconexión/revocación de Gmail, alertas y restauración. Los tests unitarios no sustituyen esta prueba.
5. **Permisos y artefactos:** construir un AAB de release Android y un archive iOS DINCR firmado; instalar en dispositivos de prueba y verificar inicio, OAuth de Gmail, biometría, notificaciones, borrado y regreso nativo. Verificar el manifiesto final y los SDK incluidos, no solo los archivos fuente.

## Requiere Play Console / App Store Connect o Google Cloud

- Google Play: declaración de funciones financieras, Data Safety, enlace público `/delete-account`, ficha, capturas, clasificación y acceso de revisores; confirmar requisitos de prueba cerrada según el tipo y fecha de creación de la cuenta.
- Google OAuth: revisión del estado de verificación de `gmail.readonly` y si corresponde evaluación de seguridad por el uso de datos de alcance restringido. No habilitar Gmail masivamente hasta resolverlo.
- Apple: ficha, detalles de privacidad, acceso de revisores, TestFlight y envío con la versión exigida de Xcode/SDK. Comprobar los datos declarados contra la app y sus SDK.
- Cuotas o suscripciones: validar el mecanismo de compra y las reglas vigentes de cada tienda antes de ofrecer pagos dentro de la app.

## Fuera del bloqueo inicial de publicación, salvo que se prometa como función v1

- AI Gateway para nuevos documentos bancarios, ledger de costos y prueba con $5: aún no integrados. El presupuesto antiguo de OpenAI no representa este proyecto.
- Reconstrucción automática de exactamente 12 meses y análisis de bancos desconocidos: aún no implementados de punta a punta.

**Cierre:** repetir pruebas y actualizar esta lista con fecha, plataforma, build, resultado y evidencia anonimizada; marcar aprobado solo después de comprobar la app desplegada y las declaraciones reales de ambas tiendas.
