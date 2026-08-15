# AGENTS.md

Coding standards for this repo. These apply to all code (backend Python, frontend TypeScript, scripts) written or edited by an AI agent, in addition to any language-specific conventions already established in the codebase.

## Function length

- No function/method should be longer than 100 lines.
- If a function grows past that, split it into smaller, well-named helper functions instead of shrinking it by deleting docstrings/structure. Each helper should do one clear thing.

```python
# BAD: one 150-line function doing parsing + validation + persistence

# GOOD
def import_course(raw: dict) -> Course:
    """Parse, validate, and persist one raw course record."""
    fields = _parse_course_fields(raw)
    _validate_course_fields(fields)
    return _persist_course(fields)
```

## Docstrings

- Every function/method must have a docstring explaining what it does: its purpose and behavior, not a restatement of its code.
- Applies to helper functions too, not just public/exported ones.
- Per [PEP 257](https://peps.python.org/pep-0257/), phrase a one-line docstring as a command ("Return ...", "Compute ...", "Raise ..."), not as a description ("Returns ...", "Computes ...", "Raises ...").

```python
def _meets_minimum_grade(earned: str | None, minimum: str | None) -> bool:
    """Return whether an earned letter grade satisfies a minimum-grade
    requirement, treating non-letter grades (P/CR/transfer) as always satisfying."""
    ...
```

## No blank lines inside a function body

- Don't use empty lines to visually separate sections inside a function.
- If a function has distinct sections that "want" a blank line between them, that's a signal to extract those sections into helper functions instead (see "Function length" above).
- [PEP 8](https://peps.python.org/pep-0008/) doesn't require blank lines inside a function; it only says to use them "sparingly" to separate logical sections. This repo goes stricter than PEP 8 on purpose: zero blank lines, no exceptions, because it forces the "sparingly" judgment call to become a concrete helper-function extraction instead.

```python
# BAD
def process(order):
    validate(order)

    total = compute_total(order)

    return total

# GOOD
def process(order):
    """Validate an order and return its computed total."""
    validate(order)
    total = compute_total(order)
    return total
```

## Minimal comments

- Don't add comments that just narrate what the next line does (e.g. `# increment the counter`, `# loop over items`, `# return the result`).
- Only comment when explaining something the code itself can't convey: non-obvious intent, a trade-off, a constraint, or why a workaround exists. Prefer a clear docstring and clear names over comments.
- This matches [PEP 8](https://peps.python.org/pep-0008/): comments should add useful information beyond what the code already says, not merely restate it.
