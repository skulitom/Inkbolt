# Shape-combination performance

The W3c.3 candidate selects possible contacts through conservative rational
bounding boxes. It keeps the exact intersection, winding and output topology
checks, while avoiding work on distant geometry. See [the geometry contract](BOOLEANS.md).
[Fresh Windows/Linux acceptance](DEVELOPMENT_STATUS.md#spatial-evaluation-acceptance)
passes all 277 stages per platform on the same audited source. W3c.3 is complete
within this contract; whole-goal and advanced-checkpoint completion remain open.

## Matched measurements

Five repetitions per build and workload alternate the preceding `415771d`
implementation and the spatial candidate. Both use the same original request,
development build profile and machine, with both binaries on the same filesystem
within each platform. Platform runs are sequential. Time includes starting the
CLI and receiving its complete JSON response. These are scripted engine timings,
not model trials or a claim about total agent interaction cost.

Every result field other than `work_units` must equal the preceding build's
result. The advance criterion requires at least a twofold median improvement
on each of the three fixed workloads; all thirty responses per platform pass
the equality check. Full responses, individual timings, binary hashes and the
protocol are retained under `boolean-spatial-01`.

| Original workload | Windows before / after | Linux before / after | Windows / Linux improvement |
| --- | ---: | ---: | ---: |
| 480 separated line edges | 16.338 / 0.298 s | 17.227 / 0.305 s | 54.9x / 56.5x |
| Four separated ellipses, tolerance mode | 8.442 / 0.610 s | 8.638 / 0.729 s | 13.8x / 11.8x |
| Sixteen separated cubic regions, exact mode | 8.744 / 0.606 s | 10.098 / 0.651 s | 14.4x / 15.5x |

These are medians on the measured machine. Dense overlap retains quadratic
worst-case behavior and can fail a resource limit. The ratios do not establish
a universal speedup, production-build performance or a portable latency promise.
The initial Linux comparison used different filesystems and was interrupted;
it is retained separately and excluded from this table. A slow cross-filesystem
copy and its premature measurement launch are also retained as setup failures.

## Admission and independent checks

The aggregate source/evaluated edge ceiling rises from 512 to **1,024**. A single
capacity run per platform checks the complete geometry of 256 separate regions
at that ceiling: 0.591 seconds on Windows and 0.652 seconds on Linux, using
184,275 charged work units. Sixteen original ellipses require 768 flattened edges
and pass independent analytic area/interior checks; their capacity measurements
take 3.046 and 2.881 seconds. These capacity timings are separate from the five
matched repetitions above.

The **4,096-atom** and **2,000,000-work-unit** ceilings remain unchanged. Dense
crossing strips exceed the atom limit even with only 384 source edges; repeated
coincident contours at the 1,024-edge ceiling exhaust the work budget. Both
refuse explicitly without partial geometry or source changes. The measured
Windows work refusal takes 10.56 seconds. These cases do not justify a higher
atom or work ceiling. The separate quadratic-projection allowance stays at 512;
curve depth, coefficient limits and the automatic curve-attempt budget also stay
unchanged.

Original tests compare every admitted line-region vertex, exact areas, source
preservation and operand ordering. Ellipse checks use analytic interiors outside
the declared conversion/error band. Cubic checks use an independent parabola
integral: over width `h`, its chord loses `h^3/36` area and has at most `h^2/24`
vertical error. Closed-box contacts, sub-float rational gaps, both winding-ray
directions, dense refusals and strict source admission are covered separately.

The routine Windows geometry/arithmetic selection passed in 69 seconds; Linux's
focused contact/topology/capacity selection passed in 126 seconds. Earlier lint
and test-oracle failures are retained. The initial arbitrary cubic-area threshold
was replaced by the exact integral and per-interval deviation check; production
geometry was unchanged by that correction.

## Full acceptance and retained failures

Windows and Linux each pass all 277 stages fresh, including the existing geometry,
precision, history and output checks. The audit binds the complete source archive,
both measured executables, all 554 stage logs and 35 identical cross-platform
measurement responses. The linked acceptance records counts and content hashes.

The first four-worker Windows full attempt hit an existing 20-second tiled-PNG
export deadline. Its logs remain retained. The unchanged nine-test rendering
module then passed in isolation, followed by a complete Windows run with two
workers. Linux full acceptance also uses two workers; platform runs are sequential.
No test deadline or acceptance oracle was relaxed. The successful Windows run
completed on 26 October 2026; Linux acceptance completed on 20 November after
the exact source and measured binaries were revalidated.
