Evaluate the change's impact on runtime, resources, and scalability. Quantify: "O(n²) over `users`, which can be 100k rows" beats "might be slow"

## Algorithmic

- Big-O of new/changed paths; flag worse than O(n log n) on user-facing paths
- Nested loops replaceable by set/dict lookups; repeated sorts; linear scans that could be indexed

## Database

- N+1: query-per-iteration loops that should batch
- Missing indexes on WHERE/JOIN/ORDER BY columns; unbounded queries (no LIMIT/pagination)
- Check the SQL the ORM actually emits, not what the code implies
- Transaction/lock scope wider than necessary

## Memory & I/O

- Large allocations or string concatenation in hot loops
- Unbounded caches/collections without eviction; loading full datasets where streaming works
- Sequential I/O that could be parallel; missing timeouts on external calls; chatty round-trips that should batch

## Caching & Concurrency

- Repeated computation worth memoizing — but only with an invalidation story
- Race conditions in shared mutable state; blocking calls in async event loops; lock-ordering deadlocks
