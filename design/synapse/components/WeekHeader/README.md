The divider that groups Sources (and, above a QuizCard, the week it recalls) by course week. Consumer provides the week number, the week's title and a source count.

Structure: a `tag` chip (`WK 03`, `surface-200` fill, `ink-soft` text — neutral, not `accent-neuro`, because grouping isn't an interactive choice) beside an `h2` title and a `caption` meta line, then a `border-subtle` rule at `space-3` below. Never a `border-strong` rule here — that weight is reserved for boundaries that carry state, not a page divider.

Repeat this exact structure at the top of every week's group; don't compress it to save space even when a week has a single source.
