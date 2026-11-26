# Roasting the change that finally locks the front door

## Intro

**Maya:** Welcome back to the spec roast. Today's change has a noble mission: stop family photo albums from being open to the whole internet.

**Leo:** Noble. Overdue. Today, an album link never expires and can't be revoked. Forward it to the wrong group chat and your cousin's coworkers are uploading memes into grandma's birthday album. `proposal.md:5`

## What it is

**Maya:** Which is exactly what this fixes. Owners can revoke the link, and a new one is issued straight away. `proposal.md:9`

**Leo:** I'll give it that. One click and the leak is closed. Applause, genuinely.

## Key decisions

**Maya:** And the clever bit: revoking doesn't keep a list of banned links. It just swaps the album's token for a new random one. `design.md:20`

**Leo:** Clever, and also a nuclear option. Rotate the token and every link dies, including the one aunt Carmen printed and stuck on her fridge. `design.md:34`

**Maya:** The design calls that acceptable, because rotating is a deliberate owner action.

**Leo:** Deliberate, sure. Until the owner realises the whole family is now locked out and the group chat lights up.

**Maya:** Fair. Next: links also expire. Each token gets an expiry date, and the lifetime comes from configuration. `design.md:24`

**Leo:** Lovely. And what is that lifetime?

**Maya:** That's… an open question. Seven, thirty or ninety days. `design.md:38`

**Leo:** Undecided. And yet the migration already decided: existing links expire thirty days after release. The task list picked a number the design is still debating. `tasks.md:6`

**Maya:** Okay, that one lands. Pick the default first, or derive the migration from it.

**Leo:** Now my favourite line. Owners get an email three days before a link expires, with a button to extend it. `specs/notifications/spec.md:13`

**Maya:** That's thoughtful.

**Leo:** It is a button to nowhere. No requirement says links can be extended, and no task builds it. We are emailing people a promise. `tasks.md:21`

**Maya:** Point taken. Either add the requirement and the task, or drop the button.

**Leo:** Then there's the breaking change. Permanent links are removed outright. `proposal.md:12`

**Maya:** With a migration: old links expire thirty days after release, and owners can issue new ones any time. `specs/albums/spec.md:33`

**Leo:** Right. Thirty days for every family to notice, in an app whose main channel to them is… an email we haven't built the button for.

**Maya:** Moderation, then. Owners can now delete any photo, whoever uploaded it. `specs/albums/spec.md:14`

**Leo:** Good. Also permanent. No undo, no record of who deleted what. One tired thumb at midnight and the wedding photos are gone for everyone.

**Maya:** And one more open question: should people who joined through a revoked link stay in the album? `design.md:39`

**Leo:** Because if they stay, revoking the link closes the door after the burglar is already on the sofa.

**Maya:** Last roast, I promise. Rotation, expiry and a data migration all touch who can see what…

**Leo:** And the task list has zero tests. Not one. Access control on vibes. `tasks.md:1`

## What you must decide

**Maya:** Alright, serious minute. If you're reviewing this change, here's what's on you.

**Maya:** One: pick the default link lifetime, and make the migration use it.

**Maya:** Two: decide whether members who came in through a revoked link keep their access.

**Maya:** Three: build the extend button, or stop promising it. And add tests while you're at it.

## Wrap-up

**Leo:** And say nice things too. Revoking a leaked link in one click is a real improvement. It just needs the rest of the house finished.

**Maya:** Thanks for listening. Go lock your front doors.
