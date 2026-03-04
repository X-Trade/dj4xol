# Coding Standards

## Language and Style

- British English spellings in all documentation, comments, and identifiers
  (e.g. `colour`, `initialise`, `serialiser`)
- Formal but concise prose in documentation and help text
- Readable, self-documenting code preferred over excessive comments

## Line Length

- Maximum 80 characters per line
- Up to 90 characters permitted when it allows a function call or string
  to close on a single line without continuation

## Python Compatibility

- Code must remain compatible with Python 2.7 and Python 3.x
- Use `from __future__ import print_function` where necessary
- Avoid version-specific exceptions (e.g. use `ImportError` not
  `ModuleNotFoundError`)

## Dependencies

- Prefer the standard library; external dependencies require justification
- Optional features may use external libraries with graceful fallback

## Code Philosophy

- No regular expressions unless demonstrably necessary; prefer readable
  iterative or string-method approaches
- Avoid over-engineering; solve the problem at hand, not hypothetical
  future requirements
- Functions should do one thing well
