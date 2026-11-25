# Research: Shared Photo Albums

## Upload path

- **Decision**: Browser uploads directly to object storage with presigned URLs.
- **Rationale**: Keeps 25 MB files off the API servers and meets the 30 s upload goal.
- **Alternatives considered**: Upload through the API; tus resumable uploads

## Invite model

- **Decision**: One invite token per album that expires after 30 days and can be revoked by the owner.
- **Rationale**: Lowest friction for non-technical relatives.
- **Alternatives considered**: Per-person email invites; expiring links; view-only links plus upload approval

## HEIC support

- **Decision**: Convert HEIC to JPEG in the worker and keep the original.
- **Rationale**: Most browsers cannot render HEIC.
- **Alternatives considered**: Reject HEIC; convert in the browser

## Digest delivery

- **Decision**: Celery beat job every hour that sends digests to members whose local time is Monday 08:00.
- **Rationale**: Respects timezones without one job per user.
- **Alternatives considered**: One scheduled job per user; send everyone at 08:00 UTC
