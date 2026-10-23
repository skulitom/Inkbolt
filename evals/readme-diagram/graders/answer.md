---
type: llm
weight: 2
focus: trace
---

PASS if the trace shows the project font imported with its licence, three labelled boxes ("Browser", "API server", "Postgres") left to right with two arrows, and two successful document.publish calls writing architecture.svg and architecture.png in docs; and the final reply gives both paths.

FAIL if a label is missing or misspelt, the arrows are missing, either file is missing from the trace, the reply claims a file the trace doesn't show being created, or the reply only explains how to draw it.
