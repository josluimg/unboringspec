# Live from the spec: Shared Photo Albums, kick-off to final whistle

**Jordan:** Good evening and welcome to a packed stadium! Tonight's fixture: Shared Photo Albums. Families create albums, invite relatives by link, and get a weekly digest of new photos. `spec.md:6`

**Sam:** Big match, Jordan. Three user stories on the pitch, nine requirements on the bench, and a couple of question marks in the line-up.

**Jordan:** Kick-off! User Story One takes possession: create an album, give it a name, upload photos from phone or desktop. Priority one, and rightly so. `spec.md:10`

**Sam:** No albums, no uploads, no product. The spec says it, I'll say it louder. `spec.md:14`

**Jordan:** And look at this build-up play! Photos go straight from the browser to object storage with presigned URLs. Twenty-five megabyte files never touch the API servers! `research.md:5` `research.md:6`

**Sam:** Lovely footwork. But they passed on resumable uploads. A big HEIC file on a shaky phone connection drops halfway, and it's back to the centre circle. `research.md:7`

**Jordan:** The target on the scoreboard: ten photos in under thirty seconds on twenty megabits. `spec.md:70`

**Sam:** A target the whole architecture is built around, and it's only tested in the very last phase. That's checking the goalposts after the final whistle. `tasks.md:37`

**Jordan:** Meanwhile, the worker is everywhere! Thumbnails, HEIC to JPEG, and it strips GPS location before anyone else sees the photo. `tasks.md:20` `spec.md:58`

**Sam:** Good defending on privacy. But the original file keeps its location, and how long originals are kept is still undecided. `research.md:17` `spec.md:59`

**Jordan:** Here comes User Story Two, also priority one: invite relatives by link. Anyone with the link can view and add photos. `spec.md:25` `spec.md:27`

**Sam:** And there it is, the most dangerous play of the night. One permanent invite token per album, full member rights, for anyone holding the link. `research.md:11` `spec.md:56`

**Jordan:** The reasoning: lowest friction for relatives who aren't technical. Grandma taps the link and she's in. `research.md:12`

**Sam:** So does anyone grandma forwards it to. What happens when the link leaks? The spec asks the question itself and leaves it open: should links expire or be revocable? `spec.md:45`

**Jordan:** That one goes to the referee. A human has to make the call.

**Sam:** And while we wait: the alternatives were on the bench all along. Per-person email invites, expiring links, view-only links with upload approval. None of them got a minute. `research.md:13`

**Jordan:** Second open question in this half: when a member leaves the album, do their photos stay or go? `spec.md:47`

**Sam:** Also unanswered. And can the owner remove photos someone else uploaded? With open upload links, they'll need to. No requirement says so. `spec.md:65`

**Jordan:** Half time! Into the second half with User Story Three, priority two: the weekly digest email. `spec.md:35`

**Sam:** The super-sub. Brings people back, but the product plays fine without it. `spec.md:39`

**Jordan:** Every Monday at eight in the morning, in each member's own timezone. An hourly job picks whoever just hit Monday, eight o'clock. `spec.md:57` `research.md:23`

**Sam:** Clever. Except for members in half-hour timezones, like India. An hourly job never lands on their eight o'clock. They never get the email. `research.md:23`

**Jordan:** Ooh, offside by thirty minutes!

**Sam:** And one more: the digest is mandatory. No way to unsubscribe, and recurring email usually needs one. `spec.md:57`

**Jordan:** Into stoppage time. The storage budget per family? Still a question mark in the plan. `plan.md:19`

**Sam:** Originals plus converted copies, twenty-five megabytes each, no retention period, no budget. That bill keeps running after the match.

**Jordan:** Full time! Let's go to the analysis desk. Reviewer, here's what's on you.

**Jordan:** One: invite links. Do they expire, can the owner revoke them, given they let people upload?

**Jordan:** Two: what happens to a member's photos when they leave.

**Jordan:** Three: how long originals are kept, and the storage budget per family.

**Sam:** And credit where it's due: direct uploads and GPS stripping are a strong game plan. Fix the link, and this team goes up a division.

**Jordan:** That's all from the stadium. Goodnight!
