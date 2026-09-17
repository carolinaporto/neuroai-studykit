One row inside a week's source list — a slide deck, a reading or a video from class. Consumer provides the file type (for the icon), title, a one-line meta string (pages or duration) and the source file or link.

Every SourceItem carries the lock glyph in `ink-soft` at the trailing edge: class materials are never public, so there is no "open" variant without it. Stack rows inside one `surface-100` card with `border-subtle` rules between them (not gaps + separate cards) so a week's sources read as one list; `surface-200` on row hover. The icon sits in a 36px `radius-sm` tile on `surface-200`; swap the inner glyph by type (document, slides, play) but keep the tile treatment identical across types.

Title is `body` set to weight 600 (a one-off bolding of the token, not a new style — don't introduce a dedicated "title" type token for this). Meta is `caption`. Don't put the lock inside the icon tile; it stays a separate mark at the row's far edge so it's scannable down the whole list.
