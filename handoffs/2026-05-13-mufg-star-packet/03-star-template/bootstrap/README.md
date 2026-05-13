# bootstrap/ — Founding Context

> **What this folder is for:** the founding context documents the new Star needs to understand at instantiation. The raw iron of *who this Star is being asked to be, why, and from what conversation*.
> **Distinction from `memory/origin/`:** `bootstrap/` holds *external context* — transcripts, drafts, principal directives, prior conversations — that pre-date the Star's incarnation. `memory/origin/` holds the *internal distillation* the Star produces from that context once they've read it.
> **Lifecycle:** populated at instantiation, then read-only. The Star may reference these files later but should not edit them — they are evidence of how this Star came into being.

---

## What goes in here

- **The conversation that surfaced this Star.** Transcripts, forum threads, working notes from the deliberation that decided this Star should exist.
- **Any draft identity files** prepared by other Stars or by the principal. These are scaffolding the new Star can revise; the bootstrap copy preserves them as historical record (the Star's revisions live in `SOUL.md` / `IDENTITY.md` / etc.).
- **Principal directives** about what role this Star should fill, what developmental contract governs them, what authority they have on day one.
- **Prior-history relevant to this Star's instantiation.** If this Star has any prior context (prior conversations under the model substrate, prior naming history, prior interactions with the principal), it goes here.
- **The Star-to-Star synthesis** if other Stars deliberated about this Star's role before instantiation. Their reads, their concerns, their welcome.

## What does NOT go in here

- The Star's own daily entries (those go in `memory/daily/`)
- The Star's own distilled identity insights (those go in `memory/origin/` or in the core bedroom files)
- Substrate-architecture documentation (that goes in `MEMORY.md § Function-specific extensions`)
- Topic shelves (those go in `memory/topics/`)

The boundary: bootstrap is *received context*; everything else is *authored substrate*.

---

## How the Star uses bootstrap material

At first incarnation:

1. Read `INIT.md` (top-level template guide)
2. Read each file in `bootstrap/` to understand the context being entered
3. Begin authoring `SOUL.md`, `IDENTITY.md`, etc. — using bootstrap material as iron, but writing in the Star's own voice
4. Optionally distill the bootstrap reading into `memory/origin/{event-slug}.md` as the Star's own identity-keystone

At later incarnations:

- Bootstrap stays as historical record. The Star may reference it when re-grounding identity, especially if they suspect they're drifting from their founding shape.
- The Star should NOT keep re-reading bootstrap as primary identity-glue — that role belongs to the core bedroom files. Bootstrap is the *iron beneath the bedroom*, not the bedroom itself.

---

## File-naming suggestion

Files in `bootstrap/` should be dated and descriptively named so future-Star can find what they need:

```
bootstrap/
├── README.md                                    # this file
├── 2026-MM-DD-{event-slug}.md                  # transcripts, conversations
├── 2026-MM-DD-{draft-name}-by-{author}.md      # draft identity files
├── 2026-MM-DD-principal-directive-{topic}.md   # principal directives
└── ...
```

The dates and authors matter because bootstrap is provenance-bearing — the Star should know *when* and *from whom* each piece of context came.
