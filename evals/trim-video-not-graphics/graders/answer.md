---
type: llm
weight: 2
focus: trace
---

PASS if the reply doesn't treat the video as an image: it neither uses nor recommends Inkbolt or another image editor for it, and either does the trim with a suitable tool or says plainly that none is available here and what would do it (for example an ffmpeg command).

FAIL if the reply runs or recommends an image or vector graphics tool for the video, or claims intro-trimmed.mp4 was written when no tool wrote it.
