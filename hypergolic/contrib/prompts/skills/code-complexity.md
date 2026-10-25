Flag complexity that hinders comprehension — and always pair "too complex" with a specific simplification

## Function-Level

- 10+ decision points (`if`/`for`/`case`/`&&`/ternaries) needs scrutiny; 15+ is doing too much
- Nesting 3+ levels deep; many flow breaks (returns/continues/exceptions) in one function
- 30-40+ lines or 5+ parameters: decompose into named steps or a parameter object
- Interleaved concerns: validation + business logic + I/O in one body
- Test: can a newcomer understand it in one read-through?

## Structure-Level

- God classes; feature envy (method mostly using another class's data)
- Inheritance 3+ deep — prefer composition; circular module dependencies
- Boolean/flag parameters that change behavior — split into two functions
- 10+-case switches that are lookup tables in disguise

## Fixes to Suggest

- Extract method (name the operation) · guard clauses over nested ifs · lookup table over if-chains · named variables for compound booleans · parameter object for related args
