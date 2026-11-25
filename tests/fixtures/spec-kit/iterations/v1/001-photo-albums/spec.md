# Feature Specification: Shared Photo Albums

**Feature Branch**: `001-photo-albums`
**Created**: 2026-11-20
**Status**: Draft
**Input**: User description: "Let families create shared photo albums, invite relatives by link, and get a weekly digest of new photos."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create an album and upload photos (Priority: P1)

A user creates an album, gives it a name and uploads photos from their phone or desktop.

**Why this priority**: Without albums and uploads there is no product.

**Independent Test**: Create an album, upload 10 photos, see them in a grid sorted by date taken.

**Acceptance Scenarios**:

1. **Given** a signed-in user, **When** they create an album named "Summer 2026", **Then** it appears in their album list.
2. **Given** an album, **When** the user uploads 10 JPEG photos, **Then** all 10 appear sorted by EXIF date.

---

### User Story 2 - Invite relatives by link (Priority: P1)

The album owner shares an invite link. Anyone with the link can view and add photos.

**Why this priority**: Sharing is the core value proposition.

**Independent Test**: Open the invite link in a private window, join, upload a photo.

---

### User Story 3 - Weekly digest email (Priority: P2)

Members receive a weekly email with thumbnails of new photos in albums they belong to.

**Why this priority**: Drives re-engagement but the product works without it.

---

### Edge Cases

- What happens when an invite link is leaked publicly? [NEEDS CLARIFICATION: should links expire or be revocable?]
- How are duplicate uploads of the same photo handled?
- What happens to photos when a member leaves the album? [NEEDS CLARIFICATION: do their photos stay or get removed?]

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow signed-in users to create albums with a name of up to 80 characters.
- **FR-002**: System MUST accept JPEG, PNG and HEIC uploads up to 25 MB each.
- **FR-003**: System MUST generate a unique invite link per album.
- **FR-004**: Anyone with an invite link MUST be able to view and upload photos to that album.
- **FR-005**: System MUST send a weekly digest email every Monday at 08:00 in the member's timezone.
- **FR-006**: System MUST strip GPS location from EXIF metadata before photos are visible to other members.
- **FR-007**: System MUST retain original files for [NEEDS CLARIFICATION: retention period not specified].

### Key Entities

- **Album**: name, owner, invite token, created at.
- **Photo**: file, album, uploader, taken at, uploaded at.
- **Membership**: user, album, role (owner, member), joined at.

## Success Criteria *(mandatory)*

- **SC-001**: 80% of new albums receive at least one invited member within 7 days.
- **SC-002**: Upload of 10 photos completes in under 30 seconds on a 20 Mbps connection.
