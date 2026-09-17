The one badge that answers "can a signed-out visitor see this?" — used on `InsightNote`, `HomeworkCard`, and, in its bare colors (no room for the full pill), the `Homework` row in `SiteNav`. Consumer provides only the boolean.

`Public` — `accent-warm` on `accent-warm-soft`, an open-shackle lock glyph. `Private` — `ink-soft` on `surface-200`, a closed lock glyph. Both set in `tag` (mono, uppercase). Never invent a third state ("Unlisted," "Draft") without a corresponding token — this system ships exactly two, matching the site's actual rule: homework defaults public, everything else defaults private.

Don't recolor this badge per section (a "Sources" flavored private badge, a "Quizzes" flavored one) — one gray private badge and one warm public badge, everywhere, is what makes the access rule legible at a glance across the whole site.
