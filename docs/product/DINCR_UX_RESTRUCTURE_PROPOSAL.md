# DINCR: reestructuración de la experiencia (decisiones de producto aprobadas)

**Base auditada:** `main` `7478fb91`, código real de:
- iOS (SwiftUI);
- Android (Compose);
- web (React);
- backend (FastAPI);
- `native/feature-reachability.json`, el spec de alcance con 40 funciones;
- `DINCR_UNIVERSE_AUDIT_2026-10-02.md` y `DINCR_MASTER_RECOVERY_PLAN_2026-10-02.md` (D1–D20, R1, P-1).

**Fecha:** 2026-10-04.

**Estado:** **APPROVED PRODUCT DECISIONS** (UX-1 a UX-16, K-1 a K-7, más deudas automáticas, regla visual y Owner), con el diseño y el plan consolidados.
- Nada implementado: sin commits, sin PR, sin migraciones, sin escrituras en producción.
- Ninguna función eliminada ni oculta; #319 sin tocar.

---

## 0. Regla central de DINCR

> **El usuario registra HECHOS. DINCR hace el trabajo financiero.**
> **Un dato se ingresa una vez y todo DINCR lo reutiliza.**
> DINCR puede ser compleja por dentro, pero debe sentirse extremadamente simple por fuera.

**Lo que el usuario ingresa o corrige** (idealmente, nada más):

| Hecho | Hogar único |
|---|---|
| Ingresos no detectados | Movimientos → "+" |
| Gastos no detectados | Movimientos → "+" |
| Deudas | Plan → Deudas |
| Ahorros y cuentas | Patrimonio → Cuentas |
| Correcciones | En el propio dato: movimiento, cuenta, deuda o meta |
| Pagos fijos (UX-9) | Plan → Pagos fijos |
| *Owner:* cuentas por cobrar | Patrimonio → Cuentas por cobrar |

**Todo lo demás se deriva:**
- disponible;
- situación financiera;
- prioridad;
- plan del mes;
- Salvavidas;
- proyecciones;
- salud;
- patrimonio.

El usuario puede cambiar la **prioridad** (UX-8) y la **meta del Salvavidas** en meses, pero nunca se le pide volver a escribir un dato que DINCR ya tiene.

**Restricciones que se respetan en todo el documento:**
- **R1:** ninguna función se elimina, oculta ni queda inaccesible sin decisión explícita. Moverla exige actualizar el spec de alcance y que una persona ponga la etiqueta `reachability-change-approved`.
- **P-1:** representar o corregir la propia realidad nunca se cobra.
- **Invariantes A–F** de CLAUDE.md: Users ≠ Owner, tenancy, las lecturas no mutan, desconocido ≠ 0, sin IA generativa, privacidad.

---

## 1. Decisiones aprobadas

| # | Decisión aprobada | Efecto en el diseño |
|---|---|---|
| **UX-1** | El onboarding **no pide** ingreso ni objetivo estimados. DINCR aprende de datos reales. | No hay paso financiero nuevo. **Verificado:** el paso actual "¿Qué querés lograr?" (`usage_goal`) se guarda pero **ningún motor lo lee**. Se conserva solo como personalización, con un test que impide que un motor lo use. |
| **UX-2** | La selección de bancos sale del onboarding. Nace **CUENTAS**: Agregar cuenta → buscar institución → elegir → agregar cuentas → administrar conexiones, más "Agregar cuenta sin conectar". "Conectar correo" se mueve aquí. Nunca fingir conexión bancaria. | Modelo **Institución → Cuenta → Fuente** (correo/parser, manual, futuras integraciones reales). Cuentas es la fuente de verdad de las instituciones del usuario y puede orientar al parser. Ver §6.4. |
| **UX-3** | **Opción B:** una sola **experiencia**, "Tu plan del mes" (Salvavidas · Deudas · Metas · Ahorro/inversión · Disponible), con "Por qué DINCR recomienda esto". **No se eliminan** motores, historia ni capacidades. | Los dos endpoints actuales siguen intactos; cambia la presentación (§6.3). |
| **UX-4** | Las deudas **se administran en Plan**: crear, editar, corregir, pagos, estrategia, próximos pagos. **Patrimonio** usa esas mismas deudas, con un **donut** de composición interactivo. | Una sola fuente y dos vistas (§6.3, §6.4). |
| **Regla visual** | La app es bella, moderna y fácil de leer. Cada gráfico debe ayudar a entender más rápido; nunca es decoración. | Sistema visual en §5. |
| **UX-5** | Las alertas viven en **Hoy → Para atender** (máximo 3 y "Ver todas"). Cuatro lenguajes visuales distintos: **Error técnico / Para atender / Oportunidad / Positivo**. | **Causa encontrada:** las alertas financieras usan el mismo componente y tono que los fallos técnicos (§2.2). |
| **UX-6** | Hoy tiene unos 4 bloques que responden en 5 segundos: ¿Cómo estoy? ¿Qué puedo gastar? ¿Hay algo que atender? ¿Qué viene? El análisis profundo vive en **Movimientos**. | §6.1. |
| **Movimientos** | Análisis visual profundo sin perder nada: ingresos y gastos, evolución, categorías, meses, comercios, tendencias, filtros por período, cuenta y categoría. | §6.2. |
| **UX-7** | Desaparece la **necesidad** de la pantalla Situación: cada dato va a su hogar y DINCR construye la situación. | La pantalla se retira solo cuando cada campo tenga hogar con paridad (§6.6, matriz H). |
| **UX-8** | **Opción B:** DINCR **propone** la prioridad con datos reales, explica por qué y deja cambiarla. No se pregunta repetidamente. | §6.3. Requiere backend y lógica canónica (§12). |
| **UX-9** | **Free** registra y mantiene sus pagos fijos. Se monetiza la inteligencia: calendario avanzado, anticipación, automatización, recordatorios. | Cambio de gate en el backend y en el spec (`profile.recurring`: Free pasa de HIDDEN a AVAILABLE). |
| **Deudas automáticas** | El Owner tiene amortización automática; VIP la tiene como **opt-in por deuda** ("Actualizar deuda automáticamente"), solo con datos completos. Cuota = capital + intereses + otros. **Cuota programada ≠ pago confirmado.** Conciliar con evidencia. No inventar pagos. | **Requiere diseño técnico previo** (§8). **Hallazgo:** el comando Owner existente asume que la cuota quedó pagada al llegar la fecha (§2.2 B5). |
| **UX-10/11** | La app comercial es **iOS + Android**. **Vercel = laboratorio interno** de Kenneth. La **landing** es otra cosa. No hay paridad comercial entre web y nativo. | §9. |
| **UX-12** | "Mi plan" pasa a llamarse **"Suscripción"**. "Plan" queda solo para la planificación financiera. | Cambio de texto. |
| **UX-13** | La pestaña **DINCR** se retira **solo** cuando el gate función → nueva ubicación → paridad verificada esté completo. Si una función queda sin destino, el retiro se bloquea. | §11. |
| **UX-14** | Las **proyecciones** completas viven en **Patrimonio**, en forma visual (3 meses, 6 meses, 1 año, escenarios). Hoy solo avisa ante un cambio realmente relevante. | §6.4. |
| **UX-15** | La **salud /100** vive en **Patrimonio → Análisis**: visual, explicable y accionable. **No se presenta un único puntaje como verdad** hasta tener un cálculo canónico (P3.7). | Queda una decisión de transición (K-2, §14). |
| **UX-16** | Lenguaje cotidiano. Lo técnico va detrás de ⓘ. **Simplificar sin cambiar el significado.** | El glosario de §5.3 requiere validar la semántica de cada término. |
| **Owner** | No es un menú gigante. Sus capacidades financieras viven en las 5 pestañas, JARVIS conserva lo personal o histórico, Administración lo administrativo. Cuentas por cobrar es solo Owner. | §7. |
| **Gate de preservación** | Matriz exhaustiva con estados MOVED / MERGED / CONTEXTUAL / OWNER / ADMINISTRATION / HISTORICAL_RECOVERY_PENDING. **No existe** "borrar por falta de uso" ni "ocultar por complejo". | §10. |

---

## 2. Punto de partida

### 2.1 Problemas de la auditoría anterior (resumen)
- **Navegación:**
  - la pestaña "DINCR" es ambigua;
  - hay dos "Hoy";
  - las funciones financieras están en Perfil;
  - Deudas y Metas están en Hoy;
  - no existe Patrimonio para Users;
  - las rutas son profundas: Perfil → Cuentas → banco → cuenta → corregir.
- **Gating de tres formas** (fila bloqueada, fila oculta o pantalla de bloqueo), y avisos que piden datos que el plan no permite editar.
- **Datos pedidos varias veces:**
  - ahorro (Situación y Salvavidas);
  - meta de emergencia (monto en un lugar, meses en otro);
  - prioridad (3 lugares);
  - ingreso (5 fuentes);
  - esenciales (3–4 lugares);
  - "¿es mía?" (2 lugares);
  - categoría (lista fija contra texto libre);
  - preferencias no editables pese a la promesa "podés cambiarlo después".
- **La misma información en muchos lugares:** prioridad, "podés gastar", plan de deudas (5 lugares), cifras del Salvavidas (3).
- **Pantallas densas:** Director VIP con hasta 10 tarjetas.
- **Jerga visible.**
- **JARVIS:** 9 filas, 6 "en restauración".
- **Web:** metas VIP de solo lectura, Free sin acceso a planes de ahorro, rutas muertas.

### 2.2 Hallazgos nuevos de esta revisión (verificados en el código)
| # | Hallazgo | Evidencia | Consecuencia |
|---|---|---|---|
| **B1** | **Las alertas financieras se ven como errores técnicos.** Usan el mismo `StatusBanner` que "Servicio con demoras", "Cambios temporalmente pausados" o "No pudimos cargar tu cuenta". En iOS, la severidad `high` usa el tono **`.error`**. Android no tiene tono positivo: `success` se muestra como INFO. | iOS `AdvisorViews.swift:262-287`, `PlanDashboards.swift:128`; Android `HomeScreen.kt:179`, `AdvisorScreens.kt:175-184`, `MainScaffold.kt:179-183` | UX-5 exige cuatro tonos: falta crear los componentes de tono en ambos sistemas de diseño. |
| **B2** | **Android no tiene donut, líneas ni micrográficos.** Solo existen `CategoryBars` e `IncomeExpenseBars`. iOS tiene Swift Charts, pero el donut solo existe en el Análisis del Owner. | Android `core/design/.../Components.kt:200,218`; iOS `DincrDesign/Components/Charts.swift`, `OwnerAnalysisView.swift:168` | La regla visual necesita una pequeña librería de gráficos compartida por concepto, sin dependencia nueva obligatoria (Canvas en Compose). |
| **B3** | **El onboarding ofrece 8 instituciones**, pero el parser de correo solo lee **BAC, MultiMoney y Banco Popular** (y CCSS para planilla). | `auth/models.py:60-62`, `email_monitor/parser.py:24`, `email_monitor/service.py:41` | Cuentas no puede insinuar lectura automática donde no existe (UX-2). |
| **B4** | **Las instituciones del onboarding son una preferencia suelta** (`accounts.selected_financial_institutions`) sin relación con las cuentas reales (`account_balances.bank_name`). | `auth/saas.py:165-213`, `schema.sql` `account_balances` | Para que Cuentas sea la fuente de verdad (UX-2), la institución debe vivir en la cuenta. Requiere backend. |
| **B5** | **La automatización de deudas existente asume que la cuota fue pagada al llegar la fecha.** `apply_due_installments` registra cada cuota vencida como pagada (crea un `debt_payments` y una transacción `debt_payment`) y separa intereses y capital. Hoy es solo Owner, comando explícito, *dry run* por defecto, **sin ningún cliente ni scheduler que lo llame**. Además, `debts.auto_update_monthly` tiene **DEFAULT TRUE** para todas las deudas, inerte para Users porque el gate es del Owner. | `finance/debt_automation.py`, `finance/service.py:396-500`, `schema.sql` `debts` | Contradice la decisión "programada ≠ confirmada". **No conectarlo a ninguna pantalla ni scheduler** hasta el rediseño (§8). Un opt-in VIP real necesita su propio indicador con default `false`, probablemente con migración. |
| **B6** | **La consulta de Gmail compartida incluye un filtro de CCSS "Orden Patronal".** Puede ser una heurística de la realidad del Owner dentro de código compartido. **No verificado** si esa ruta es solo Owner. | `email_monitor/service.py:41` | Fuera de alcance. Se reporta para revisión (invariante A); no se toca. |
| **B7** | **El puntaje de salud se calcula de varias formas** (deterioration, lifecycle, director), y solo iOS VIP lo muestra en Hoy. | inventarios previos, master plan P3.7 | UX-15: transición en K-2. |
| **B8** | **Agregar Patrimonio antes de retirar DINCR daría 6 pestañas.** | `MainTabView.swift`, `MainScaffold.kt` | Patrimonio **reemplaza** a DINCR en el mismo PR, con el gate de §11 cumplido. |

