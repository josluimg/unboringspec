# Proposal

## Why

Album invite links never expire and cannot be revoked. A link forwarded to the wrong group chat exposes a family's photos and lets strangers upload, and the owner has no way to stop it.

## What Changes

- Owners can revoke an album's invite link; a new link is issued at once.
- Invite links expire after a configurable period.
- Owners can delete photos uploaded by any member.
- **BREAKING**: permanent invite links are removed. Links created before this change expire 30 days after release.

## Capabilities

### New Capabilities
- `notifications`: notify owners when a link is revoked or about to expire.

### Modified Capabilities
- `albums`: invite links become revocable and expiring; owners can moderate photos.

## Impact

Album API (`/albums/{id}/invite`), the join flow, the web join page, and the weekly digest job.
