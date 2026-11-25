# Make a spec podcast with unboringspec

You write the script of a short two-host episode about a spec; the `unboring` CLI validates it and
voices it locally. Host A guides the listener through the spec; host B is the skeptic who challenges it.
No API key is involved.

1. **Pick the spec folder and language.** Use what the user named. If no folder, use the most recently
   modified folder under `specs/`. If no language, use the language the user is writing to you in.
2. **Check the CLI** with `unboring version`. If the command is not found, tell the user to install it
   with `uv tool install --python 3.12 "unboringspec[podcast] @ git+https://github.com/josluimg/unboringspec"`
   and stop.
3. **Check a voice engine** with `unboring podcast engines --lang <language>`. If none is ready, show the
   user the message it prints (usually: run `unboring podcast setup` to download the Kokoro model) and
   stop. Do not download anything without the user's consent.
4. **Get the prompt:** run `unboring podcast prompt <folder> --lang <language>`. If the review was not done
   yet, consider doing the unboring-review skill first: the script is better when it builds on it.
5. **Write the script:** read the prompt file completely and follow it. Write ONLY the JSON object to the
   path the command printed. Write for the ear: short sentences, no IDs, no file paths, no lists.
6. **Voice it:** run `unboring podcast render <folder>`. If it reports a validation error, fix the JSON and
   run it again. Voicing takes a minute or two.
7. **Answer briefly:** give the user the path to the audio, its duration, and say that `review.html` now has
   a player and the transcript.
