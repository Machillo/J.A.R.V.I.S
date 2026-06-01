# J.A.R.V.I.S

> Just A Rather Very Intelligent System

Proyecto personal inspirado en JARVIS de Iron Man.

El objetivo es construir un asistente personal capaz de gestionar información, finanzas, metas, tareas, eventos, memoria y automatizaciones mediante lenguaje natural.

---

# Visión del Proyecto

JARVIS será un sistema capaz de:

* Comprender instrucciones en lenguaje natural.
* Gestionar finanzas personales.
* Mantener memoria persistente.
* Administrar metas y proyectos.
* Analizar deudas, ahorros e inversiones.
* Consultar información en internet.
* Interactuar mediante voz.
* Funcionar desde PC y teléfono.
* Actuar como un asistente personal centralizado.

---

# Estado Actual

## Fase 1 — JARVIS CORE

Completada ✅

Características implementadas:

* Usuario persistente.
* Configuración persistente.
* Fecha y hora.
* Zona horaria.
* Eventos.
* Logs.
* SQLite.
* API REST con FastAPI.
* Brain → Interpreter → Router.

---

# Tecnologías

## Backend

* Python 3.11+
* FastAPI
* SQLite

## Frontend (planeado)

* React
* TypeScript
* Vite

## Base de Datos

* SQLite (actual)
* PostgreSQL (futuro)

---

# Flujo del Sistema

```text
Usuario
   ↓
Brain
   ↓
Interpreter
   ↓
Router
   ↓
Módulo correspondiente
   ↓
Respuesta
```

Ejemplo:

```text
¿Qué hora es?

↓

Interpreter

↓

GET_TIME

↓

Router

↓

Time Module

↓

Respuesta
```

---

# API Disponible

## Estado General

```http
GET /status
```

Obtiene:

* Usuario
* Configuración
* Fecha
* Hora

---

## Preguntas a JARVIS

```http
POST /ask
```

Body:

```json
{
  "text": "qué hora es"
}
```

---

## Eventos

Crear:

```http
POST /events
```

Consultar:

```http
GET /events
```

---

## Logs

Consultar:

```http
GET /logs
```

---


# Objetivo Final

Construir un asistente personal capaz de comprender la situación financiera, laboral y personal del usuario para ayudarle a tomar mejores decisiones y ejecutar acciones mediante lenguaje natural.

---

# Autor

Kenneth Alvarado

Proyecto personal de aprendizaje y construcción de un asistente inteligente inspirado en J.A.R.V.I.S.
