# Tasks

## 1. Data model

- [x] 1.1 Add `expires_at` to the album invite token
- [ ] 1.2 Migration: set existing tokens to expire 30 days after release

## 2. API

- [ ] 2.1 POST /albums/{id}/invite/rotate rotates the token
- [ ] 2.2 Reject expired tokens on join with a dedicated error
- [ ] 2.3 Allow owners to delete any photo

## 3. Web

- [ ] 3.1 Revoke button and confirmation on the album settings page
- [ ] 3.2 Expired-link message on the join page

## 4. Notifications

- [ ] 4.1 Daily job that emails owners 3 days before expiry
