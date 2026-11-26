# Tareas: Álbumes de fotos compartidos

## Fase 1: Preparación

- [x] T001 Crear la estructura de backend y frontend según plan.md
- [x] T002 [P] Configurar ruff, mypy y eslint
- [ ] T003 [P] Preparar PostgreSQL y el almacenamiento de objetos en docker-compose

## Fase 2: Base

- [ ] T004 Crear los modelos Álbum, Foto y Membresía en backend/src/api/models.py
- [ ] T005 [P] Implementar la lectura de EXIF y el borrado de GPS en backend/src/photos_core/exif.py
- [ ] T006 [P] Implementar la generación de miniaturas en backend/src/photos_core/thumbs.py

## Fase 3: Historia de usuario 1 - Crear un álbum y subir fotos (P1)

- [ ] T007 [US1] Prueba de contrato de POST /albums en backend/tests/contract/test_albums.py
- [ ] T008 [US1] Implementar POST /albums y GET /albums
- [ ] T009 [P] [US1] Implementar el endpoint de URL de subida prefirmada
- [ ] T010 [US1] Tarea en segundo plano: miniatura, conversión de HEIC y borrado de GPS al subir
- [ ] T011 [P] [US1] Página de cuadrícula del álbum ordenada por fecha de captura en frontend/src/pages/Album.tsx

## Fase 4: Historia de usuario 2 - Invitar a los parientes con un enlace (P1)

- [ ] T012 [US2] Generar el token de invitación al crear el álbum
- [ ] T013 [US2] Endpoint para unirse al álbum con el enlace de invitación
- [ ] T014 [P] [US2] Página para unirse en frontend/src/pages/Join.tsx

## Fase 5: Historia de usuario 3 - Correo con el resumen semanal (P2)

- [ ] T015 [US3] Tarea horaria de Celery beat que selecciona a los miembros en su lunes a las 08:00
- [ ] T016 [P] [US3] Plantilla del correo del resumen con miniaturas

## Fase 6: Pulido

- [ ] T017 [P] Prueba de principio a fin con Playwright: crear, invitar, subir
- [ ] T018 Prueba de carga: 10 subidas en paralelo con una conexión limitada a 20 Mbps
