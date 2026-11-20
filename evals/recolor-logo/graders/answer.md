---
type: llm
weight: 2
focus: trace
---

PASS if the trace shows brand/logo.svg imported, the two blue (#1E66F5) items changed to #0B6E4F and nothing else recoloured, and two successful document.publish calls: logo-green.svg and logo-green.png at 1024 pixels wide (the 256x96 logo at scale 4); and the final reply gives both paths and says the original is unchanged.

FAIL if the original is overwritten or targeted as an output, the grey wordmark is recoloured, the PNG isn't 1024 pixels wide, the reply claims a file the trace doesn't show being created, or the reply only explains how to do it.
