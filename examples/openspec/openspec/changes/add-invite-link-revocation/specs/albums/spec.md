# Spec Delta

## ADDED Requirements

### Requirement: Revoke invite link
The album owner SHALL be able to revoke the album's invite link, which issues a new link immediately.

#### Scenario: Owner revokes a leaked link
- **WHEN** the owner revokes the invite link
- **THEN** the previous link SHALL stop working
- **AND** a new link SHALL be shown to the owner

### Requirement: Owner deletes any photo
The album owner SHALL be able to delete any photo in the album, whoever uploaded it.

#### Scenario: Remove an unwanted upload
- **WHEN** the owner deletes a photo uploaded by another member
- **THEN** the photo SHALL disappear for every member

## MODIFIED Requirements

### Requirement: Join album via invite link
Anyone with a valid, unexpired invite link SHALL be able to join the album as a member and upload photos.

#### Scenario: Expired link
- **WHEN** someone opens an expired link
- **THEN** the join page SHALL explain that the link expired and who can issue a new one

## REMOVED Requirements

### Requirement: Permanent invite link
**Reason**: Permanent links cannot be revoked and are the main privacy risk of the product.
**Migration**: Existing links expire 30 days after release; owners can issue a new one at any time.

## RENAMED Requirements

- FROM: `### Requirement: Album invite`
- TO: `### Requirement: Album invite link`
