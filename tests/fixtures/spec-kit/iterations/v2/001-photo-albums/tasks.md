# Tasks: Shared Photo Albums

## Phase 1: Setup

- [x] T001 Create backend and frontend project structure per plan.md
- [x] T002 [P] Configure ruff, mypy and eslint
- [x] T003 [P] Provision PostgreSQL and object storage in docker-compose

## Phase 2: Foundational

- [ ] T004 Create Album, Photo and Membership models in backend/src/api/models.py
- [ ] T005 [P] Implement EXIF reader and GPS stripping in backend/src/photos_core/exif.py
- [ ] T006 [P] Implement thumbnail generation in backend/src/photos_core/thumbs.py

## Phase 3: User Story 1 - Create an album and upload photos (P1)

- [ ] T007 [US1] Contract test POST /albums in backend/tests/contract/test_albums.py
- [ ] T008 [US1] Implement POST /albums and GET /albums
- [ ] T009 [P] [US1] Implement presigned upload URL endpoint
- [ ] T010 [US1] Worker job: thumbnail, HEIC conversion, GPS stripping on upload
- [ ] T011 [P] [US1] Album grid page sorted by date taken in frontend/src/pages/Album.tsx

## Phase 4: User Story 2 - Invite relatives by link (P1)

- [ ] T012 [US2] Generate invite token on album creation
- [ ] T013 [US2] Join album via invite link endpoint
- [ ] T014 [P] [US2] Join page in frontend/src/pages/Join.tsx
- [ ] T019 [US2] Revoke invite link endpoint and button

## Phase 5: User Story 3 - Weekly digest email (P2)

- [ ] T015 [US3] Hourly Celery beat job selecting members at Monday 08:00 local time
- [ ] T016 [P] [US3] Digest email template with thumbnails

## Phase 6: Polish

- [ ] T017 [P] Playwright end-to-end test for create, invite, upload
