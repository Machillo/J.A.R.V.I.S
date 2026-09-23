# Frontend por experiencia y plataforma

Esta carpeta mantiene separadas la experiencia comercial DINCR y la experiencia interna DINCR Owner sin duplicar cálculos ni llamadas de API. Los nombres de carpetas son identificadores históricos.

## Experiencias

- `dincr/`: navegación, estilos y módulos de la aplicación comercial.
- `jarvis/`: navegación, estilos y módulos internos DINCR Owner (nombre histórico de carpeta).

Cada función nueva debe vivir en `products/<producto>/features/<función>/`. El resumen de DINCR es el ejemplo completo: componente y estilos están juntos en `dincr/features/overview/`.

## Plataformas

Los componentes y estilos que cambian por sistema operativo viven en `ui/native/`:

- `styles/ios.css`: superficies flotantes, navegación tipo cápsula y mayor desenfoque.
- `styles/android.css`: navegación inferior pegada al borde y ajustes táctiles de Android.
- `styles/tokens.css`: medidas y comportamiento compartido.
- `styles/sheets.css`: hojas de navegación y menús secundarios compartidos.

La lógica financiera nunca debe duplicarse por plataforma. Android y iOS comparten datos y funciones; solo cambia la presentación nativa.

## Sistema visual

- DINCR y DINCR Owner comparten tarjetas, formularios, encabezados, hojas y espaciado desde `ui/native`.
- Los archivos de cada experiencia solo definen color y compatibilidad con sus pantallas existentes.
- DINCR aplica una variante de color por plan: `free`, `basic` o `vip`.
- Cada experiencia mantiene cinco accesos principales. Las funciones secundarias se organizan en **Más** para que ninguna ruta desaparezca cuando la app crezca.
