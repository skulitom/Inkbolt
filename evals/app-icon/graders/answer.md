---
type: llm
weight: 2
focus: trace
---

PASS if the trace shows a 512x512 document drawn with an orange rounded square and a white bolt, a preview checked before delivery, and two successful document.publish calls: a PNG named app-icon.png and an SVG in the icons folder; and the final reply gives both paths.

FAIL if either file is missing from the trace, the PNG isn't 512x512 (canvas 512x512 at scale 1, or a smaller canvas published at a scale that gives 512x512), the reply claims a file the trace doesn't show being created, or the reply only explains how to make the icon.
