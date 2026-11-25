# Design

## Context

Today each album has one permanent invite token stored on the album row. Joining checks only that the token matches.

## Goals / Non-Goals

**Goals:**
- Revoke a leaked link in one click.
- Keep joining as easy as today for relatives.

**Non-Goals:**
- Per-person invitations.

## Decisions

### Rotate the token instead of keeping a denylist

Revoking replaces the album's token with a new random one, so every old link stops working at once. A denylist was considered, but it grows forever and must be checked on every join.

### Store an expiry next to the token

Each token gets an `expires_at`. The default lifetime comes from configuration so it can change without a migration.

### Owners moderate photos, members do not

Only the album owner can delete photos uploaded by others. Members can still delete their own.

## Risks / Trade-offs

- [Risk] Relatives with an old link are locked out after rotation → The join page explains the link expired and who to ask for a new one.
- [Risk] Expiry silently breaks links shared in printed invitations → Owners get an email 3 days before a link expires.
- [Trade-off] Rotation invalidates every outstanding link, including legitimate ones → Acceptable: rotation is a deliberate owner action.

## Open Questions

- What should the default link lifetime be: 7, 30 or 90 days?
- Should members who joined through a revoked link stay in the album?
