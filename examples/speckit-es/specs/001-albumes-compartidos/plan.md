# Plan de implementación: Álbumes de fotos compartidos

**Rama**: `001-albumes-compartidos` | **Fecha**: 2026-11-21 | **Spec**: [spec.md](./spec.md)

## Resumen

Aplicación web con una API REST. Las fotos van del navegador directamente al almacenamiento de objetos con URL prefirmadas;
un proceso en segundo plano genera miniaturas, elimina los datos GPS y envía el resumen semanal.

## Contexto técnico

**Lenguaje/Versión**: Python 3.12 (API, proceso en segundo plano), TypeScript 5 (web)
**Dependencias principales**: FastAPI, SQLAlchemy, Celery, React 19
**Almacenamiento**: PostgreSQL 16 para los metadatos, almacenamiento de objetos compatible con S3 para los archivos
**Pruebas**: pytest, Playwright
**Plataforma objetivo**: contenedores Linux en Kubernetes
**Tipo de proyecto**: web
**Objetivos de rendimiento**: 10 fotos subidas en menos de 30 s con 20 Mbps
**Restricciones**: [NEEDS CLARIFICATION: presupuesto mensual de almacenamiento por familia]
**Escala/Alcance**: 5.000 familias el primer año

## Comprobación de la constitución

- Primero las bibliotecas: las miniaturas y el EXIF viven en `photos_core`, independiente de la API. CUMPLE
- Primero las pruebas: pruebas de contrato antes que los endpoints. CUMPLE

## Estructura del proyecto

```text
backend/
  src/api/  src/worker/  src/photos_core/
  tests/contract/  tests/integration/
frontend/
  src/pages/  src/components/
```
