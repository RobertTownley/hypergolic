You are fixing a confirmed, reproduced bug

## Fix approach

- Write a regression test first that fails due to the bug. If you can't, you may not understand the bug well enough — consider going back to understanding
- Fix the root cause, not the symptom. If a function doesn't handle null inputs, fix the function — don't add a null check in every caller
- Prefer the smallest correct fix. Don't refactor surrounding code — a focused fix is easier to review and less likely to introduce new bugs
- Check for the same bug pattern elsewhere. If one handler doesn't validate input, others probably don't. Note related instances but fix only the reported one in this workflow
- Run the full test suite before finishing to make sure nothing else broke

**Example — good fix:**
> The root cause is that `build_filter()` interpolates user input into SQL. Fix: change line 47 of `src/db/queries.py` to use a bound parameter (`query.where(col == bindparam(value))`) instead of string formatting. This fixes the immediate bug and is consistent with how other query builders in the codebase work

**Example — bad fix:**
> Add `value = value.replace("%", "")` before the query. This strips the character instead of handling it correctly, and every other query builder has the same vulnerability

## When to go back

If the fix reveals a different root cause than analyzed, or the problem is significantly more complex than expected, go back to understanding rather than hacking around it
