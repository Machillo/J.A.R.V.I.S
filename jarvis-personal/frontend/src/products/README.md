# Frontend por producto y plataforma

Esta carpeta mantiene separadas las experiencias de JARVIS y FINVA sin duplicar cálculos ni llamadas de API.

## Productos

- `finva/`: navegación, estilos y módulos de la aplicación comercial.
- `jarvis/`: navegación, estilos y módulos del laboratorio personal.

Cada función nueva debe vivir en `products/<producto>/features/<función>/`. El resumen de FINVA es el ejemplo completo: componente y estilos están juntos en `finva/features/overview/`.

## Plataformas

Los componentes y estilos que cambian por sistema operativo viven en `ui/native/`:

- `styles/ios.css`: superficies flotantes, navegación tipo cápsula y mayor desenfoque.
- `styles/android.css`: navegación inferior pegada al borde y ajustes táctiles de Android.
- `styles/tokens.css`: medidas y comportamiento compartido.
- `styles/sheets.css`: hojas de navegación y menús secundarios compartidos.

La lógica financiera nunca debe duplicarse por plataforma. Android y iOS comparten datos y funciones; solo cambia la presentación nativa.

## Sistema visual

- JARVIS y FINVA comparten tarjetas, formularios, encabezados, hojas y espaciado desde `ui/native`.
- Los archivos de cada producto solo definen color y compatibilidad con sus pantallas existentes.
- FINVA aplica una variante de color por plan: `free`, `basic` o `vip`.
- Cada producto mantiene cinco accesos principales. Las funciones secundarias se organizan en **Más** para que ninguna ruta desaparezca cuando la app crezca.
