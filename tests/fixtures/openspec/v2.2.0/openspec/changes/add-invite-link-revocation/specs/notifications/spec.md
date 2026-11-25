# Spec Delta

## Purpose
Tell album owners about events on their invite links so a revoked or expiring link never surprises them.

## ADDED Requirements

### Requirement: Warn before a link expires
The system SHALL email the album owner 3 days before the invite link expires.

#### Scenario: Link about to expire
- **WHEN** an invite link expires in 3 days
- **THEN** the owner SHALL receive an email with a button to extend it
