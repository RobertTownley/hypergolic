The codebase's own patterns are the standard — read the surrounding code before flagging anything, and cite the existing convention (file:line) with every finding

## Consistency

- Naming, error handling, import order, file placement, API shapes, test style: does new code match where similar code already lives?
- Is the change internally consistent (not one style in file A, another in file B)?
- If it introduces a new pattern, is the old one deprecated — or is this fragmentation?
- If it refactors, is the migration complete? Half-migrated patterns are worse than none

## DRY — But Not Prematurely

Flag duplication when an existing utility already does the job, or the same logic appears 3+ times with a natural abstraction

Don't flag when: similar-looking code serves diverging concerns, the abstraction would be more complex than the duplication, or there are only 2 occurrences. The wrong abstraction is worse than duplication

## Reuse Red Flags

- Reimplements an existing helper (cite it)
- Single-use utilities that should be inlined; base classes with one subclass
- "Helper" junk drawers; shared modules coupling independent features
- Inheritance where composition is simpler