---

## 3. Mapa final de navegación

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  HOY            MOVIMIENTOS        PLAN              PATRIMONIO      PERFIL   │
│  ¿cómo estoy?   ¿qué pasó?         ¿qué voy a hacer? ¿qué tengo y    mi cuenta│
│                                                       qué debo?               │
└──────────────────────────────────────────────────────────────────────────────┘
HOY
 ├ ¿Cómo estoy?  (estado + micrográfico)
 ├ ¿Qué puedo gastar?
 ├ Para atender (≤3 · Ver todas)
 └ ¿Qué viene?  (próximos pagos / agenda Owner)
MOVIMIENTOS   [ Lista | Análisis | Por revisar ]
 ├ Lista: buscar · filtros (tipo, categoría, cuenta, período) · "+" Gasto/Ingreso/Otro
 ├ Análisis: Resumen · Ingresos vs gastos · Categorías · Comercios · Tendencias · Reportes · Revisión del mes
 └ Por revisar: correos detectados · transferencias propias · sin categoría · duplicados · moneda
PLAN
 ├ Tu plan del mes  (Salvavidas · Deudas · Metas · Ahorro/inversión · Disponible + "Por qué")
 ├ Deudas           (administrar · pagos · estrategia · próximos · auto-actualización*)
 ├ Metas y ahorro   (★ Salvavidas arriba · metas · planes de ahorro)
 ├ Pagos fijos      (todos los planes; "esencial")
 ├ Presupuesto      🔒B
 ├ Calendario       🔒B
 └ Aguinaldo        🔒V  (destacado oct–dic)
PATRIMONIO
 ├ Patrimonio neto  (cuando P0.9 esté listo)
 ├ Cuentas          (instituciones → cuentas → fuente · Agregar cuenta · Agregar sin conectar · Conexiones)
 ├ Deudas           (donut de composición, lee Plan › Deudas)
 ├ Proyecciones     🔒V (3m · 6m · 1a · escenarios)
 ├ Historial        🔒V
 ├ Análisis         (salud financiera: ayuda / perjudica / recomienda)
 └ [Owner] Cuentas por cobrar · Inversiones · Negocios · Línea de tiempo · Conciliación
PERFIL
 ├ Cabecera · Suscripción · Preferencias
 ├ Seguridad · Apariencia · Ayuda y soporte · Legal
 ├ Tus datos (descargar · eliminar [no Owner] · cerrar sesión)
 ├ [Owner] JARVIS: Chat · Agenda · Memoria · (Deportes, tras P0.2c)
 └ [Owner] Administración (en el laboratorio web; nativo opcional)
```
`*` La auto-actualización de deudas requiere el diseño de §8 antes de cualquier implementación.

---

## 4. Principio de presentación

Cada función tiene un solo **tipo**:
- **Titular:** un número en Hoy.
- **Sección:** una fila en el hub de una pestaña.
- **Subpantalla.**
- **Contextual:** un botón dentro de otra pantalla.
- **Detalle:** se ve al tocar.
- **Análisis avanzado.**
- **Bloqueado visible:** fila con insignia; abre Suscripción.
- **Owner:** solo Owner.
- **Administración.**
- **Diferido:** aparece cuando hay datos suficientes (§6.7).

**Reglas de visibilidad:**
- Lo bloqueado por plan **nunca se oculta**: es una fila bloqueada.
- Lo bloqueado tampoco se promociona en Hoy.
- Desconocido nunca se muestra como 0: se muestra "Sin dato" con un enlace al hogar del dato.

---

## 5. Sistema visual

### 5.1 Los cuatro tonos de mensaje (UX-5)
Un componente nuevo, `DincrMessage` (iOS `DincrDesign` y Android `core/design`), con 4 tonos. El tono se reconoce **antes de leer** por color, ícono, forma y ubicación.

| Tono | Significa | Forma | Ícono | Color (token) | Dónde aparece | Nunca |
|---|---|---|---|---|---|---|
| **ERROR TÉCNICO** | Algo de DINCR falló: red, servidor, sesión, mantenimiento | Banda superior gris neutra, ancho completo, con "Reintentar" | `wifi.slash` / `exclamationmark.icloud` | `systemNeutral` (no rojo financiero) | Arriba de la pantalla afectada | Dentro de "Para atender" |
| **PARA ATENDER** | Situación financiera que merece atención: cuota por vencer, gasto sobre presupuesto, Salvavidas bajo | Tarjeta con borde lateral ámbar y una acción | `bell` / `calendar.badge.exclamationmark` | `attention` (ámbar) | Hoy → Para atender; arriba de la pantalla relacionada | Para fallos técnicos |
| **OPORTUNIDAD** | DINCR encontró algo que puede ayudar: conectar correo, aportar el sobrante, marcar un pago fijo | Tarjeta suave azul o violeta, ícono de destello, acción secundaria | `sparkles` / `lightbulb` | `opportunity` (azul) | Para atender (después de lo urgente); contextual | Como bloqueo o error |
| **POSITIVO** | Progreso, mejora o meta alcanzada | Tarjeta verde con check o confeti sutil | `checkmark.seal` / `arrow.up.right` | `positive` (verde) | Hoy (máximo 1), Metas, Deudas | Para tapar un problema |

**Reglas:**
1. El rojo se reserva para dinero negativo real (sobregiro o compromisos mayores que los ingresos), siempre con una explicación humana. Nunca se usa para un fallo de la app.
2. Cada alerta del backend se traduce a un tono con una tabla fija (`severity` → tono): `critical`/`high` → Para atender; `success` → Positivo; `info` → Oportunidad. Los errores técnicos nunca vienen del motor financiero.
3. Hoy muestra como máximo 3 ítems, ordenados así: Para atender, luego Oportunidad, luego Positivo.

### 5.2 Gráficos: cuándo y cuál
| Pregunta | Gráfico | Dónde |
|---|---|---|
| ¿De qué se compone? | **Donut** con centro = total; toque = detalle del segmento | Patrimonio → Deudas, Patrimonio → Cuentas, Análisis → Categorías |
| ¿Cómo evoluciona? | **Línea** (con área suave) | Análisis → Evolución, Patrimonio → Historial y Proyecciones |
| ¿Cómo se compara? | **Barras** | Análisis → Ingresos vs gastos, por mes |
| ¿Cuánto llevo? | **Progreso** (anillo o barra) | Metas, Salvavidas, presupuesto, deuda pagada |
| ¿En qué estado estoy? | **Indicador** de estado con 3 niveles + texto | Hoy → ¿Cómo estoy?, Salud |
| Vistazo rápido | **Micrográfico** (sparkline de 30 días, sin ejes) | Hoy |

**Librería mínima por plataforma:**
- `DonutChart`, `LineTrend`, `ProgressRing`, `Sparkline` y `StatusIndicator`;
- iOS con Swift Charts, Android con Compose Canvas;
- la misma API conceptual, accesible (VoiceOver/TalkBack leen los valores) y con colores por token.

**Regla:** un gráfico entra solo si responde su pregunta más rápido que el número.

### 5.3 Lenguaje (UX-16): glosario propuesto
**Cada fila requiere validar la semántica antes de cambiar el texto.** Si la fórmula no coincide con la palabra cotidiana, se busca otra palabra; el significado nunca cambia.

| Hoy dice | Propuesta | Validar |
|---|---|---|
| Margen para decidir | "Dinero disponible" / "Te queda para decidir" | ¿Es ingreso − compromisos − esenciales? Si incluye ahorro asignado, usar "Te queda para decidir" |
| Sobrante para repartir | "Lo que te sobra este mes" | igual a la base de distribución |
| Podés gastar con tranquilidad | se mantiene | — |
| Saldo mínimo previsto (45 días) | "Lo más bajo que llegaría tu dinero en 45 días" | — |
| De dónde sale | "De dónde sale este dinero" | — |
| Base mensual | "Lo que necesitás cada mes" | ¿incluye deudas? |
| Mínimo personal por mes | "Lo mínimo para tus gastos personales" | — |
| Hitos | "Próximos logros" | — |
| Confianza baja | "Todavía con pocos datos" | — |
| Deterioro financiero detectado | "Este mes tus finanzas empeoraron: [causa principal]" + ⓘ | la causa viene del motor |
| Monitor de correo | "Lectura de correos del banco" | — |
| Distribución de dinero | "Cómo repartir tu dinero" (dentro de Tu plan del mes) | — |
| Mi plan (suscripción) | **"Suscripción"** (UX-12, aprobado) | — |
| *Owner:* Efectivo distribuible | "Dinero que podés repartir" | — |
| *Owner:* Gastos nuevos después del corte | "Compras después del cierre de la tarjeta" | — |
| *Owner:* Excluidos por duplicar una deuda | "No contados: ya están en una deuda" | — |
| *Owner:* VGH | "Vacaciones, aguinaldo y horas (VGH)" ⓘ | — |

---

## 6. Wireframes textuales

### 6.1 HOY: cuatro preguntas en cinco segundos
```
┌───────────────────────────────────────────┐
│ Buenas, {nombre}            [Owner: ◉ JARVIS]│
├───────────────────────────────────────────┤
│ ① ¿CÓMO ESTOY?                              │
│  ● Vas bien este mes            ▁▂▃▅▄▆▇ 30d │   ← indicador 3 estados + sparkline
│  Entró ₡X · Salió ₡Y                        │
├───────────────────────────────────────────┤
│ ② ¿QUÉ PUEDO GASTAR?                        │
│  ₡Z disponibles  ━━━━━━━━━░░░  (Basic: vs presupuesto)
│  VIP: "Podés gastar ₡Z con tranquilidad" ⓘ  │
├───────────────────────────────────────────┤
│ ③ PARA ATENDER                     Ver todas│   ← desaparece si está vacío
│  ▌🔔 Cuota de Préstamo vence en 2 días  [Registrar pago]
│  ▌✨ Te sobraron ₡N: ¿lo sumamos al Salvavidas? [Ver]
│  ▌✓ ¡Pagaste el 50% de tu tarjeta!          │
├───────────────────────────────────────────┤
│ ④ ¿QUÉ VIENE?                               │
│  Vie 10 · Alquiler ₡…   Lun 13 · Luz ₡…     │
│  [Owner: + agenda JARVIS]                   │
└───────────────────────────────────────────┘
          [ + Registrar movimiento ]
