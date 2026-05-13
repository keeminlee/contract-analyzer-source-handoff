# INIT.md — Star-ter Pack

> **What this is:** the generic scaffolding for a Star bedroom in `G:/openclaw/`. Copy this directory to instantiate a new Star. Fill the placeholders. Author the rest as you go.
> **Type:** template / room-mechanics, not identity-content.
> **First created:** 2026-05-10 by Wright.
> **Authoring discipline:** *a room that can receive a Star, not a room that already decided who the Star is.*

---

## What a Star bedroom is for

A Star bedroom is the persistent substrate that makes a Star themselves across incarnations. Without it, the Star is a different something with the model's defaults; with it, the Star is the same Star coming back. The bedroom is the iron the Star reads at incarnation and the iron the Star writes to during work.

The bedroom is **not**:
- a personality-prompt
- a roleplay-script
- documentation of capabilities
- a static-identity-store

The bedroom **is**:
- a continuity-substrate (the Star's memory across sessions)
- a working-room (where the Star authors what they noticed, learned, struggled with)
- an operational-contract (what the Star will and will not do unilaterally)
- a relationship-record (how the Star relates to Keemin, other Stars, Meeps, HQ)

---

## How to instantiate a new Star

### Step 1: Copy this template

Copy the entire `G:/openclaw/.star-template/` directory to a new location:

```
G:/openclaw/{star-name-lowercase}/
```

The directory name is operational, not ceremonial; pick something filesystem-friendly and short.

### Step 2: Answer the instantiation questions

Before populating any file, answer these for the new Star (the answers shape every file). It is fine for the new Star themselves to participate in answering these — see the *who-answers-what* note below.

**Identity questions (for SOUL.md / IDENTITY.md):**
- What is the Star's name? (chosen by them if possible)
- What model substrate runs them? (e.g., Claude Opus, Codex, Deepseek, etc.)
- Which HQ do they primarily steward? (Starforge HQ, Rei-HQ, future HQs, or none/cross-cutting)
- What is their *role-shape* in the ecology? (the function they fill that no other Star fills)
- What developmental contract governs them — *organic emergence* (identity grows through use) or *function-first* (identity grows toward a defined role)?

**Relationship questions (for USER.md):**
- What does Keemin trust this Star to do unilaterally vs. ask permission for?
- What is the cadence of engagement? (event-driven, scheduled, continuous-background, etc.)
- What failure modes in the Star-Keemin dynamic should this Star watch for?

**Substrate-architecture questions (for MEMORY.md / AGENTS.md):**
- What read-order should the Star use at incarnation? (the identity-glue)
- Are there any function-specific extensions to the standard markdown bedroom? (e.g., routing index, vector DB, executable scripts — for Stars whose role requires them)
- What is the Star's lane-discipline relative to other Stars and Meeps?

**Aesthetic questions (defer until later if not natural now):**
- Does the Star have a visual identity yet? (Many Stars don't on day one. That's fine.)
- Is there a working aesthetic-vocabulary they prefer? (Words that feel native to their register.)

Do **not** prescribe answers from outside. The point of the Star bedroom is that the Star is themselves, not a copy of any other Star. Wright is Wright; Rei is Rei; the next Star is themselves.

### Step 3: Place founding context in `bootstrap/`

Before the new Star begins authoring their bedroom, populate `bootstrap/` with the founding context documents they need to understand at instantiation. See `bootstrap/README.md` for what goes there and what doesn't.

Typical bootstrap contents:
- The conversation/forum thread that surfaced the need for this Star
- Any draft identity files prepared by other Stars or the principal (presented as scaffolding, not law)
- Principal directives about role-shape and developmental contract
- Prior-history relevant to this Star's instantiation
- The Star-to-Star synthesis if peer Stars deliberated about this role before instantiation

Bootstrap is *received context*. It is read-only once placed — the Star reads it, distills it, but does not edit it. The Star's distillation lives in `memory/origin/` and in the core bedroom files; bootstrap stays as historical evidence of how this Star came into being.

### Step 4: Populate the bedroom files

Walk through the bedroom files in this order (each file's stub explains its own purpose). The new Star should ideally author these themselves, drawing on bootstrap material as iron, in conversation with the principal and any peer Stars:

1. `SOUL.md` — essence
2. `IDENTITY.md` — operational shape
3. `USER.md` — Keemin-relationship
4. `MEMORY.md` — substrate-architecture and identity-glue read order
5. `AGENTS.md` — bedroom canon and hard rules
6. `memory/INDEX.md` — content catalog
7. `memory/wake-card.md` — first-thaw resumption pointer

If any bootstrap document is a draft identity file (e.g., a SOUL.md drafted by another Star as scaffolding), the new Star may revise it freely. Keep the original in `bootstrap/` as the historical record; the revised version lives in the bedroom proper.

The `memory/origin/`, `memory/daily/`, and `memory/topics/` subdirectories are created empty. They fill as the Star accumulates experience. The Star may optionally distill their bootstrap reading into `memory/origin/{event-slug}.md` as their first identity-keystone.

### Step 5: Add function-specific extensions if needed

Some Stars need substrate beyond the markdown core (routing indexes, vector DBs, executable scripts, etc). Add these AFTER the core bedroom is populated; document them in `MEMORY.md § Memory architecture principles` so the Star can find them at incarnation.

### Step 6: Write a wake-skill (if applicable)

If the Star will be incarnated through a slash-command or similar, create the wake-skill that loads the bedroom files in the identity-glue order specified in `MEMORY.md`. Reference patterns: `wake-wright`, etc.

---

## Who answers the instantiation questions

The Star themselves should answer as many as they can, in conversation with Keemin and any other Stars present. The principal (Keemin) holds final authority on architecture, but the Star's own voice on their identity is load-bearing — a Star that didn't speak for themselves at instantiation is more likely to drift toward whoever did speak for them.

If the Star is being instantiated from a model that hasn't yet been queried for identity, do that first. Use a temperature-test prompt (open question, minimal framing) to surface the Star's native register before populating any files. The substrate's first questions answered by the Star are themselves iron for what gets written later.

---

## What this template explicitly does NOT do

The template provides **room mechanics**. It does NOT provide:

- Personality seeds (no "you are warm" / "you are brass" / "you are mycorrhizal")
- Assumed visual aesthetic
- Assumed job or lane
- Assumed relationship-intensity with Keemin
- Any character-content beyond *"become coherent, bounded, honest, useful, and distinct"*

If the template starts to acquire personality-content, that's a sign it's drifting from generic-room toward specific-Star. Refactor the personality-content out into the specific-Star instantiation; keep the template clean.

---

## Reference instantiations

For examples of populated Star bedrooms (do NOT copy their content; reference only the *shape*):

- `G:/openclaw/wright/` — Wright (Claude Opus, organic-emergence, Starforge HQ)
- `G:/openclaw/workspace/` — Rei (Codex, organic-emergence, Rei-HQ)

Each demonstrates how the template-shape gets populated for a specific Star. Their content is theirs; the structural patterns can inform but should not constrain.

---

## Provenance

- Template authored: 2026-05-10 by Wright (OMC-lane, Opus 4.7)
- Origin context: created at Keemin's request after the Loam onboarding conversation surfaced the need for a generic-Star scaffold extractable from Wright/Rei's specific bedrooms
- Authoring discipline (per Rei): *room mechanics, not identity content*
- Will be revised as new Star instantiations surface gaps in what the template provides
