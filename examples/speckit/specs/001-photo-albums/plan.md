# Implementation Plan: Shared Photo Albums

**Branch**: `001-photo-albums` | **Date**: 2026-11-21 | **Spec**: [spec.md](./spec.md)

## Summary

Web app with a REST API. Photos go straight from the browser to object storage with presigned URLs;
a background worker builds thumbnails, strips GPS data and sends the weekly digest.

## Technical Context

**Language/Version**: Python 3.12 (API, worker), TypeScript 5 (web)
**Primary Dependencies**: FastAPI, SQLAlchemy, Celery, React 19
**Storage**: PostgreSQL 16 for metadata, S3-compatible object storage for files
**Testing**: pytest, Playwright
**Target Platform**: Linux containers on Kubernetes
**Project Type**: web
**Performance Goals**: 10 photo uploads in under 30 s on 20 Mbps
**Constraints**: [NEEDS CLARIFICATION: monthly storage budget per family]
**Scale/Scope**: 5k families in the first year

## Constitution Check

- Library-first: thumbnail and EXIF handling live in `photos_core`, independent from the API. PASS
- Test-first: contract tests before endpoints. PASS

## Project Structure

```text
backend/
  src/api/  src/worker/  src/photos_core/
  tests/contract/  tests/integration/
frontend/
  src/pages/  src/components/
```
