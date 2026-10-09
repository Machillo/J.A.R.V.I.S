# Product decisions

`DINCR_UX_RESTRUCTURE_PROPOSAL.md` is the UX restructure approved on 2026-10-04 (decisions UX-1 to UX-16 and K-1 to K-7), kept here as an exact copy. It is not edited: where a later merged decision placed a function somewhere else, the later decision wins. The current location of every function is in `jarvis-personal/native/feature-reachability.json`.

## Later decisions that replace locations in the document

| Document | Replaced by |
|---|---|
| §3 navigation and §15 PR 8: Patrimonio "in place of" DINCR with Cuentas, connections, debt donut, projections, scenarios and health factors | UX-13 (#335): Patrimonio holds Proyecciones and Escenarios only; Movimientos → Análisis holds Resumen, Reportes and Revisión del mes; DINCR hoy moved to Hoy → Para atender. Cuentas, the debt donut and the health factors are not in Patrimonio yet. |
| §1 UX-12 / §15 PR 4 "Mi plan" → "Suscripción" | UX-12 (#334): Perfil → Suscripción. |
| §6.6 / H rows: Situación fields | UX-7 (#330): Plan → Ingresos y base; savings and the emergency target in Metas y ahorros → Tus ahorros; plan settings in Tu plan del mes → Ajustes. |
| §1 UX-8: DINCR proposes the priority and lets the user change it; §15.2 `be/priority-override` | UX-8 (#331): the recommended priority is shown, with no free priority choice. |
| §1 UX-14: projections in Patrimonio; Hoy warns on a relevant change | UX-14 (#336): projections in Patrimonio never use unknown inputs; the Hoy warning waits for an approved definition of a material change. |
| §1 UX-15 / K-2: health in Patrimonio → Análisis | K-2 fix (#337): no public /100 score; UX-15 stays blocked until P3.7. |
| §15 PR 4: locked rows in Perfil (Correos, Cuentas, Finanzas) | Applied where these rows live today: Perfil (decision PR-4 in the reachability spec). |
| §15 PR 10: retire Perfil's Finanzas section and the Correos and Cuentas rows | Partly applied (decision PR-10): Correos and Cuentas left Perfil; they live in Patrimonio → Cuentas / Conexiones de correo and Movimientos → Por revisar. Finanzas (Presupuesto, Calendario, Recurrentes) stays in Perfil: its new home in Plan (§15 PR 5) is not confirmed. |
| §15 PR 5: Plan adds Metas y ahorro, Presupuesto, Calendario and Pagos fijos | Not applied. The code keeps those rows outside Plan (Metas on Hoy, Presupuesto, Calendario and Recurrentes in Perfil → Finanzas); this needs a product confirmation before any change. |

Implementation numbering: the commits titled "UX-1" (message kinds, #320) and "UX-2" (visual components, #321) follow §15's PR order, not the decisions UX-1 (onboarding) and UX-2 (Cuentas), which are still pending.
