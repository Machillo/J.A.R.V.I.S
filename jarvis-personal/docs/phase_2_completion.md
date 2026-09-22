# Fase 2 — cierre funcional

DINCR convierte el historial financiero confirmado en retención útil para VIP:

1. `financial-state-v1` resume flujo, patrimonio, deuda, fondo de emergencia,
   metas, salud y estrategia sin depender del origen Gmail/PDF.
2. Un snapshot diario idempotente conserva el estado longitudinal.
3. Las comparaciones de 30/90/180/365 días explican progreso y desviaciones.
4. La revisión mensual compara plan contra realidad y propone la prioridad del
   mes siguiente.
5. El asesor proactivo detecta deterioro, cambios de estrategia y logros.
6. Cada alerta material se encola una sola vez en `notification_jobs`, de modo
   que DINCR pueda buscar al usuario aunque este no abra primero la pantalla.

El payload de la notificación contiene solo código, severidad y navegación. No
transporta estados financieros completos ni evidencia cruda de Fase 1.