```

**Qué muestra cada plan:**
- **Free:** ① ② ③ ④. En ④ aparecen sus pagos fijos y deudas (UX-9).
- **Basic:** ② agrega la barra contra el presupuesto; ④ agrega el calendario avanzado.
- **VIP:** ② muestra "Podés gastar con tranquilidad" y el saldo mínimo ⓘ; ③ incluye alertas del Director y avisos de proyección **solo si hay un cambio relevante** (UX-14; al tocar, abre Patrimonio → Proyecciones).
- **Owner:** saludo, atajo a JARVIS y agenda; ③ absorbe "Necesita tu atención".

**Sale de Hoy:**
- gráficos completos, a Análisis;
- hoja de ruta, a Tu plan del mes;
- salud, a Patrimonio → Análisis;
- "En 6 meses", a Proyecciones;
- tarjetas de Deudas y Metas, a Plan (en Hoy quedan contextuales vía ③ y ④).

### 6.2 MOVIMIENTOS
```
[ Lista | Análisis | Por revisar ●3 ]
LISTA     🔍  [Tipo ▾] [Categoría ▾] [Cuenta ▾] [Período ▾]
          Hoy ─ Supermercado  −₡…   ·  Salario  +₡…
          "+" → Gasto · Ingreso · Otro… (me prestaron, me devolvieron, vendí algo, transferí entre mis cuentas)
ANÁLISIS  [Este mes ▾]  [Cuenta ▾]  [Categoría ▾]
          ▸ Resumen (ingresos · gastos · neto)          barras
          ▸ Ingresos vs gastos (6m Free / 12m B+)        barras
          ▸ Evolución del gasto                          línea
          ▸ Categorías → toque = lista filtrada          donut
          ▸ Comercios (top)                              barras horizontales
          ▸ Tendencias / mes anterior 🔒B                línea
          ▸ Reportes 🔒B · Revisión del mes 🔒V (destacada al cierre)
          ▸ [Owner] ingresos/planilla, ciclo de tarjeta, tarjetas adicionales, alertas de moneda
POR REVISAR  correos detectados [Confirmar · Corregir · Descartar] · transferencias propias ·
             sin categoría · posibles duplicados · moneda sin tipo de cambio
```

### 6.3 PLAN
```
TU PLAN DE OCTUBRE                                   ⓘ Por qué DINCR recomienda esto
 Prioridad: Fortalecer tu Salvavidas  (propuesta por DINCR · Cambiar)
 ┌ reparto del mes (barra apilada) ───────────────────────────────┐
 │ Salvavidas ₡a │ Deudas ₡b │ Metas ₡c │ Ahorro/inv ₡d │ Disponible ₡e │
 └───────────────────────────────────────────────────────────────┘
 Cada segmento → su pantalla. "Por qué" = el detalle actual del Director/Estrategia (sin perder nada).
 [VIP] ¿Y si…? → Patrimonio › Proyecciones › Escenarios
 Free: fila 🔒B con valor en una línea.

DEUDAS                     [+ Agregar deuda]
 Tarjeta BAC   ₡…  ━━━━░░ 62% pagado   próxima cuota 10/10
 ▸ Deuda → editar · corregir · registrar pago · historial · plan de pago
          [Owner / VIP opt-in] "Actualizar deuda automáticamente" (solo con datos completos; §8)
METAS Y AHORRO   ★ Salvavidas  ◔ 2,1 de 3 meses   ·  metas  ·  planes de ahorro
PAGOS FIJOS      (Free ✓) alquiler · luz · marcar "esencial"
INGRESOS*        salario o ingreso declarado (esperado) · frecuencia · ingresos reales del mes (desde Movimientos)
PRESUPUESTO 🔒B · CALENDARIO 🔒B · AGUINALDO 🔒V
```
`*` Ingreso declarado (K-1): **Plan → Ingresos**, que edita la fuente existente `financial_profiles` (monto mensual + frecuencia semanal/quincenal/mensual). Es esperado, no confirmado.

**Prioridad (UX-8):**
1. DINCR analiza los datos reales.
2. Propone una prioridad con una frase de motivo, por ejemplo: *"Tu Salvavidas cubre 0,8 meses; con una emergencia te endeudarías."*
3. "Cambiar" permite elegir otra.
4. La elección humana manda y se guarda.
5. DINCR **no vuelve a preguntar**. Solo sugiere revisar si cambian los datos de fondo (en tono Oportunidad).

### 6.4 PATRIMONIO
```
(Sin número grande de patrimonio neto hasta P0.9, K-3.) Resumen fiable: cuentas · ahorros · deudas
CUENTAS                                        [+ Agregar cuenta]
 BAC ─ Cuenta ••1234 ₡…  · fuente: correo ✓       ← institución → cuenta → fuente
 Popular ─ Ahorro ••88   · fuente: manual
 Davivienda ─ ••55       · fuente: manual (lectura de correo no disponible todavía)
 [Administrar conexiones]  → Gmail/Outlook: estado · reautorizar · buscar avisos
DEUDAS (composición)                           → administrar en Plan › Deudas
      ╭─────╮   Tarjeta BAC 48%  ₡…
     │ ₡Tot │   Préstamo auto 37% ₡…   ← tocar segmento = resalta + detalle
      ╰─────╯   Préstamo pers. 15% ₡…     (tasa, cuota, fin estimado)
PROYECCIONES 🔒V   [3m | 6m | 1a]   línea de efectivo, deuda y patrimonio · Escenarios
HISTORIAL 🔒V      línea del patrimonio
ANÁLISIS           Salud financiera: SOLO factores con estado (sin número /100, K-2) · qué recomienda DINCR
[Owner]            Cuentas por cobrar · Inversiones · Negocios · Línea de tiempo · Conciliación
```

**Flujo de Cuentas (UX-2).** Es conceptual: no copia la interfaz de YNAB.
```
Agregar cuenta → 🔍 Buscar institución (BAC, BN, BCR, Popular, Davivienda, Scotiabank, Promerica, MultiMoney, Otra)
 → Institución elegida:
     · "Leer avisos de este banco desde tu correo" [VIP] → conectar Gmail/Outlook (si no está) → cuentas detectadas → "¿Es tuya?"
       (solo si el parser soporta esa institución; si no: "Por ahora: cuenta manual")
     · "Agregar cuenta sin conectar" → nombre, tipo, moneda, saldo actual (declarado)
 → Administrar conexiones: correo conectado, permisos, última lectura, desconectar
