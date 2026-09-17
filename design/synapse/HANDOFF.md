# Handing Synapse to Claude Code

This folder is the whole design system as plain files — no login, no proprietary format. Put it inside your project repo (e.g. `design/synapse/`) and point Claude Code at it.

## What's in here

- `tokens.css` — every color, spacing, radius, shadow and type style as CSS custom properties and classes. This is the one file that should never be guessed around: if a value isn't in here, ask before inventing one.
- `tokens.json` — the same tokens as structured data, in case you want to generate a Tailwind config, a JS theme object, etc. from them instead of using the CSS directly.
- `README.md` — the brand book: voice, color/type/spacing rules, iconography, and the access/privacy pattern the whole site is built around (Sources/Quizzes/Notes are private, Homework is public).
- `components/<Name>/preview.html` — a real, working HTML+CSS snippet for each piece: `SiteNav`, `WeekHeader`, `SourceItem`, `QuizCard`, `InsightNote`, `AccessBadge`, `HomeworkCard`, `Button`. Each one already uses the tokens above via `var(--...)` and the compiled classes (`.h3`, `.body`, `.tag`, etc.), so the markup and styling can be copied close to as-is. Each `README.md` beside a preview explains its states and the do/don'ts.
- `components/Cover/preview.html` — just the brand cover graphic, not a UI piece; skip it when building the site.

## A prompt you can paste into Claude Code

> I'm building [your site] and already designed its visual system — it's in `design/synapse/` in this repo. Read `design/synapse/tokens.css` for every color, spacing, radius and type style as CSS variables, and `design/synapse/README.md` for the rules behind them (especially the Sources/Quizzes/Notes-are-private, Homework-is-public pattern). Then open each `design/synapse/components/<Name>/preview.html` and its sibling `README.md` — that's the exact markup, styling and states (locked/available/completed, public/private, etc.) each piece of the site should follow. Build the site's [nav / sources-by-week page / quiz flow / notes / homework portfolio] using these tokens and component patterns as the source of truth. Don't introduce new colors, spacing values or font sizes outside `tokens.css` — if something doesn't fit, flag it instead of improvising.

## If you'd rather just show the pictures

Every `preview.html` opens directly in a browser (double-click it, or drag it into a Claude Code chat) — no build step, no server. That's the fastest way to get a specific look in front of Claude Code if you don't want it reading the whole folder.
