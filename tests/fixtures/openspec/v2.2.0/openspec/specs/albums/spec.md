# albums Specification

## Purpose
Families create shared albums, upload photos and invite relatives.

## Requirements

### Requirement: Create album
Signed-in users SHALL be able to create albums with a name of up to 80 characters.

#### Scenario: Create
- **WHEN** a user creates an album named "Summer"
- **THEN** it SHALL appear in their album list

### Requirement: Album invite link
Each album SHALL have an invite link that lets relatives join.