```

**Reglas de Cuentas:**
- **Nunca** dice "conectado al banco": dice "leemos los avisos de tu correo".
- Las instituciones de Cuentas pueden **orientar al parser**, para saber qué remitentes son relevantes para el usuario. Eso requiere backend y no debe crear dependencias Owner (invariante A).

### 6.5 PERFIL
```
{nombre} · {correo} · [Free|Basic|VIP|Owner]
Suscripción · Preferencias (nombre, moneda, formato — editables)
Seguridad · Apariencia · Ayuda y soporte · Legal
Tus datos: Descargar · Eliminar cuenta (no Owner) · Cerrar sesión
[Owner] JARVIS → Chat · Agenda · Memoria
[Owner] Administración → (laboratorio web)
```

### 6.6 Situación financiera (UX-7): adónde va cada campo
| Campo actual | Nuevo hogar | Mientras tanto |
|---|---|---|
| Tipo de ingreso y salario (fijo o por hora) | **Plan → Ingresos** (K-1), con la misma fuente `financial_profiles` | el campo sigue accesible y sigue alimentando `income_policy` |
| Ahorros disponibles (`liquid_savings`) | Patrimonio → Cuentas (saldos declarados, P2.8) | accesible hasta P2.8 + P3.2 |
| Meta de fondo de emergencia (monto) | Salvavidas en meses; el monto queda como override heredado (P3.6) | accesible |
| Gastos esenciales | derivados de Pagos fijos marcados "esencial" (P3.0); ajuste manual opcional | accesible hasta P3.2 |
| Mínimo personal por mes | Tu plan del mes → Ajustes | accesible |
| Prioridad (VIP) | Tu plan del mes → Cambiar prioridad (UX-8) | accesible |
| **La pantalla Situación** | se retira solo cuando las 6 filas tengan hogar con paridad | **gate** (§11) |

### 6.7 Aparición progresiva (sin preguntar estimaciones, UX-1)
| Datos reales | Aparece |
|---|---|
| Ninguno | Hoy muestra "Empecemos": registrar un movimiento, agregar cuenta, agregar deuda o pago fijo |
| Primeros movimientos | ① y ② del mes; categorías |
| Pagos fijos o deudas | ④ "¿Qué viene?"; ③ cuotas próximas |
| 1 mes cerrado | Revisión del mes; prioridad propuesta (B+); Salvavidas con meta sugerida (D19) |
| 2+ meses | tendencias, comparación con el mes anterior |
| Saldos y 1+ mes (VIP) | proyecciones, historial |

---

## 7. Experiencias por plan y Owner

| | Free | Basic | VIP | Owner |
|---|---|---|---|---|
| **Hoy** | ① ② ③ ④ | + presupuesto, calendario avanzado | + "podés gastar con tranquilidad", alertas del Director, avisos de proyección | + JARVIS, agenda, "necesita tu atención" |
| **Movimientos** | lista completa, tipos especiales (D14), análisis 6 m, Por revisar (sin categoría, duplicados) | + 12 m, tendencias, reportes | + revisión del mes, correo en Por revisar | + registros, planilla, tarjeta, adicionales, moneda |
| **Plan** | deudas (editar, D1), metas y ahorro, Salvavidas (D17, tras P3.4), **pagos fijos (UX-9)**; plan del mes 🔒 | + Tu plan del mes, presupuesto, calendario | + Director detrás de "Por qué", aguinaldo, deuda automática opt-in (§8) | + Tu ciclo, gastos protegidos, amortización automática (§8) |
| **Patrimonio** | cuentas manuales, donut de deudas, patrimonio neto (D11, tras P0.9); proyecciones e historial 🔒 | igual que Free | + correo, proyecciones, escenarios, historial | + por cobrar, inversiones, negocios, línea de tiempo, conciliación |
| **Perfil** | completo | completo | completo | + JARVIS, Administración; no puede eliminar la cuenta |

**Owner:**
- JARVIS queda en **Chat, Agenda y Memoria**, más Deportes cuando P0.2c deje de escribir desde un GET.
- Las 6 secciones "en restauración" **no son filas permanentes**: cada una aterriza en su pestaña al recuperarse (matriz J, estado HISTORICAL_RECOVERY_PENDING).
- **Hasta entonces se mantienen en JARVIS (R1).**

---

## 8. Deudas automáticas: requisitos de diseño (sin implementar)

**Objetivo:**
- Owner con amortización automática.
- VIP con opt-in por deuda: "Actualizar deuda automáticamente".

**Requisitos aprobados:**
1. **Habilitación:** solo si la deuda tiene los datos completos para calcularla:
   - saldo;
   - tasa y método de interés;
   - cuota, plazo y día de pago;
   - cargos fijos;
   - fecha de inicio o del primer pago.

   Si falta algo, el interruptor queda deshabilitado con "Falta: tasa de interés" (tono Oportunidad).
2. **Descomposición:** cada cuota se divide en **intereses + capital + otros** (cargos, seguros). Nunca se resta la cuota completa del capital. El cálculo ya existe (`interest_method`, `fixed_fee_amount`, `principal_amount`/`interest_amount` en `debt_payments`) y debe reutilizarse.
3. **Cuota programada / devengada ≠ pago confirmado.** Diseño propuesto:
   - Al llegar la fecha se crea una **cuota esperada** (estado `scheduled` → `due`) **sin** mover el saldo ni crear una transacción.
   - Pasa a `confirmed` solo con **evidencia**: un movimiento conciliado (manual o de correo/parser) o la confirmación explícita del usuario ("Sí, la pagué").
   - Solo una cuota `confirmed` registra el pago (intereses y capital) y mueve el saldo.
   - Una cuota `due` sin evidencia aparece en **Para atender**: "¿Pagaste la cuota de X?" [Sí, registrar] [Todavía no].
4. **Conciliación:** si un movimiento o correo coincide en monto (±tolerancia), fecha (ventana) e institución con una cuota `due`, DINCR **propone** el vínculo. Si la regla determinista es inequívoca y el usuario activó el opt-in, puede vincular automáticamente, siempre con historial y "deshacer".
5. **Idempotencia y tenancy:** una cuota por deuda y período, con alcance `account_id` + `workspace_id`. Sin escrituras en lecturas (invariante C): todo mediante un comando o job explícito y auditado.
6. **Lo existente:** `apply_due_installments` (Owner) **asume el pago** al llegar la fecha. **No se conecta a ninguna pantalla ni scheduler** y se rediseña con el modelo anterior. `auto_update_monthly` (DEFAULT TRUE) no sirve como opt-in VIP: hace falta un indicador explícito con default `false`.
7. **Dependencias:**
   - P2.2a, el servicio unificado de pagos de deuda (D16);
   - P2.2b, el historial de Users;
   - posiblemente una migración (tabla o estados de cuotas esperadas y el nuevo indicador) con `migration-gate-acknowledged`;
   - tests PG de idempotencia, aislamiento y "sin pago sin evidencia".

**Siguiente paso:** el documento técnico `DEBT-AUTO-DESIGN`, para revisión de Kenneth antes de cualquier código.

---

## 9. Web: tres cosas distintas
| Superficie | Qué es | Regla |
|---|---|---|
| **App comercial** | iOS + Android | la única experiencia para clientes; la paridad se exige aquí |
| **Laboratorio web (Vercel)** | herramienta interna de Kenneth para probar pantallas, gráficos, flujos y la administración Owner | sin paridad comercial; los prototipos de esta reestructuración pueden probarse aquí antes de llevarlos a nativo |
| **Landing (dincr.com)** | sitio público y comercial | marketing, legal y soporte; nunca app financiera (CLAUDE.md §1) |

**Consecuencias:**
- Los defectos web (metas VIP de solo lectura, ahorro Free inalcanzable, componentes muertos, la llamada `owner-link` rota) pasan a ser **deuda del laboratorio**, sin bloquear el producto.
- Nada se borra sin decisión.
- Restringir el acceso del laboratorio (hoy cualquier usuario podría entrar) es un **cambio de configuración de producción**: gate humano (K-6).

---

## 10. Matriz de preservación funcional

**Convenciones:**
- **Plan:** F/B/V/O = Free/Basic/VIP/Owner. `✓` disponible, `🔒` bloqueado visible, `✗` hoy no disponible, `Ⓞ` solo Owner. `A→B` = cambio aprobado.
- **iOS / Android / Web lab:** `✓` existe, `◐` parcial, `—` no existe.
- **Owner:** si aplica una capa o diferencia para el Owner.
- **Estado:** uno de MOVED, MERGED, CONTEXTUAL, OWNER, ADMINISTRATION, HISTORICAL_RECOVERY_PENDING (abreviado **HRP**). *MOVED (en su lugar)* significa que se clasifica sin cambio de ubicación.
- **Depende:** el requisito para la migración. "UX" significa que basta con el cliente.
- **Ninguna fila está en estado de borrado u ocultamiento.**

### A. Acceso, onboarding e identidad
| # | Función actual | Ubicación actual | Nueva ubicación | Plan | iOS | And | Web lab | Backend | Owner | Estado | Depende |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A01 | Login Google | Inicio | Inicio | FBVO ✓ | ✓ | ✓ | ✓ | /auth | — | MOVED (en su lugar) | — |
| A02 | Login Apple | Inicio | Inicio | FBVO ✓ | ✓ | — | — | /auth | — | MOVED (en su lugar) | regla de plataforma |
| A03 | Aceptación legal | Onboarding | Onboarding | FBVO ✓ | ✓ | ✓ | ✓ | /auth | — | MOVED (en su lugar) | — |
| A04 | Nombre, moneda, formato | Onboarding (no editable) | Onboarding + Perfil → Preferencias (editable) | FBVO ✓ | ✓ | ✓ | ◐ | /auth/profile-setup | — | MOVED | P2.12 (backend PATCH) |
| A05 | Objetivo de uso (`usage_goal`) | Onboarding | Onboarding, solo personalización (UX-1); nunca entrada de motores | FBVO ✓ | ✓ | ✓ | ◐ | se guarda; sin consumidor | — | MOVED (en su lugar) | test de guarda (backend) |
| A06 | Selección de bancos | Onboarding, paso 4 | Patrimonio → Cuentas → Agregar cuenta (UX-2) | FBVO ✓ | ✓ | ✓ | — | `selected_financial_institutions` | — | MOVED | backend (institución por cuenta, B4) |
| A07 | Elegir plan | Onboarding | Onboarding + Perfil → Suscripción | FBV ✓ | ✓ | ✓ | ✓ | /auth/plans | Owner salta | MOVED (en su lugar) | — |
| A08 | Oferta de bloqueo de app | Onboarding | Onboarding | FBVO ✓ | ✓ | ✓ | — | — | — | MOVED (en su lugar) | — |
| A09 | Rol no soportado | Raíz | Raíz | — | ✓ | ✓ | ✓ | P0.2d | — | MOVED (en su lugar) | — |
| A10 | Mantenimiento, servicio degradado, cambios pausados | Global | Global, tono **Error técnico** | FBVO ✓ | ✓ | ✓ | ◐ | /health | — | MOVED (en su lugar) | UX (§5.1) |
| A11 | Cuenta eliminándose / no pudimos cargar | Raíz | Raíz, tono Error técnico | FBV ✓ | ✓ | ✓ | ✓ | /auth/me | — | MOVED (en su lugar) | UX |

### B. Hoy (Users)
| # | Función actual | Ubicación actual | Nueva ubicación | Plan | iOS | And | Web lab | Backend | Owner | Estado | Depende |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B01 | Disponible del mes (Free) | Hoy | Hoy ② | F ✓ | ✓ | ✓ | ✓ | /free/home | — | MERGED | UX |
| B02 | Gráfico de 6 meses (Free) | Hoy | Análisis (Hoy: sparkline) | F ✓ | ✓ | ✓ | ✓ | /free/home | — | MOVED | UX |
| B03 | Categorías (Free) | Hoy | Análisis → Categorías | F ✓ | ✓ | ✓ | ✓ | /free/home | — | MOVED | UX |
| B04 | Balance del mes (Basic) | Hoy | Hoy ① | B ✓ | ✓ | ✓ | ✓ | /basic/dashboard | — | MERGED | UX |
| B05 | Tarjeta Deudas (Basic) | Hoy | Plan → Deudas; Hoy ③④ contextual | B ✓ | ✓ | ✓ | ✓ | /finance/debts | — | CONTEXTUAL | UX |
| B06 | Tarjeta Ahorro y metas | Hoy | Plan → Metas y ahorro | B ✓ | ✓ | ✓ | ✓ | /goals | — | MOVED | UX |
| B07 | Presupuesto en Hoy | Hoy (solo Android) | Hoy ②, barra (ambas) | B ✓ | — | ✓ | ✓ | /basic/budget | — | MERGED | UX (paridad) |
| B08 | Próximos 7 días | Hoy (solo Android) | Hoy ④ (ambas; Free con pagos fijos y deudas) | B ✓ → F ✓ | — | ✓ | ◐ | /basic/calendar | agenda | MOVED (en su lugar) | UX; Free necesita la fila G24 |
| B09 | Gráficos de ingresos/gastos y categorías (Basic) | Hoy | Análisis | B ✓ | ✓ | ✓ | ✓ | /basic/dashboard | — | MOVED | UX |
| B10 | "Podés gastar con tranquilidad" | Hoy | Hoy ② | V ✓ | ✓ | ✓ | ✓ | /vip/command-center | ✓ | MOVED (en su lugar) | UX |
| B11 | "Tu prioridad" | Hoy | Hoy (una línea) + Tu plan del mes | V ✓ | ✓ | ✓ | ✓ | estrategia | ✓ | MERGED | UX |
| B12 | Alertas VIP en Hoy | Hoy | Hoy ③ Para atender | V ✓ | ✓ | ✓ | ✓ | alertas | ✓ | MERGED | UX (§5.1) |
| B13 | Hoja de ruta | Hoy | Tu plan del mes | V ✓ | ✓ | ✓ | ✓ | estrategia | ✓ | MOVED | UX |
| B14 | Salud financiera | Hoy (solo iOS VIP) | Patrimonio → Análisis | V ✓ | ✓ | — | ◐ | deterioration/lifecycle | ✓ | MOVED | K-2: solo factores, sin número; P3.7 para el puntaje |
| B15 | "En 6 meses" | Hoy (solo Android VIP) | Patrimonio → Proyecciones; Hoy solo con cambio relevante | V ✓ | — | ✓ | ◐ | /vip/projections | ✓ | MOVED | UX |
| B16 | "Tus finanzas" (enlaces) | Hoy | Hub de Plan | FBVO ✓ | ✓ | ✓ | ✓ | — | — | MOVED | UX |
| B17 | Deslizar para actualizar | Hoy (iOS) | Todas las pestañas (ambas) | FBVO ✓ | ✓ | — | — | — | — | MOVED (en su lugar) | UX (paridad) |
| B18 | ProfileNudge | Hoy (Android) | Hoy ③ Oportunidad, según el plan (ambas) | FBV ✓ | — | ✓ | — | — | — | MERGED | UX (corrige G3) |
| B19 | Aviso de deuda sin tasa | Hoy | Hoy ③ Oportunidad, solo si el plan permite editar | FBV ✓ | ✓ | ✓ | — | — | — | MERGED | UX; edición Free con P2.1 |

### C. Hoy del Owner
| # | Función actual | Ubicación actual | Nueva ubicación | Plan | iOS | And | Web lab | Backend | Owner | Estado | Depende |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C01 | Saludo y atajo JARVIS | Hoy (solo iOS) | Hoy (ambas) | Ⓞ | ✓ | — | ✓ | — | ✓ | OWNER | P1.2 |
| C02 | "Tu dinero" | Hoy | Hoy ① ② | Ⓞ | ✓ | — | ✓ | /finance/* | ✓ | OWNER | P1.2 |
| C03 | "Necesita tu atención" | Hoy | Hoy ③ | Ⓞ | ✓ | — | ◐ | alertas | ✓ | OWNER | P1.2 + §5.1 |
| C04 | Tus finanzas (Owner) | Hoy | Plan | Ⓞ | ✓ | — | ✓ | — | ✓ | OWNER | UX |
| C05 | Próximos y agenda | Hoy | Hoy ④ | Ⓞ | ✓ | — | ✓ | /jarvis/calendar/upcoming | ✓ | OWNER | P1.2 |

### D. Movimientos: Lista
| # | Función actual | Ubicación actual | Nueva ubicación | Plan | iOS | And | Web lab | Backend | Owner | Estado | Depende |
|---|---|---|---|---|---|---|---|---|---|---|---|
| D01 | Lista por día | Movimientos | Movimientos → Lista | FBVO ✓ | ✓ | ✓ | ✓ | /free/movements | — | MOVED (en su lugar) | — |
| D02 | Búsqueda | Movimientos | Lista | FBVO ✓ | ✓ | ✓ | ✓ | — | — | MOVED (en su lugar) | — |
| D03 | Filtro por tipo (Android usa una regex "Deudas") | Movimientos | Lista, filtro por tipo fiel | FBVO ✓ | ◐ | ◐ | ◐ | movement_type | — | MOVED (en su lugar) | P0.3a/b/c |
| D04 | Filtros por categoría, cuenta y período | parcial | Lista + Análisis | FBVO ✓ | ◐ | ◐ | ◐ | financial_account_id | — | MOVED | parámetros de backend (P5.1) |
| D05 | Agregar gasto o ingreso | Movimientos | Lista "+" | FBVO ✓ | ✓ | ✓ | ✓ | /free/movements POST | — | MOVED (en su lugar) | — |
| D06 | Editar o eliminar movimiento | Movimientos | Lista → detalle | FBVO ✓ | ✓ | ✓ | ✓ | PUT/DELETE | — | MOVED (en su lugar) | anulación de filas bancarias P2.10 |
| D07 | Moneda original | Lista | Lista | FBVO ✓ | ✓ | ✓ | ✓ | — | — | MOVED (en su lugar) | — |
| D08 | Tipos especiales (transferencia, reembolso, préstamo recibido, venta de activo, cobro) | backend parcial | Lista "+ Otro…" | FBVO ✓ (cobro Ⓞ) | — | — | ◐ | parcial | cobro | HRP | P2.14/P2.15 |
| D09 | Enlace "Resumen del mes" | Movimientos (Android) | Segmento Análisis | FBVO ✓ | — | ✓ | — | — | — | MERGED | UX |

### E. Movimientos: Análisis (incluye lo que hoy está en la pestaña DINCR)
| # | Función actual | Ubicación actual | Nueva ubicación | Plan | iOS | And | Web lab | Backend | Owner | Estado | Depende |
|---|---|---|---|---|---|---|---|---|---|---|---|
| E01 | Resumen del mes | DINCR | Análisis → Resumen | FBVO ✓ | ✓ | ✓ | ✓ | /free/monthly-summary | — | MOVED | UX |
| E02 | Reportes | DINCR (Free oculto) | Análisis → Reportes | F ✗→🔒, BVO ✓ | ✓ | ◐ (oculto si el flag está apagado) | ✓ | /basic/reports | — | MOVED | UX (P6.4) |
| E03 | Revisión mensual | DINCR (FB oculto) | Análisis → Revisión del mes | FB ✗→🔒, VO ✓ | ✓ | ✓ | ✓ | /vip/monthly-review | — | MOVED | UX |
| E04 | Ingresos vs gastos | Hoy / Resumen | Análisis (barras) | FBVO ✓ | ✓ | ✓ | ✓ | varios | — | MERGED | UX |
| E05 | Categorías con detalle | Hoy / Resumen / Reportes | Análisis (donut → lista filtrada) | FBVO ✓ | ◐ | ◐ | ✓ | varios | — | MERGED | UX (B2: donut en Android) |
| E06 | Evolución, tendencias, comercios, meses anteriores | Reportes parcial | Análisis | F 6m, B+ 12m | ◐ | ◐ | ◐ | parcial | — | MOVED | P5.1 (`/user-product/analysis`) |
| E07 | Análisis financiero JARVIS | Perfil → JARVIS → Análisis | Análisis (capa Owner) + Patrimonio | Ⓞ | ✓ | ✓ | ✓ | /transactions/analysis/* | ✓ | OWNER | UX (mover); conservar acceso JARVIS hasta paridad |
| E08 | Pronóstico Owner y donut de categorías | JARVIS → Análisis | Análisis Owner | Ⓞ | ✓ | ◐ | ✓ | forecast | ✓ | OWNER | UX |

### F. Movimientos: Por revisar
| # | Función actual | Ubicación actual | Nueva ubicación | Plan | iOS | And | Web lab | Backend | Owner | Estado | Depende |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F01 | Avisos de correo: confirmar, corregir, descartar | Perfil → Correos financieros | Por revisar | FB 🔒, VO ✓ | ✓ | ✓ | ✓ | /email-monitor/* | ✓ | MOVED | UX; contadores P5.5 |
| F02 | Transferencias entre cuentas propias | Correos / Cuentas | Por revisar | VO ✓ | ✓ | ✓ | ◐ | own_transfer_review | ✓ | MOVED | UX |
| F03 | Sin categoría, duplicados, moneda sin tipo de cambio | disperso | Por revisar | FBVO ✓ | ◐ | ◐ | ◐ | parcial | ✓ | MERGED | P5.5 (backend) |
| F04 | Pendientes por cuenta | Perfil → Cuentas | Por revisar + insignia en la cuenta | VO ✓ | ✓ | ✓ | ◐ | — | — | MERGED | UX |

### G. Plan
| # | Función actual | Ubicación actual | Nueva ubicación | Plan | iOS | And | Web lab | Backend | Owner | Estado | Depende |
|---|---|---|---|---|---|---|---|---|---|---|---|
| G01 | Estrategia | Plan → Estrategia | **Tu plan del mes** | F 🔒, BVO ✓ | ✓ | ✓ | ✓ | /finance/strategy-basic | — | MERGED | UX (endpoint intacto) |
| G02 | Distribución | Plan → Distribución | Tu plan del mes → reparto | F 🔒, BVO ✓ | ✓ | ✓ | ✓ | misma respuesta | — | MERGED | UX |
| G03 | Director VIP (hasta 10 tarjetas) | Estrategia VIP | Tu plan del mes + "Por qué DINCR recomienda esto" (todo el detalle se conserva) | VO ✓ | ✓ | ✓ | ✓ | /vip/director | ✓ | MERGED | UX |
| G04 | "Tu ciclo" y capa personal | Estrategia Owner | Tu plan del mes (capa Owner) | Ⓞ | ✓ | ✓ | ✓ | strategy-dashboard | ✓ | OWNER | UX |
| G05 | Prioridad | Situación VIP + motor | Tu plan del mes: propuesta + Cambiar (UX-8) | B+ ✓ (Free 🔒 junto con el plan) | ✓ | ✓ | ◐ | parcial | ✓ | MERGED | backend (guardar override para todos los planes) + P3.7 |
| G06 | Escenarios "¿y si?" | DINCR | Patrimonio → Proyecciones → Escenarios; contextual desde Tu plan del mes | FB ✗→🔒, VO ✓ | ✓ | ✓ | ✓ | POST /vip/scenarios | ✓ | MOVED | UX |
| G07 | Lista de deudas | Hoy → Tus finanzas | Plan → Deudas | FBVO ✓ | ✓ | ✓ | ✓ | /finance/debts | — | MOVED | UX |
| G08 | Crear deuda | Deudas | Plan → Deudas | FBVO ✓ | ✓ | ✓ | ✓ | POST | — | MOVED | UX |
| G09 | Editar o corregir deuda | Deudas (B+) | Plan → Deudas | F ✗→✓ (D1), BVO ✓ | ✓ | ✓ | ✓ | PUT | — | MOVED | P2.1 (gate Free) |
| G10 | Eliminar deuda | Deudas | Plan → Deudas | FBVO ✓ | ✓ | ✓ | ✓ | DELETE | — | MOVED | UX |
| G11 | Registrar pago | Deudas | Plan → Deudas → deuda; contextual en Hoy ③ | FBVO ✓ | ✓ | ✓ | ✓ | POST payment | — | MOVED | P2.2a (servicio unificado) |
| G12 | Historial de pagos y revertir | backend parcial | Plan → Deudas → deuda | FBVO ✓ | — | — | ◐ | parcial | ✓ | HRP | P2.2a/b, P2.6 |
| G13 | Estrategia de pago (`/vip/debt-strategies` sin cliente) | backend / Proyecciones | Plan → Deudas → Plan de pago | VO ✓ | ◐ | ◐ | ◐ | /vip/debt-strategies | ✓ | HRP | UX sobre un endpoint existente |
| G14 | Próximos pagos de deuda | Calendario / Hoy | Plan → Deudas + Hoy ④ | FBVO ✓ | ✓ | ✓ | ✓ | calendario | — | MERGED | UX |
| G15 | Actualización automática de deuda (`apply-due-installments`, sin cliente) | backend Owner | Plan → Deudas → deuda: "Actualizar automáticamente" (Owner; VIP opt-in) | Ⓞ → +V opt-in | — | — | — | comando Owner | ✓ | HRP | **§8 diseño técnico** + posible migración + **K-4** |
| G16 | Metas: listar, crear, editar, aportar, eliminar | Hoy → Metas y ahorro | Plan → Metas y ahorro | FBVO ✓ (Free edita, D1) | ✓ | ✓ | ◐ (VIP solo lectura) | /goals | — | MOVED | P2.1 (gate Free) |
| G17 | Planes de ahorro | Hoy → Metas y ahorro | Plan → Metas y ahorro | FBVO ✓ | ◐ (sin edición) | ✓ | ◐ | /savings-plans | — | MOVED | P2.5 (edición iOS) |
| G18 | Salvavidas | Plan → Salvavidas | Plan → Metas y ahorro (★ arriba) + fila en Tu plan del mes | FB 🔒→✓ (D17), VO ✓ | ✓ | ✓ | ✓ | /vip/emergency-fund | ✓ | MOVED | UX para mover; P3.4 para F/B |
| G19 | Salvavidas: "Actualizar ahorros" | Salvavidas | lee de Patrimonio → Cuentas; el campo se mantiene hasta P2.8/P3.2 | VO ✓ | ✓ | ✓ | ✓ | liquid_savings | ✓ | MERGED | P2.8 + P3.2 |
| G20 | Salvavidas: meses 1/3/6 (0 en Android) | Salvavidas | igual | VO ✓ | ✓ | ◐ | ✓ | — | ✓ | MOVED (en su lugar) | P2.13 |
| G21 | Aguinaldo | Plan → Aguinaldo | Plan → Aguinaldo (destacado oct–dic) | FB 🔒, VO ✓ | ✓ | ✓ | ✓ | /vip/aguinaldo | ✓ | MOVED (en su lugar) | UX |
| G22 | Presupuesto | Perfil → Finanzas (Free oculto) | Plan → Presupuesto | F ✗→🔒, BVO ✓ | ✓ | ✓ (Free bloqueado) | ✓ | /basic/budget | — | MOVED | UX; categorías P0.10 |
| G23 | Calendario financiero | Perfil → Finanzas (Free oculto) | Plan → Calendario | F ✗→🔒, BVO ✓ | ✓ | ✓ | ✓ | /basic/calendar | — | MOVED | UX |
| G24 | Pagos recurrentes | Perfil → Finanzas (Free oculto) | Plan → **Pagos fijos** | **F ✗→✓ (UX-9)**, BVO ✓ | ✓ | ✓ | ✓ | /basic/recurring | — | MOVED | backend (gate Free) + etiqueta de alcance; edición completa P2.4 |
| G25 | Indicador "esencial" | — | Pagos fijos | FBVO ✓ | — | — | — | — | — | HRP | P3.0 (backend) |

### H. Situación financiera (UX-7)
| # | Función actual | Ubicación actual | Nueva ubicación | Plan | iOS | And | Web lab | Backend | Owner | Estado | Depende |
|---|---|---|---|---|---|---|---|---|---|---|---|
| H01 | Tipo de ingreso, salario, pago por hora | Perfil → Situación | Plan → Ingresos (K-1: misma fuente `financial_profiles`; esperado ≠ confirmado) | FBVO ✓ | ✓ | ✓ | ✓ | /financial-profile | ✓ | MOVED | UX (misma fuente); income_policy sin cambios |
| H02 | Ahorros disponibles | Situación | Patrimonio → Cuentas | FBVO ✓ | ✓ | ✓ | ✓ | liquid_savings | ✓ | MERGED | P2.8 + P3.2 |
| H03 | Meta de fondo de emergencia (monto) | Situación | Salvavidas (meses); monto heredado como override | FBVO ✓ | ✓ | ✓ | ✓ | — | ✓ | MERGED | P3.6 |
| H04 | Gastos esenciales | Situación (Free oculto) | Derivados de Pagos fijos "esencial" + ajuste | BVO ✓ | ✓ | ✓ | ✓ | — | protegidos | MERGED | P3.0 + P3.1/P3.2 |
| H05 | Mínimo personal por mes | Situación | Tu plan del mes → Ajustes | BVO ✓ | ✓ | ✓ | ◐ | discretionary_monthly_minimum | ✓ | MOVED | UX |
| H06 | Prioridad (VIP) | Situación | Tu plan del mes (UX-8) | VO ✓ | ✓ | ✓ | ◐ | — | ✓ | MERGED | = G05 |
| H07 | **Pantalla Situación** | Perfil | Se retira solo cuando H01–H06 tengan hogar con paridad; mientras tanto accesible (Plan → Ajustes) | FBVO ✓ | ✓ | ✓ | ✓ | — | ✓ | MERGED | gate §11 |

### I. Patrimonio (Users)
| # | Función actual | Ubicación actual | Nueva ubicación | Plan | iOS | And | Web lab | Backend | Owner | Estado | Depende |
|---|---|---|---|---|---|---|---|---|---|---|---|
| I01 | Patrimonio neto actual | — (solo web Owner) | Titular de Patrimonio | FBVO ✓ (D11) | — | — | ◐ | 4 fórmulas | ✓ | HRP | **P0.9** |
| I02 | Cuentas detectadas por correo | Perfil → Cuentas | Patrimonio → Cuentas | FB 🔒, VO ✓ | ✓ | ✓ | ◐ | /accounts/detected | ✓ | MOVED | UX |
| I03 | "¿Es mía?" | Monitor + Cuentas | Patrimonio → Cuentas → cuenta | VO ✓ | ✓ | ✓ | ◐ | ownership | ✓ | MERGED | UX |
| I04 | Cuenta → movimientos → corregir | Perfil → Cuentas → banco → cuenta | Patrimonio → Cuentas → cuenta (2 niveles) | VO ✓ | ✓ | ✓ | ◐ | — | ✓ | MOVED | UX |
| I05 | Saldos declarados / "Agregar cuenta sin conectar" | — (Users) | Patrimonio → Cuentas | FBVO ✓ (D11) | — | — | — | account_balances (Owner) | ✓ | HRP | **P2.8a/b/c** |
| I06 | Conectar correo (Gmail/Outlook), reautorizar, buscar avisos, estado | Perfil → Correos financieros | Patrimonio → Cuentas → Agregar cuenta / Administrar conexiones (UX-2) | FB 🔒, VO ✓ | ✓ | ✓ | ✓ | /mail-providers/* | ✓ | MOVED | UX |
| I07 | Catálogo de instituciones con soporte de lectura | onboarding (8 sin soporte real) | Agregar cuenta → buscar institución | FBVO ✓ | ◐ | ◐ | — | parser (3 bancos) | — | MOVED | backend (catálogo + soporte por institución) |
| I08 | Deudas: composición (donut) | — | Patrimonio → Deudas (lee Plan → Deudas) | FBVO ✓ | — | — | — | /finance/debts | ✓ | MERGED | UX (B2: donut) |
| I09 | Proyecciones | DINCR (FB oculto) | Patrimonio → Proyecciones (3m, 6m, 1a) | FB ✗→🔒, VO ✓ | ✓ | ✓ | ✓ | /vip/projections | ✓ | MOVED | UX (línea B2) |
| I10 | Historial patrimonial | — | Patrimonio → Historial | FB 🔒, VO ✓ | — | — | ◐ | — | ✓ | HRP | P5.2a |
| I11 | Salud financiera /100 | iOS VIP Hoy | Patrimonio → Análisis | VO ✓ | ✓ | — | ◐ | varios cálculos | ✓ | MOVED | K-2: solo factores, sin número; P3.7 |
| I12 | Lifecycle state, snapshots, progreso (sin cliente) | backend | Patrimonio → Análisis (VIP) | VO ✓ | — | — | — | /lifecycle/* | — | HRP | P0.4 + P5.2 |
| I13 | Calidad de lectura de correo (trust-analytics, sin cliente) | backend | Cuentas → Administrar conexiones | VO ✓ | — | — | — | /gmail/trust-analytics | — | HRP | UX sobre un endpoint existente |

### J. Owner: capacidades financieras e históricas
| # | Función actual | Ubicación actual | Nueva ubicación | Plan | iOS | And | Web lab | Backend | Owner | Estado | Depende |
|---|---|---|---|---|---|---|---|---|---|---|---|
| J01 | Cuentas y saldos + conciliación | web Owner Accounts | Patrimonio → Cuentas (Owner) | Ⓞ | — | — | ✓ | /finance/accounts | ✓ | HRP | P1.3a/b/c |
| J02 | Cuentas por cobrar | web Control de dinero; WIP nativo archivado | Patrimonio → Cuentas por cobrar + "+ Cobro" | Ⓞ | — | — | ✓ | /finance/receivables | ✓ | HRP | P1.5 (port de `172625b0`) |
| J03 | Inversiones (IBKR) + CRUD | web Wealth | Patrimonio → Inversiones | Ⓞ | — | — | ✓ | /finance/investment-center | ✓ | HRP | P1.9 |
| J04 | Negocios | web Wealth | Patrimonio → Negocios | Ⓞ | — | — | ✓ | sí | ✓ | HRP | P1.9 |
| J05 | Línea de tiempo | web Wealth | Patrimonio → Historial (Owner) | Ⓞ | — | — | ✓ | /finance/timeline | ✓ | HRP | P1.6 |
| J06 | Alerta temprana / deterioro | web Wealth | Patrimonio → Análisis + Hoy ③ | Ⓞ | — | — | ✓ | deterioration | ✓ | HRP | P1.6 |
| J07 | Registros (libro completo) | JARVIS (placeholder) / web | Movimientos → Lista (alcance Owner) | Ⓞ | ◐ | ◐ | ✓ | /finance/timeline, transactions | ✓ | HRP | P1.7 |
| J08 | Tarjetas adicionales | web Control de dinero | Análisis Owner / Cuentas | Ⓞ | — | — | ✓ | sí | ✓ | HRP | P1.7 |
| J09 | Ciclo de tarjeta de crédito (sin cliente) | backend | Plan → Calendario (Owner) + Análisis | Ⓞ | — | — | ◐ | credit-card cycle | ✓ | HRP | UX sobre un endpoint existente |
| J10 | Gastos fijos CRUD (sin cliente) | backend | Plan → Pagos fijos (misma pantalla, capa Owner) | Ⓞ | — | — | ◐ | fixed-expenses | ✓ | HRP | decidir fusión con recurrentes (técnico) |
| J11 | Planilla, salario, VGH, bonos, pay schedule | backend | Análisis → Ingresos (Owner); proyección en Tu plan del mes | Ⓞ | — | — | ◐ | payroll/* | ✓ | HRP | P1.10 |
| J12 | Pronóstico de flujo de caja | backend | Patrimonio → Proyecciones (Owner) | Ⓞ | — | — | ◐ | cashflow forecast | ✓ | HRP | UX sobre un endpoint existente |
| J13 | Evaluar préstamo o compra | backend | Tu plan del mes → ¿Y si? (Owner) | Ⓞ | — | — | ◐ | evaluate | ✓ | HRP | UX sobre un endpoint existente |
| J14 | Análisis de metas | backend | Plan → Metas (Owner) | Ⓞ | — | — | ◐ | goals analysis | ✓ | HRP | UX |
| J15 | Reportes semanales, mensuales y anuales | backend | Análisis → Reportes (Owner) | Ⓞ | — | — | ◐ | reports | ✓ | HRP | UX |
| J16 | Motor: pronóstico, salud, simulación | backend | Patrimonio → Análisis y Proyecciones (Owner) | Ⓞ | — | — | ◐ | engine/* | ✓ | HRP | P3.7 (puntaje canónico) |
| J17 | Alertas de moneda | backend (el GET muta) | Movimientos → Por revisar (Owner) | Ⓞ | — | — | ◐ | /transactions/currency/alerts | ✓ | HRP | **P0.2b** |
| J18 | Estrategia personal (JARVIS) | JARVIS (placeholder) / web Strategy | Tu plan del mes (capa Owner) | Ⓞ | ◐ | ◐ | ✓ | strategy-dashboard | ✓ | HRP | UX + P0.2 hecho |
| J19 | Mi dinero (JARVIS) | JARVIS (placeholder) | Hoy y Patrimonio Owner | Ⓞ | ◐ | ◐ | ✓ | — | ✓ | HRP | P1.3/P1.4 |
| J20 | Control de dinero (JARVIS) | JARVIS (placeholder) | Patrimonio → Por cobrar + Movimientos | Ⓞ | ◐ | ◐ | ✓ | receivables | ✓ | HRP | P1.5/P1.7 |
| J21 | Patrimonio (JARVIS) | JARVIS (placeholder) | Pestaña Patrimonio (Owner) | Ⓞ | ◐ | ◐ | ✓ | investment-center | ✓ | HRP | P1.4/P1.9 |
| J22 | Memoria | JARVIS (placeholder) / web | Perfil → JARVIS → Memoria | Ⓞ | ◐ | ◐ | ✓ | /jarvis/memory | ✓ | HRP | P1.8 |
| J23 | JARVIS Chat | Perfil → JARVIS | Perfil → JARVIS (+ atajo en Hoy) | Ⓞ | ✓ | ✓ | ✓ | /jarvis/chat | ✓ | OWNER | — |
| J24 | JARVIS Agenda | Perfil → JARVIS | Perfil → JARVIS (+ Hoy ④) | Ⓞ | ✓ | ✓ | ✓ | /jarvis/calendar | ✓ | OWNER | — |
| J25 | Radar deportivo | backend (el GET escribe) | Perfil → JARVIS | Ⓞ | — | — | ◐ | /jarvis/sports/radar | ✓ | HRP | **P0.2c** |
| J26 | Hub JARVIS (9 filas) | Perfil → JARVIS | Chat · Agenda · Memoria; cada placeholder sale **solo** cuando su función aterriza | Ⓞ | ✓ | ✓ | ✓ | — | ✓ | OWNER | gate por fila (R1) |

### K. Perfil
| # | Función actual | Ubicación actual | Nueva ubicación | Plan | iOS | And | Web lab | Backend | Owner | Estado | Depende |
|---|---|---|---|---|---|---|---|---|---|---|---|
| K01 | Mi plan | Perfil | Perfil → **Suscripción** (UX-12) | FBV ✓ | ✓ | ✓ | ✓ | /auth/plans | — | MOVED (en su lugar) | UX |
| K02 | Seguridad (bloqueo) | Perfil | Perfil | FBVO ✓ | ✓ | ✓ | — | — | — | MOVED (en su lugar) | — |
| K03 | Apariencia | Perfil | Perfil | FBVO ✓ | ✓ | ✓ | ✓ | — | — | MOVED (en su lugar) | — |
| K04 | Soporte | Perfil | Perfil → Ayuda y soporte | FBVO ✓ | ✓ | ✓ | ✓ | /product-ops/feedback | — | MOVED (en su lugar) | — |
| K05 | Legal | Perfil | Perfil | FBVO ✓ | ✓ | ✓ | ✓ | — | — | MOVED (en su lugar) | — |
| K06 | Descargar mis datos | Perfil | Perfil → Tus datos | FBVO ✓ | ✓ | ✓ | ✓ | /auth/me/export | — | MOVED (en su lugar) | — |
| K07 | Eliminar mi cuenta | Perfil | Perfil → Tus datos | FBV ✓, O oculta por seguridad | ✓ | ✓ | ✓ | DELETE /auth/me | oculta | MOVED (en su lugar) | — |
| K08 | Cerrar sesión | Perfil | Perfil → Tus datos | FBVO ✓ | ✓ | ✓ | ✓ | — | — | MOVED (en su lugar) | — |
| K09 | Correos financieros (fila) | Perfil | Patrimonio → Cuentas (I06) + Por revisar (F01) | FB ✗→🔒, VO ✓ | ✓ | ✓ | ✓ | — | ✓ | MOVED | UX |
| K10 | Cuentas (fila) | Perfil | Patrimonio → Cuentas (I02) | FB ✗→🔒, VO ✓ | ✓ | ✓ | ◐ | — | ✓ | MOVED | UX |
| K11 | Finanzas: Presupuesto, Calendario, Recurrentes (sección) | Perfil | Plan (G22–G24) | ver G22–G24 | ✓ | ✓ | ✓ | — | — | MOVED | UX |
| K12 | Situación financiera (fila) | Perfil | ver H07 | FBVO ✓ | ✓ | ✓ | ✓ | — | ✓ | MERGED | gate H07 |
| K13 | JARVIS (fila) | Perfil | Perfil → JARVIS | Ⓞ | ✓ | ✓ | ✓ | — | ✓ | OWNER | — |

### L. Administración (Owner)
| # | Función actual | Ubicación actual | Nueva ubicación | Plan | iOS | And | Web lab | Backend | Owner | Estado | Depende |
|---|---|---|---|---|---|---|---|---|---|---|---|
| L01 | Usuarios y cortesías | web Owner | Administración (laboratorio web; nativo opcional, K-5) | Ⓞ | — | — | ✓ | /users-admin/* | ✓ | ADMINISTRATION | — |
| L02 | Operaciones de producto (feedback, triage) | web Owner | Administración | Ⓞ | — | — | ✓ | /product-ops/* | ✓ | ADMINISTRATION | — |
| L03 | Monitor de despliegues y health | web Owner | Administración | Ⓞ | — | — | ✓ | /health, deploy events | ✓ | ADMINISTRATION | — |
| L04 | "Vincular Owner a Users" (llama a una ruta inexistente) | web Owner | Administración: llamada rota registrada; **sin borrar** | Ⓞ | — | — | ◐ | ruta inexistente | ✓ | ADMINISTRATION | decisión futura (K-7) |
| L05 | Jobs programados (historial financiero diario, notificaciones) | GitHub Actions | Administración (solo visibilidad; sin ejecución desde la app) | Ⓞ | — | — | — | /financial-history/cron, /notifications/cron | ✓ | ADMINISTRATION | — (las 28 notificaciones pendientes no se tocan) |

### M. Web y landing
| # | Función actual | Ubicación actual | Nueva ubicación | Plan | iOS | And | Web lab | Backend | Owner | Estado | Depende |
|---|---|---|---|---|---|---|---|---|---|---|---|
| M01 | App web Users (Hoy, Movimientos, Plan, DINCR, Perfil) | Vercel | **Laboratorio web interno** (sin paridad comercial) | lab | — | — | ✓ | igual | ✓ | MOVED | K-6 (restringir acceso = cambio de producción) |
| M02 | Metas VIP de solo lectura; ahorro Free inalcanzable | web | laboratorio (deuda del laboratorio) | lab | — | — | ◐ | — | — | MOVED | — |
| M03 | Componentes inalcanzables (BasicMore, FreeMore, ChatsHub, `pages/Debts.jsx` vacío) | web | laboratorio, sin cambios (no se borran) | lab | — | — | ◐ | — | — | MOVED | K-7 si algún día se limpian |
| M04 | Web Owner (Owner, Strategy, Finance, Accounts, Wealth) | Vercel | laboratorio + Administración; las capacidades financieras se llevan a nativo (matriz J) | Ⓞ | — | — | ✓ | — | ✓ | OWNER | P1.x |
| M05 | Landing dincr.com | landing | landing (sin cambio) | público | — | — | — | — | — | MOVED (en su lugar) | — |

### N. Pestaña DINCR (contenedor)
| # | Función actual | Ubicación actual | Nueva ubicación | Plan | iOS | And | Web lab | Backend | Owner | Estado | Depende |
|---|---|---|---|---|---|---|---|---|---|---|---|
| N01 | Pestaña DINCR | barra, posición 4 | **Patrimonio** ocupa su lugar | FBVO ✓ | ✓ | ✓ | ✓ | — | ✓ | MOVED | gate §11: E01, E02, E03, B12/"DINCR hoy", I09, G06 en VERIFIED |
| N02 | "DINCR hoy" (alertas VIP) | DINCR (FB oculto) | Hoy ③ Para atender + "Ver todas" | VO ✓ | ✓ | ✓ | ✓ | /vip/today | ✓ | MERGED | UX (§5.1) |
| N03 | Fila "Director financiero" bloqueada (Android) / filas VIP ocultas (iOS) | DINCR | filas bloqueadas en Plan y Patrimonio | FB 🔒 | ◐ | ✓ | — | — | — | MOVED | UX (P6.4) |
| N04 | Tarjeta vacía con VIP y el flag apagado (Android) | DINCR | fila "En pausa" (ambas) | V | — | ◐ | — | flags | — | MOVED | UX |

**Total:** 154 filas.
- MOVED: 75, de ellas 29 *en su lugar*.
- MERGED: 27.
- CONTEXTUAL: 1.
- OWNER: 13.
- ADMINISTRATION: 5.
- HRP: 33.
- Borradas u ocultas: **0**.

Las 40 funciones del spec de alcance están cubiertas: `tab.*` → N01 y §3; `home.*` → B16/G07/G16; `owner.home` → C; `movements.list` → D; `plan.*` → G; `advisor.*` → E/N/I09/G06; `profile.*` → K/H/I06/G22–24; `jarvis.*` → J/E07.

---

## 11. Gate de retiro de la pestaña DINCR (UX-13)

Antes de que el PR de retiro pueda mergearse, cada función debe estar en **VERIFIED**:

| Función de la pestaña DINCR | Nueva ubicación | iOS | Android | Test de alcance | Estado del gate |
|---|---|---|---|---|---|
| Resumen del mes (`advisor.summary`) | Movimientos → Análisis → Resumen | ☐ | ☐ | spec + UI test | PENDING |
| Reportes (`advisor.reports`) | Análisis → Reportes (Free 🔒) | ☐ | ☐ | spec + UI test | PENDING |
| DINCR hoy (`advisor.today`) | Hoy → Para atender + Ver todas | ☐ | ☐ | spec + UI test | PENDING |
| Proyecciones (`advisor.projections`) | Patrimonio → Proyecciones | ☐ | ☐ | spec + UI test | PENDING |
| Escenarios (`advisor.scenarios`) | Patrimonio → Proyecciones → Escenarios | ☐ | ☐ | spec + UI test | PENDING |
| Revisión mensual (`advisor.review`) | Análisis → Revisión del mes | ☐ | ☐ | spec + UI test | PENDING |
| Fila bloqueada "Director" / filas VIP ocultas | Filas bloqueadas en los nuevos hogares | ☐ | ☐ | spec (estado VISIBLE_LOCKED) | PENDING |

**Reglas del gate:**
1. Se codifica en `native/feature-reachability.json` (P6.1): cada `advisor.*` recibe su nueva ubicación. Los tests de iOS y Android (`FeatureReachabilitySpecTests` / `FeatureReachabilityUITests`, `FeatureReachabilitySpecTest` / `FeatureReachabilityUiTest`) prueban **por plan** que la función se alcanza en la nueva ubicación.
2. Si **una sola** fila queda en PENDING, el PR de retiro **no se mergea**.
3. **El mismo gate aplica a** la pantalla Situación (H07), la sección Finanzas de Perfil (K11), la fila Correos (K09) y cada placeholder de JARVIS (J26).
4. La etiqueta `reachability-change-approved` la pone **una persona**.

---

## 12. Clasificación del trabajo

| Clase | Qué incluye |
|---|---|
| **UX-only** (cliente nativo; sin backend, sin lógica financiera ni migración) | Tonos de mensaje (§5.1) y su mapeo · librería de gráficos (donut, línea, progreso, sparkline, indicador) · "Mi plan" → "Suscripción" · glosario, cuando se valide cada término · hub de Plan con Deudas, Metas y ahorro, Presupuesto, Calendario y Pagos fijos (pantallas existentes) · Movimientos segmentado (Lista / Análisis / Por revisar con las pantallas existentes) · Hoy de 4 bloques con datos existentes · donut de deudas en Patrimonio (presentación de `remaining_amount`) · Patrimonio con Cuentas detectadas, conexiones de correo, Proyecciones y Escenarios existentes · filas bloqueadas en vez de ocultas (P6.4) · fila "En pausa" · paridad de presupuesto y próximos en Hoy, deslizar para actualizar y nudges según el plan · mover el Análisis Owner (conservando el acceso en JARVIS hasta la paridad) · aviso de proyección en Hoy (si el endpoint ya lo indica) |
| **Requiere backend** (sin lógica financiera canónica) | Gate Free para pagos fijos (UX-9) · catálogo de instituciones con soporte de lectura e institución por cuenta (UX-2, B4) · preferencias editables (P2.12) · contadores de Por revisar (P5.5) · endpoint de análisis con filtros, comercios y tendencias (P5.1) · guardar el override de prioridad para todos los planes (UX-8) · test de guarda de `usage_goal` · Free edita deudas y metas (P2.1) · categorías canónicas (P2.9) · saldos declarados de Users (P2.8a) |
| **Requiere lógica financiera canónica** | Patrimonio neto (P0.9) · Salvavidas para todos (P3.1–P3.4) · esenciales desde pagos fijos (P3.0–P3.2) · prioridad propuesta con datos reales consistente (P3.7) · puntaje de salud canónico (P3.7) · reparto canónico en Tu plan del mes (P3.7) · base de ingreso (`income_policy`, P0.6/P0.7) · ledger unificado y tipos fieles (P0.3a) · pagos de deuda unificados (P2.2a) |
| **Requiere migración** | Deudas automáticas (cuotas esperadas e indicador opt-in, §8; probable) · `goal_allocations` (P3.3a) · `is_essential` (P3.0a, columna) · institución por cuenta, si no cabe en `account_balances.bank_name` (a evaluar) |
| **Requiere decisión de Kenneth** | ninguna abierta para el bloque UX (§14) |

---

## 13. Bloqueos

| # | Bloqueo | Afecta a | Desbloqueo |
|---|---|---|---|
| X1 | Patrimonio neto: 4 fórmulas, sin canónica | titular de Patrimonio (I01) | P0.9; mientras tanto Patrimonio se publica **sin titular** (K-3, aprobado) |
| X2 | Users sin saldos declarados | "Agregar cuenta sin conectar" (I05), ahorro desde Cuentas (H02, G19) | P2.8a/b/c |
| X3 | La automatización de deudas existente asume el pago (B5) | G15 | diseño §8 + K-4; no conectar lo existente |
| X4 | Varios puntajes de salud | I11/B14 | K-2 aprobado: solo factores; P3.7 |
| X5 | Ingreso declarado sin hogar al desaparecer Situación | H01 | **resuelto (K-1):** Plan → Ingresos sobre `financial_profiles` |
| X6 | Agregar Patrimonio antes del retiro daría 6 pestañas (B8) | N01 | PR de intercambio con el gate de §11 |
| X7 | Android sin gráficos de composición ni evolución (B2) | donut de deudas, categorías, proyecciones | PR de librería de gráficos (UX-only) |
| X8 | Las alertas usan el tono de error (B1) | UX-5 | PR de tonos (UX-only) |
| X9 | Cuentas: 8 instituciones contra 3 con lectura (B3/B4) | flujo UX-2 | backend de catálogo; mientras tanto la UI marca "solo manual" |
| X10 | Mover funciones requiere la etiqueta humana `reachability-change-approved` | todos los PRs de reubicación | Kenneth pone la etiqueta por PR |
| X11 | Alertas de moneda y radar deportivo escriben desde un GET | J17, J25 | P0.2b, P0.2c (orden P0 vigente) |
| X12 | Posible heurística Owner (CCSS) en la consulta compartida de Gmail (B6) | invariante A | revisión aparte; fuera de este alcance |

---

## 14. Decisiones K, cerradas (2026-10-04)

**No queda ninguna decisión K abierta para el bloque UX.**

**K-1. Ingreso o salario declarado: APROBADO**
- Mientras DINCR no pueda obtener de forma fiable la planilla real de todos, **el usuario declara su salario o ingreso recurrente**: monto y frecuencia (semanal, quincenal o mensual).
- **Fuente canónica existente, reutilizada sin crear una segunda:** `financial_profiles`. Sus campos son:
  - `income_type`: fixed / hourly;
  - `fixed_monthly_salary`;
  - `hourly_rate`, `hours_per_day`, `work_days_per_week`;
  - `pay_frequency`: weekly / biweekly / monthly, exactamente las tres frecuencias aprobadas;
  - `payday_note`.

  La escribe `UnifiedOnboardingRequest` (`auth/models.py`, `auth/saas.py`) y hoy se edita en Perfil → Situación. Su nuevo hogar visible es **Plan → Ingresos** (la misma fuente, editada desde otro lugar). Esto **reemplaza** la idea anterior de modelarlo como pago fijo de tipo ingreso, que habría creado una segunda fuente.
- **Semántica existente que no se reinterpreta:**
  - `fixed_monthly_salary` es un monto **mensual** ("el salario que realmente te llega al mes");
  - `pay_frequency` describe **cada cuánto se paga**.
  - Pedir el monto *por pago* sería comportamiento nuevo: no se hace sin decisión.
- **Regla:** salario declarado o esperado ≠ ingreso real confirmado.
  - El declarado es **ingreso esperado para planificar**.
  - DINCR **no inventa** horas extra, feriados, bonos, rebajos, vacaciones, incapacidades, comisiones ni deducciones.
  - **No crea transacciones de salario** al llegar la fecha.
  - El ingreso real solo viene de un movimiento detectado, evidencia fiable, una futura automatización de planillas o un registro o corrección explícita del usuario.
  - Es el mismo patrón que las deudas: esperado/programado ≠ ocurrido/confirmado.
  - `income_policy` sigue arbitrando cuál base usa cada motor; este bloque no la cambia.

**K-2. Salud financiera: APROBADO**
- Mientras no exista **un único** cálculo canónico y confiable, **no se muestra ningún número /100**, tampoco "74/100 preliminar" ni variantes.
- Solo se muestran **factores comprensibles y visuales** con estado: "Salvavidas mejorando", "Deuda alta", "Gastos bajo control", "Ahorro estable".
- El puntaje se incorpora cuando P3.7 lo resuelva.
- Los cálculos históricos **no se eliminan**.
- **Nota de preservación:** iOS VIP Hoy muestra hoy un número. Cambiarlo a factores es la decisión explícita de Kenneth (no un ocultamiento por R1). Se aplica en el PR de Hoy/Patrimonio, con el dato de factores tomado solo de campos que el backend ya entrega; sin factores fiables, la tarjeta no inventa ninguno.

**K-3. Patrimonio antes de P0.9: APROBADO**
- Patrimonio se construye y publica antes de P0.9, **sin un número grande de "Patrimonio neto"**.
- Muestra solo datos fiables: cuentas, ahorros, deudas, composición, distribución, detalles y visualizaciones.
- No se inventa ni se aproxima el patrimonio neto. El número principal llega con P0.9.

**K-4. Deudas automáticas: RESUELTO**
- **No se conecta** `apply_due_installments`.
- Se diseña después la cadena cuota esperada → fecha → evidencia o confirmación → pago confirmado → capital, interés y otros → saldo → conciliación y reversión (§8).
- Fuera de este bloque.

**K-5. Administración: RESUELTO**
- Separada e interna.
- No hay pantallas administrativas en Hoy, Movimientos, Plan, Patrimonio ni Perfil, salvo funciones financieras o personales del Owner con hogar natural allí.

**K-6. Laboratorio web: RESUELTO**
- La intención es restringirlo al Owner.
- **No se cambia la configuración de producción ahora:** queda registrado como trabajo separado, con autorización explícita, fuera de los PRs UX.

**K-7. Web rota o inalcanzable: RESUELTO**
- Se documenta (matriz L04, M02, M03) y **no se repara esta semana** salvo que afecte a iOS, Android, backend necesario, seguridad o integridad, o bloquee el laboratorio en uso.
- **No se elimina silenciosamente.**

## 15. Orden mínimo de PRs

**Objetivo de esta semana:** una versión estable, coherente y visualmente simplificada.

**Reglas para cada PR:**
- rama nueva desde `origin/main`, con `base=main` y sin apilar;
- iOS y Android en el mismo PR (o gemelos que se mergean juntos);
- sin backend salvo donde se indica;
- sin lógica financiera;
- spec de alcance actualizado y tests por plan;
- reversible con un revert;
- capturas de iOS y Android;
- validación física declarada aparte.

### 15.1 Pueden empezar de inmediato (UX-only, sin dependencia de P0)
| Orden | PR | Contenido | Etiqueta humana |
|---|---|---|---|
| **1** | `ux/message-tones` | `DincrMessage` con 4 tonos en iOS y Android; mapeo `severity` → tono; los banners técnicos pasan a Error técnico; las alertas financieras dejan de usar `.error` (corrige B1) | — |
| **2** | `ux/chart-kit` | `DonutChart`, `LineTrend`, `ProgressRing`, `Sparkline` y `StatusIndicator` en ambos sistemas de diseño, con previews y tests de accesibilidad; sin pantallas nuevas | — |
| **3** | `ux/reachability-target-ia` (P6.1) | spec con la nueva ubicación de cada función (old + new); tests que codifican ambas; sin mover nada | — |
| **4** | `ux/subscription-rename-and-locked-rows` | "Mi plan" → "Suscripción"; lo oculto por plan pasa a filas bloqueadas (Reportes Free, filas VIP de DINCR en iOS, Finanzas Free en Perfil, Correos y Cuentas para F/B); fila "En pausa" con VIP y el flag apagado (P6.4) | `reachability-change-approved` (cambia los estados del spec) |
| **5** | `ux/plan-hub` | Plan agrega Deudas, Metas y ahorro, Presupuesto, Calendario y Pagos fijos (pantallas existentes); **los accesos viejos siguen** | — |
| **6** | `ux/movements-segments` | Movimientos con Lista / Análisis / Por revisar. Análisis aloja Resumen, Reportes y Revisión mensual sin cambios, más los gráficos que salen de Hoy. Por revisar aloja la revisión de correo existente (VIP). Accesos viejos intactos | — |
| **7** | `ux/home-four-blocks` | Hoy con ① ② ③ ④ a partir de datos existentes; Para atender absorbe "DINCR hoy" (máximo 3 y Ver todas); nudges según el plan; paridad de presupuesto, próximos y deslizar para actualizar. Los gráficos ya viven en Análisis (PR 6), así que nada se pierde | `reachability-change-approved` |
| **8** | `ux/patrimonio-swap` | Pestaña Patrimonio **en lugar de** DINCR: Cuentas (detectadas + conexiones de correo + catálogo con "solo manual" donde no hay lectura), donut de deudas, Proyecciones y Escenarios, salud con solo factores (K-2) y sin número de patrimonio neto (K-3). **Gate §11 en VERIFIED** para todas las filas | `reachability-change-approved` + K-2 y K-3 |
| **9** | `ux/glossary-pass-1` | solo los términos del §5.3 que Kenneth valide semánticamente | revisión de Kenneth |

**Mínimo estable para esta semana:** PRs 1 a 7. El 8 entra solo si el gate §11 está completo (K-2 y K-3 ya están aprobados).

**Fuera de esta semana, también sin P0:**
- **10** `ux/profile-cleanup`: retirar de Perfil la sección Finanzas y las filas Correos y Cuentas, porque ya viven en Plan y Patrimonio. Gate §11 por fila, con etiqueta.
- **11** `ux/owner-analysis-placement`: Análisis Owner en Movimientos, conservando el acceso en JARVIS hasta la paridad.

### 15.2 Backend pequeño, sin lógica canónica (pueden ir en paralelo a P0)
| PR | Contenido | Nota |
|---|---|---|
| `be/free-recurring-gate` (UX-9) | Free crea, edita y elimina pagos fijos; tests del gate por plan; spec `profile.recurring` Free → AVAILABLE | no toca cálculos; etiqueta de alcance |
| `be/usage-goal-guard` (UX-1) | test que prueba que ningún motor lee `usage_goal` | solo un test |
| `be/institutions-catalog` (UX-2) | catálogo con `reading_supported` por institución; institución por cuenta (evaluar si basta `bank_name`) | posible migración: confirmar antes |
| `be/editable-preferences` (P2.12) | PATCH de nombre, moneda y formato | — |
| `be/review-counts` (P5.5) | contadores de Por revisar | lectura pura |
| `be/priority-override` (UX-8) | guardar la prioridad elegida por el usuario para todos los planes, separada de la propuesta | sin cambiar el motor; posible migración: confirmar |

### 15.3 Deben esperar P0, backend canónico o diseño
| PR | Espera |
|---|---|
| Titular de patrimonio neto | P0.9 |
| "Agregar cuenta sin conectar" y ahorro desde Cuentas | P2.8a/b/c |
| Salvavidas para Free/Basic; esenciales desde pagos fijos; retirar los campos de Situación | P3.0–P3.4, P3.6 |
| Prioridad propuesta con datos reales; reparto canónico; puntaje de salud canónico | P3.7 (y P0.6/P0.7) |
| Filtros por tipo fiel; tipos especiales en "+ Otro" | P0.3a/b/c, P2.14/P2.15 |
| Análisis con comercios y tendencias completas | P5.1 |
| Historial patrimonial | P5.2a |
| Historial y reversión de pagos de deuda | P2.2a/b, P2.6 |
| Deudas automáticas (Owner y VIP opt-in) | diseño §8 + K-4 + probable migración |
| Retiro de la pantalla Situación | P2.8 + P3.x (gate H07); K-1 resuelto |
| Capacidades Owner en Patrimonio y Movimientos | P1.2–P1.10; alertas de moneda P0.2b; deportes P0.2c |

**Encaje con el plan maestro:**
- El orden P0 vigente no cambia: #319 (pendiente de autorización, no se toca), luego P0.2b, luego P0.2c, luego P0.3a.
- Los PRs UX 1 a 9 **no tocan el backend ni los datos**, así que pueden avanzar en paralelo sin competir con P0.

---

*Fin del documento. Decisiones K-1 a K-7 cerradas (2026-10-04). La implementación comienza por el PR UX-1 (tonos de mensaje).*
