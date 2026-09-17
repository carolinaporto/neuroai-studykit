The site's single menu — five fixed sections, each either open, locked, or public. Consumer provides the active route and the viewer's signed-in state; the nav itself owns nothing else.

Sections, in order and never reordered: **Overview** (open to everyone), **Sources**, **Quizzes**, **Notes & Insights** (all three locked until signed in), **Homework** (public, always open). A signed-out visitor sees all five, including the locked three — never hide a section, since the goal is for the site to read as a complete portfolio from the outside.

States:
- `.is-active` — `accent-neuro-soft` fill, `accent-neuro` text and icon. At most one item at a time.
- default (open, not active) — `ink` text, `ink-soft` icon, `surface-200` on hover.
- `.is-locked` — `ink-soft` text and icon throughout, a 14px lock glyph at the trailing edge, `disabled` so it isn't keyboard-focusable until the visitor signs in.
- the Homework item never carries `.is-active`'s indigo or `.is-locked`'s muted state on its own account — it takes a `Public` tag (`tag` style, `accent-warm` on `accent-warm-soft`) instead, using the `AccessBadge` colors directly rather than the full badge component (there's no room for it at this width).

Do / don't: do keep the brand mark and "Foundations of Neuro AI" caption fixed at the top of every page. Don't add a badge count or notification dot to a locked item — a lock already says everything a visitor needs to know before signing in. Don't recolor `.is-locked` with `danger`; a locked section isn't an error state.
