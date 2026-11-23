# Recorded agent evaluation results

## Results by task

On the fourteen tasks repeated with Inkbolt 0.85.1, agents using Inkbolt
completed 70 of 70 workflows. Agents using the baseline completed 62 of
65 applicable attempts. Three print PDFs omitted a required color setting.
Lost-reply recovery has no baseline. Across all 20 tasks, including the
earlier builds, median token use was lower for the baseline on all 17
tasks where both approaches were evaluated.

Each row uses the latest standard five-trial comparison, or the latest
standard engine run for tasks without a baseline. Experiments that vary the
instructions have their own results below.
B07 also records the client starts that ended before a trial could be judged.
The evidence links give the prompts, independent checks, trial conditions and
judge corrections. Both arms used Codex CLI with `gpt-6.1-sol` and medium
reasoning on Windows. The baseline used a pinned SVG renderer and Python imaging
library. Fourteen tasks now share one 0.85.1 executable. The other six rows
use earlier builds. A separate [scripted comparison with Cutbolt](BENCHMARK_COMPARISON.md#saved-session-recovery-with-cutbolt)
measures catalog size, receipt recovery and retry traffic on Windows and Linux.

| Task | Inkbolt artifact | Inkbolt workflow | Baseline passes | Median tokens, Inkbolt / baseline | Evidence |
| --- | ---: | ---: | ---: | ---: | --- |
| B01 Labelled diagram | 5/5 | 5/5 | 5/5 | 110,522 / 42,491 | [0.85.1 diagram trials](#diagram-svg-and-recovery-trials-on-0851) |
| B02 Aligned icon sheet | 5/5 | 5/5 | 5/5 | 176,022 / 55,384 | [Aligned icon sheets on 0.85.1](#aligned-icon-sheets-on-0851) |
| B03 Edit a 5,000-object layout | 5/5 | 5/5 | 5/5 | 266,993 / 70,417 | [5,000-object layouts on 0.85.1](#large-layouts-and-shared-palettes-on-0851) |
| B04 Revise imported vector artwork | 5/5 | 5/5 | 5/5 | 185,397 / 59,300 | [0.85.1 SVG receipt recheck](#diagram-svg-and-recovery-trials-on-0851) |
| B05 Recolor a shared palette | 5/5 | 5/5 | 5/5 | 204,832 / 41,573 | [Shared palettes on 0.85.1](#large-layouts-and-shared-palettes-on-0851) |
| B06 Repair linked text overflow | 5/5 | 5/5 | 5/5 | 293,389 / 76,247 | [Linked text on 0.85.1](#linked-text-and-foreground-masks-on-0851) |
| B07 Multilingual typography | 5/5 | 5/5 | 5/5 | 298,013 / 214,257 | [Typography on 0.85.1](#multilingual-typography-on-0851) |
| B08 Mask a foreground region | 5/5 | 5/5 | 5/5 | 287,596 / 44,219 | [Foreground masks on 0.85.1](#linked-text-and-foreground-masks-on-0851) |
| B09 Retouch a local defect | 5/5 | 5/5 | 5/5 | 281,627 / 43,023 | [Local image repair on 0.85.1](#local-image-repair-on-0851) |
| B10 Edit a multi-megapixel photo | 5/5 | 5/5 | 5/5 | 460,584 / 75,451 | [16-bit photo edits on 0.85.1](#editing-a-16-bit-photo-on-0851) |
| B11 Revise a mixed composition | 5/5 | 5/5 | 5/5 | 362,423 / 58,323 | [Masked compositions on 0.85.1](#revising-a-masked-composition-on-0851) |
| B12 Generate layout variants | 5/5 | 5/5 | 5/5 | 566,966 / 61,799 | [30c4ebd](#b11b12-at-30c4ebd-mixed-composition-and-layout-variants) |
| B13 Deliver transparent artwork | 5/5 | 5/5 | 5/5 | 134,535 / 41,369 | [0.85.1 source build](#transparent-screen-artwork-on-0851) |
| B14 Deliver a print page | 5/5 | 5/5 | 2/5 | 712,198 / 94,435 | [Native print controls on 0.85.1](#native-print-controls-on-0851) |
| B15 Repair resource bindings | 5/5 | 5/5 | 5/5 | 274,948 / 56,972 | [7d31cf9](#b14b15-at-7d31cf9-print-delivery-and-resource-repair) |
| B16 Repair a text layout | 5/5 | 5/5 | 5/5 | 377,956 / 128,438 | [d18ac62](BENCHMARK_CLI_EXAMPLES.md) |
| B17 Recover a lost response | 5/5 | 5/5 | n/a | 263,170 / n/a | [0.85.1 recovery trials](#diagram-svg-and-recovery-trials-on-0851) |
| B18 Resolve conflicting edits | 5/5 | 5/5 | n/a | 249,608 / n/a | [cae530a](#b17b18-at-cae530a-receipt-and-concurrent-edit-recovery) |
| B19 Recover an interrupted export | 5/5 | 5/5 | n/a | 530,157 / n/a | [Command discovery during export recovery](#command-discovery-during-export-recovery) |
| B20 Revise a linked video graphic | 5/5 | 5/5 | 5/5 | 921,483 / 284,822 | [Timed sequence example](#timed-sequence-handoff-with-one-discovery-example) |

Artifact checks cover the requested delivery and source preservation. A complete
Inkbolt workflow also requires the specified editing history, receipts or
recovery behavior. Baseline artifact and workflow counts coincide in these
batches. B17–B19 exercise engine-specific recovery and have no baseline arm.

Token medians include all attempts with reported usage, including failures, and
count cached input once. Five trials
give wide uncertainty. For example, five successes give a 95% Wilson interval
of 56.6%–100%. Full model-call counts, engine-only model-trial memory and
preview timing across the entire suite remain open. [Comparison policy](BENCHMARK_COMPARISON.md)

In B01, both arms delivered five accepted editable diagrams once the prompt
specified how to supply the font and position the labels. The earlier baseline
scored 0/5 on source-format checks despite producing the requested pixels.
[Original diagrams and rendering check](#b01-source-rendering-check)

In B07, all ten completed attempts rendered the expected pixels and reported
the correct glyph and cluster order. In B14,
all ten previews passed. Three baseline PDFs omitted the explicit black point
compensation setting required for print delivery.

The [smaller-model transparent PNG trial](#transparent-screen-delivery-with-luna),
[five-pair smaller-model diagram evaluation](#b01-with-luna),
[three five-pair 50 MP photo evaluations](B10_LARGE.md#five-matched-windows-trials) and [earlier evaluations](#b02-at-c7d9f30-initial-five-matched-icon-sheet-trials)
retain their own attempts. In the focused text-repair follow-up, median Inkbolt
token use was 35.8% lower than in the preceding essentials batch and 2.94 times
the fresh baseline's median. [Text-repair evaluation](BENCHMARK_CLI_EXAMPLES.md)

## Revising a masked composition on 0.85.1

Five Inkbolt agents and five baseline agents changed only the shadow offset
in a 32 × 24 composition. An independent calculation using the original
image, fill alpha, group mask and opacity matched every delivered pixel.
The change affected 100 of the 768 pixels. All five Inkbolt agents also
recovered the original preview from the saved revision.
[Shared task and required editing controls](../tools/benchmark_prompts/B11.md)

| Median per attempt | Inkbolt | No engine |
| --- | ---: | ---: |
| Input plus output tokens | 362,423 | 58,323 |
| Shell commands | 10 | 3 |
| Shell output, UTF-8 bytes | 103,764 | 602 |
| Seconds to first verified preview | 70.7 | 38.8 |
| Solve time, seconds | 94.8 | 47.6 |

The Inkbolt trials ran first on Windows, followed by the baseline trials
with the same client settings. All five Inkbolt agents used the CLI.
Commands that included a schema lookup produced 446,406 of their 518,307
shell-output bytes. In each trial the largest reply came from such a command.
Several commands grouped lookups with other work.

In a separate follow-up on Windows and Linux, each of the five saved
Inkbolt documents accepted a second edit moving the source image three pixels
right and two down. The mask, shadow and other objects retained their
settings. All five new previews on each platform matched an independent
calculation, including the newly transparent pixels at the canvas edges.
[Earlier trials that exposed unwanted layer locks](#mixed-composition-with-a-movable-source-layer)

The combined replay covers 135 genuine attempts on fourteen tasks. Six
standard tasks still use earlier builds. B11 trial and replay audit SHA-256
`7cfbec5ad06f7438fe2baf05baef16d270e0c12a78f8556013187dea4feb060b`.
Combined audit SHA-256 `a790b614425ae149dd2d7b0046dabfd99c1d742168d6e1da0cc14bbd0b940172`.

## Editing a 16-bit photo on 0.85.1

Ten agents cloned the requested 12 × 14 patch in a 1920 × 1080 RGBA16
photo. An independent TIFF decoder and sample comparison confirmed all 168
repaired pixels, all 2,073,432 untouched pixels and every pixel of the
focused PNG preview in both arms. The five Inkbolt agents also retained
the original TIFF and all four editable revisions. Checking all 135 native
tiles at each revision found the same four tile replacements in every edit
and redo. One saved session also reproduced all four TIFFs on Linux.
[Move the photo and its history between machines](SESSION_BACKUPS.md#moving-a-16-bit-image-with-stored-tiles)

| Median per attempt | Inkbolt | No engine |
| --- | ---: | ---: |
| Input plus output tokens | 460,584 | 75,451 |
| Shell commands | 15 | 3 |
| Shell output, UTF-8 bytes | 1,127,642 | 302 |
| Seconds to first verified preview | 103.9 | 64.0 |
| Solve time, seconds | 151.2 | 71.3 |

The five Inkbolt trials ran first, followed by the five baseline trials,
on the same Windows host and with the same client settings. Each agent used
the CLI. All ten passed the 256 MiB memory check. The largest single-process
peak commit in each owned client tree ranged from 74.95 to 99.15 MiB for
Inkbolt and 66.64 to 93.54 MiB for the baseline. The measurement includes
the launcher, client and tools. Linux peak commit remains unmeasured.
[Separate 50 MP photo benchmark](B10_LARGE.md#five-matched-windows-trials)

Four Inkbolt transcripts recorded a shell reply over 1 MiB containing the
proposed edit's hex-encoded tiles. The task requires the full review on
disk. In a separate scripted check on the first agent's source document,
`review_output` reduced the Windows CLI reply from 1,073,816 to 1,041
bytes and the Linux reply from 1,073,684 to 954 bytes. Each saved file
contained the full review. Applying the returned proposal produced the same
edited tile manifest as the agent. [Save a review to a file](SESSION_PROPOSALS.md#save-the-review-to-a-file)

Replaying all 125 genuine attempts in the thirteen standard tasks
reproduced their verdicts and recorded usage. At that stage seven tasks still
used earlier executables. B10 trial and replay audit SHA-256
`41e7f83bf36ebe5bf94c6ebb7033336498f484d27f797ddd3d1fc43e3b0b7c7d`.
Independent sample check SHA-256 `3b9dd8b39101e2b17220b2287f8bc0cefa98544980735c4f19e00c397cfa46e4`.
Combined audit SHA-256 `a31c50f352b08dc59b2db6f1b5f19009f0dcb19da46301cd852d9218127d3ab6`.

## A focused lookup during local image repair

Ten fresh agents repaired the same four pixels with Inkbolt 0.85.1.
Five received the standard task. Five also received the 246-byte retouch
example from the discovery guide. Each agent chose its own tools. The
experiment alternated which condition went first in each pair, using
the same executable, client, model settings, fixture and judge. All ten
captures passed on replay. An independent check compared every pixel
in each saved editable layer, repaired preview and original revision.
[Example supplied to agents](https://github.com/skulitom/Inkbolt/blob/bc3d238293f91b742e43e9accb9055b9f4a58c4c/docs/AGENT_DISCOVERY.md#focused-schemas)

| Median per attempt | Standard task | With focused lookup |
| --- | ---: | ---: |
| Complete workflows | 5/5 | 5/5 |
| Input plus output tokens | 230,610 | 266,146 |
| Shell commands | 9 | 9 |
| Shell output, UTF-8 bytes | 53,381 | 52,286 |
| Shell output plus serialized MCP replies, bytes | 53,381 | 52,660 |
| Seconds to first verified preview | 45.6 | 33.2 |
| Solve time, seconds | 80.7 | 84.7 |

The earlier median preview came with 15.4% higher median token use. Token
use rose in four pairs. The preset decision required lower medians for
both tokens and shell output with all workflows passing. Keep the lookup
available in the guide and leave the default instructions as they are.
These ten attempts are a separate experiment from the standard benchmark.

One agent given the example made 21 direct MCP calls. It used the intended
retouch selector and also requested several complete command schemas. Its
shell returned 8,082 bytes and its MCP calls returned another 115,300 bytes
of serialized replies. All nine other agents used the CLI alone for Inkbolt.

Replaying that agent's eleven schema lookups with
`response_format:"structured"` preserved every structured result and
error flag. The tool results totaled 44,059 bytes, down from 89,522
with the default format. Windows and Linux returned the same results
and sizes. This scripted check counts compact UTF-8 tool-result JSON
before client serialization. It measures transport savings only.
[MCP response formats](AGENT_INSPECTION.md)

Trial and replay audit SHA-256 `efe78c1a9b4909059ddbbbc2af765c8a1fa9d38ad534223c8fa20b953c10c37e`.
Independent pixel and paired checks SHA-256 `2562d9d1cdf9a65187446cf52a7e6bea3c0aadb47ac04f7fc0462ab5ef73dae7`.

## Local image repair on 0.85.1

All ten agents cloned the original 2 × 2 patch onto the four defective
pixels. A separate check reconstructed the patch from the original and
compared it with every pixel in each editable layer and PNG preview.
All 252 pixels outside the patch stayed unchanged. Each
Inkbolt agent also reopened the damaged revision and delivered its
original pixels.

| Median per attempt | Inkbolt | No engine |
| --- | ---: | ---: |
| Input plus output tokens | 281,627 | 43,023 |
| Shell commands | 9 | 2 |
| Shell output, UTF-8 bytes | 69,583 | 2,430 |
| Seconds to first verified preview | 61.8 | 23.8 |
| Solve time, seconds | 99.5 | 27.5 |

Both arms used the same external client configuration as the linked-text
and mask trials. The five Inkbolt attempts ran first. Local verification
overlapped some attempts. Replaying the ten captures reproduced the
verdicts and recorded usage. In each of the five Inkbolt trials, the largest
shell reply came from a command that included a schema lookup. Across the
linked-text, mask and retouch tasks this held for all 15 agents. Commands
mentioning schema lookup produced 1,030,186 of their 1,262,527 shell-output
bytes. Some also ran other commands. On the same release, requesting the
single `retouch` operation schema described the clone operation, sampling
and transform in a 1,918-byte CLI reply, including the response envelope
and excluding the newline. The [five-pair follow-up](#a-focused-lookup-during-local-image-repair) measured what happened when agents received that request.

At this stage the combined replay covered twelve tasks and 115 genuine
attempts on one executable. All 60 Inkbolt workflows passed. The baseline passed 52
of 55 applicable attempts. Its three failures were on print delivery.
Lost-reply recovery requires an Inkbolt receipt and has no baseline arm.
Eight standard tasks still used earlier binaries.

Capture and replay audit SHA-256 `033e32bd68b95b3dc890de7c5abd500dfa3861c5decab2935e4793b43f4be6bb`.
Independent image check SHA-256 `a51f55e9c4945f72ff93a0ab68f13c7c87917a85108879ef5d8998abe990ae4e`.
Combined audit SHA-256 `f46e4f114f45783fb375bc0370a6b495c1e5d2c6019acd0029dc1ad82c97553f`.

## Linked text and foreground masks on 0.85.1

Five Inkbolt agents and five baseline agents repaired the linked story. All
ten identified the first overflowing character at offset 8 and preserved the
twelve characters, their reading order, the font and the unrelated artwork.
An independent check read the five saved session databases, checked their
state hashes and matched both revisions to the source and delivery. All ten
previews and five fresh baseline SVG renders matched the expected glyphs at
every pixel.

On the mask task, all ten retained the full 16 × 16 layer. A separate
point-in-polygon check found the same 56 selected pixels in every delivered
selection and mask. Each preview hid the other 200 pixels. All five Inkbolt
sessions also reopened the original unmasked layer.

| Median per attempt | Text, Inkbolt | Text, no engine | Mask, Inkbolt | Mask, no engine |
| --- | ---: | ---: | ---: | ---: |
| Input plus output tokens | 293,389 | 76,247 | 287,596 | 44,219 |
| Shell commands | 10 | 4 | 9 | 3 |
| Shell output, UTF-8 bytes | 84,291 | 6,460 | 77,851 | 2,543 |
| Seconds to first verified preview | 65.4 | 31.9 | 61.7 | 33.7 |
| Solve time, seconds | 82.1 | 49.8 | 91.0 | 38.1 |

The trials used the same optimized 0.85.1 Windows binary, external model
settings and baseline programs as the earlier icon-sheet trials. Within
each task, the five Inkbolt attempts ran first. Host and network load varied
and local verification overlapped some solves. Both tasks cost more tokens
with Inkbolt in these batches.

In all ten Inkbolt transcripts, the largest shell reply came from a command
that included a schema lookup. Those commands accounted for 347,321 of
446,974 shell-output bytes on text and 326,179 of 387,641 bytes on masks.
Some commands also performed other work. On the same binary, a
`schema.lookup` with `name="operation"` and `select="story/Slot"` returned
the six slot fields in 554 bytes. Selecting
`selection_shape/field:boundary/polygon` returned the polygon schema in
449 bytes, and `mask_from_selection` returned its operation schema in 431
bytes. These sizes include the CLI response envelope and exclude the
trailing newline. Their effect on model usage has
yet to be tested. [Schema selectors](AGENT_DISCOVERY.md#focused-schemas)

| Task | Capture and replay audit SHA-256 | Independent artifact check SHA-256 |
| --- | --- | --- |
| Linked text | `540f7a254ef1c8cb1bd4de9dcab05ae75b6013f541f2cce1e0e7e2a7609f7471` | `9c73749edd8d771e2b5c74f1828dcd0777b3afb13278efef6bb04426edbe79a6` |
| Foreground mask | `a1895405f0bc22840aea45c80f92fcab45e80eeb3e570847e7c8e1e7702c0f9b` | `916f70a8e4203138a3a3de8a7828f30c1876a87bc25072f0b7b933ae261339c5` |

A combined replay covered 105 genuine attempts on eleven tasks. All 55
Inkbolt workflows passed. The baseline passed 47 of its 50 applicable
attempts, with all three failures on print delivery. Lost-reply recovery
requires an Inkbolt receipt and has no baseline arm. The combined audit SHA-256 for those eleven tasks is
`ac4461425209e6be3ef36a572ada6b91c0b2b7436c8abf5c2ef8bde67711b038`.

## Large layouts and shared palettes on 0.85.1

Both arms passed five of five attempts on each task. On the 5,000-object
layout, moving one rectangle by one pixel along each axis changed exactly
22 pixels. The other 4,999 objects stayed in place. On the palette task,
one swatch edit changed both linked rectangles, covering 128 pixels, and
the green rectangle kept its original color. Inkbolt preserved the live
swatch references and reopened the original revision on every attempt.

| Median per attempt | Layout, Inkbolt | Layout, no engine | Palette, Inkbolt | Palette, no engine |
| --- | ---: | ---: | ---: | ---: |
| Input plus output tokens | 266,993 | 70,417 | 204,832 | 41,573 |
| Shell commands | 9 | 5 | 8 | 4 |
| Shell output, UTF-8 bytes | 58,916 | 885 | 51,581 | 828 |
| Seconds to first verified preview | 44.9 | 24.9 | 47.3 | 23.9 |
| Solve time, seconds | 91.5 | 39.1 | 66.0 | 30.3 |

Reading a whole layout was expensive in either arm. Two Inkbolt agents and
one baseline agent printed the complete 672,387-byte, single-line source
file. All twenty layout and palette attempts used the shell. A separate
read-only lookup returned the target object's geometry, bounds and transform
in 770 bytes. [Inspect one object](LARGE_VECTOR.md#inspect-one-object-in-a-saved-layout)

Each batch used the same optimized Windows executable, external model
configuration and baseline tools as the icon-sheet trials. The five
Inkbolt attempts preceded the five baseline attempts on each task. Host
and network load varied. Local verification overlapped some attempts.
Replaying all twenty captures reproduced the
checks, token counts, shell activity and preview times. A separate pixel
check covered the ten delivered previews, five historical previews and
five independently rendered baseline SVGs for each task.

| Task | Capture and replay audit SHA-256 | Independent pixel check SHA-256 |
| --- | --- | --- |
| Large layout | `45031e6ec8b427310cf176787c6c8434bdf21be80f7d496448229ff87fe2a26c` | `464f5af45e8162015f6c8c22b313348f84f545ac86e9221570adfc5e2232f961` |
| Shared palette | `2abe0180ab68cb6fe523fbf83d5da90e8c3998ac97c90a2783ec467240085d24` | `f2ef7eea4f4c0f36b4bfedaa0f876653e42365315bfc167a5cc49be6dcba8532` |

A combined replay checked all nine standard tasks on this executable with
the same evaluator. All 45 Inkbolt workflows passed. The baseline passed
37 of its 40 applicable attempts. Its three failures were the previously
recorded print deliveries. B17 requires a saved Inkbolt receipt. The
combined audit SHA-256 is
`c78f4dac697e9a3dc70f42104688cc8828090911ea9fb7de4ee4001a9d10fe67`.

## Aligned icon sheets on 0.85.1

Five agents using Inkbolt and five using the baseline each delivered an
editable three-board sheet and three separately cropped PNGs. Replaying all
ten captures reproduced every check. An independent decoder matched every
pixel in all 30 PNGs against the requested local position, size, fill and
transparent background.

| Median per attempt | Inkbolt | No engine |
| --- | ---: | ---: |
| Shell commands | 8 | 2 |
| Shell output, UTF-8 bytes | 35,552 | 430 |
| Input plus output tokens | 176,022 | 55,384 |
| Seconds to first verified preview on disk | 46.5 | 27.2 |
| Solve time, seconds | 63.2 | 35.7 |

The five Inkbolt trials ran first, using the same client, model settings and
engine executable as the other 0.85.1 tasks. Each requested the vector
quickstart through the CLI. Neither arm made a direct MCP call. Both arms
also passed 5/5 in the earlier batch. The Inkbolt token median fell from
313,114 on that build to 176,022 here, still 3.18 times the new baseline.
The batches differ in build and host conditions. [Earlier icon-sheet trials](#b02-at-8586e82-cli-help-and-sibling-index-guidance)

The capture and replay audit has SHA-256
`4b3f2e36ac050dd11c630e787370095aba1d5b29da45f2d9d5b881824d94a649`.

## Multilingual typography on 0.85.1

Each arm delivered five editable typography sheets and five correct glyph
reports. Independently decoding the ten PNGs reproduced the same 1000 × 960
RGBA image as the accepted reference. All ten reports matched its four rows,
including logical source intervals, glyph sequence, positioned origins and
advances. The Hebrew base and combining mark follow the order independently
observed with HarfBuzz on Windows and Linux. [Earlier typography trials and HarfBuzz check](#glyph-order-within-a-cluster)

| Median per completed trial | Inkbolt | No engine |
| --- | ---: | ---: |
| Shell commands | 13 | 8 |
| Shell output, UTF-8 bytes | 65,682 | 13,270 |
| Input plus output tokens | 298,013 | 214,257 |
| Seconds to first verified preview on disk | 69.9 | 97.9 |
| Solve time, seconds | 87.2 | 133.4 |

Both arms used the same client settings and task fixtures. The Inkbolt arm
used the executable from the screen and print trials. On the first five
scheduled launches per arm, four completed and passed in each arm. The fifth
Inkbolt launch hit a provider rate limit and its first retry hit a capacity
limit. The fifth baseline launch also hit a capacity limit. A subsequent
launch for each arm completed with the same prompt, settings and task
contract. In total, five of seven Inkbolt launches and five of six baseline
launches produced judged trials. Capture replay reproduced all ten verdicts
and their recorded usage. Timings in the table cover completed solves and
exclude the waits between launches.

The previous five-pair batch scored 5/5 for Inkbolt and 4/5 for the baseline.
That difference disappeared on this build. Across the latest batches, print
delivery accounts for the one remaining difference in artifact success. A
broader efficiency claim still needs results from the remaining tasks on the
same executable. The capture and replay audit has SHA-256
`23b617f93f80a098371a68f2da9b58c0bfcba7a89548513751f1e00d5b2bea62`. The independent
pixel and glyph check has SHA-256
`c7cd34629f84f50722a667284383cf8980e8a4004924697253ffafa404018e91`.

## Native print controls on 0.85.1

Five agents using Inkbolt delivered the requested A4 print PDF with embedded
profiles, native process and spot colors, a display preview and a receipt for
the published file. Two of five agents using the baseline also passed every
applicable check. The other three passed the preview and page geometry checks
but failed the native ink check. An independent MuPDF inspection found that
those three PDFs omitted `/UseBlackPtComp` from the required paint settings.
All seven accepted PDFs explicitly set it to `/OFF`. Leaving the setting at
its PDF default lets the print processor choose whether to apply compensation.
[PDF Association application note, page 3](https://pdfa.org/download-area/publications/PDF20_AN001-BPC.pdf#page=4)

| Median per attempt | Inkbolt | No engine |
| --- | ---: | ---: |
| Shell commands | 15 | 4 |
| Shell output, UTF-8 bytes | 131,751 | 878 |
| Input plus output tokens | 712,198 | 94,435 |
| Seconds to first verified preview on disk | 89.4 | 78.0 |
| Solve time, seconds | 149.7 | 90.4 |

The five engine attempts preceded the five baseline attempts on the same
Windows host, with the executable and client settings used for screen delivery.
Replaying all ten captures reproduced the original verdicts and usage.
The [preceding print batch](#observing-print-previews-in-delivery-folders)
scored 5/5 and 4/5 respectively. The difference in artifact success appeared
in both batches, and the baseline used fewer tokens in both. The independent
PDF inspection record has SHA-256
`b2f527b2b88ea223a154ee45dbfa0aa3f3582f4a5fc9c546c814684923d4fd8f`.

## Transparent screen artwork on 0.85.1

Five agents using Inkbolt and five using the no-engine baseline each delivered
the requested 1920 × 1080 transparent PNG, editable source and creation
receipt. Replaying the ten captured workspaces reproduced every verdict. An
independent pixel check matched every delivered pixel and confirmed the sRGB
declaration on all ten PNGs.

| Median per attempt | Inkbolt | No engine |
| --- | ---: | ---: |
| Shell commands | 7 | 2 |
| Shell output, UTF-8 bytes | 12,200 | 180 |
| Input plus output tokens | 134,535 | 41,369 |
| Seconds to first verified preview on disk | 47.4 | 30.2 |
| Solve time, seconds | 85.2 | 35.4 |

All five Inkbolt agents used the CLI and looked up both `screen.quickstart`
and `vector.quickstart`. Together those two replies accounted for 4,741 bytes
per agent. The baseline matched artifact success, and the Inkbolt arm used
3.25 times as many tokens at the median. Measure how often agents need
multiple guides on the other tasks before expanding the default catalog.

Both arms used Codex CLI 0.160.0, `gpt-6.1-sol` and medium reasoning on one
Windows host. The five engine attempts preceded the five baseline attempts.
The model and settings came from an external evaluation configuration. The
locally optimized binary from commit `a546eef` had SHA-256
`277681785bf7f47bc155bad7ef9c6bd3ffd2139f987cc801923a627bfd79db39`.
The baseline used resvg 0.47.0 and Pillow 12.3.0. The capture and replay audit
has SHA-256 `52cc076d4e09a2a147060bae2ce080c533dfadf8993c665e828e32663ee80cff`.

## Diagram, SVG and recovery trials on 0.85.1

The next 25 Windows attempts used the same client settings and the exact
executable retained from the screen-delivery trials. The five engine attempts
for each task ran first. Each applicable baseline used the same prompt,
fixtures and pinned rendering tools. All 25 workspaces were captured and
rejudged. The table reports per-attempt medians.

| Task and arm | Passed | Shell commands | Shell output, bytes | Input + output tokens | First verified preview, s | Solve time, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B01 diagram, Inkbolt | 5/5 | 6 | 7,150 | 110,522 | 38.0 | 45.9 |
| B01 diagram, baseline | 5/5 | 4 | 5,476 | 42,491 | 20.5 | 24.4 |
| B04 SVG revision, Inkbolt | 5/5 | 7 | 55,160 | 185,397 | 42.2 | 58.1 |
| B04 SVG revision, baseline | 5/5 | 3 | 536 | 59,300 | 18.6 | 49.3 |
| B17 lost edit reply, Inkbolt | 5/5 | 14 | 36,116 | 263,170 | 55.5 | 97.0 |

All ten diagrams preserved the supplied font and produced the requested pixels.
Each Inkbolt agent fetched the vector quickstart once. On B04, the revised
path, editable group and PNG passed in both arms. All five Inkbolt imports
reported remapped IDs and an omitted description. All five baseline SVGs kept
the source IDs and description. In four Inkbolt SVG trials, the largest shell
reply came from looking up several schemas together, including SVG import.
The fifth combined the import with lookups for starting a session, moving an
object and publishing. Those replies ranged from 19,116 to 36,124 bytes.
The [SVG editing example](SVG_IMPORT.md#move-one-object-and-export-the-result)
uses the import mapping and a saved revision to move one path and export it.
A [separate five-pair trial](#giving-agents-the-svg-editing-example) measured
what happened when agents received that example with their task.

The original B04 judge recorded 0/5 Inkbolt workflows and 5/5 baseline
workflows. All five agents had saved the full opt-in omission receipt, including
an empty `omissions` list. The judge compared it with a strict-mode result.
Repeating the import in the recorded mode reproduced every receipt exactly.
Only the five loss-check verdicts changed. Each captured PNG also matched the
expected 32 × 24 pixels independently. The regression checks invented and
missing omissions and altered reuse data. [Judge correction](https://github.com/skulitom/Inkbolt/commit/bae20da7fded7684f971c3b4c691dfeec84c38f8)

In B17, all five agents recovered the original edit receipt, retried the move
before and after undo, and retained the restored state and valid history.
This exercises `session.apply`. The simultaneous publication fix has separate
tests. The baseline has no session receipt to recover. All fifteen Inkbolt
attempts used the CLI. Host load was uncontrolled.

| Capture audit | SHA-256 |
| --- | --- |
| B01 original and replay | `811df9c73a44133ba7be5668b3e9898973ca686d59c5a68749f0327e2d760379` |
| B04 original and corrected verdicts | `20a2c6ba1c1d7a16689789b11c7901980bf34c9d3402383bd2c348bcb1193811` |
| B17 original and replay | `56517f4c73028d653c7b6e871cc72d7e5007e1aebab2997d2d32d502ceac7e0c` |

## Giving agents the SVG editing example

Ten agents revised the same SVG with the same Inkbolt executable, tools,
client and model settings. Five received the usual instructions. Five also
received the 2,134-byte documentation example, which uses a different
drawing and movement. The agent still had to identify the requested path,
preserve its group, disclose import losses and deliver the editable source.
The pair order alternated so the example ran first in two of five pairs.
Usage and timing figures are medians across the five attempts.
[Example given to the agents](https://github.com/skulitom/Inkbolt/blob/2736a42e3fd22a645dde9628c53999ca5d79129f/docs/SVG_IMPORT.md#move-one-object-and-export-the-result)

| Measure | Usual instructions | With example |
| --- | ---: | ---: |
| Complete workflows | 5/5 | 5/5 |
| Input plus output tokens | 213,769 | 162,125 |
| Shell commands | 8 | 7 |
| Shell commands mentioning `schema.lookup` | 4 | 2 |
| Shell output, UTF-8 bytes | 58,626 | 29,952 |
| Seconds to first verified preview on disk | 44.5 | 27.0 |
| Solve time, seconds | 68.1 | 48.7 |

Every pair used fewer tokens and reached its first preview sooner with the
example. Median token use fell 24.2%. Median shell output fell 48.9%, but two
agents given the example each printed the full `document.publish` schema,
about 94 KB in one reply. Those two produced more output than their controls.
The lookup row counts shell commands whose text names `schema.lookup`.
One command can request several schemas.

Rejudging all ten captures reproduced every check, usage count and preview
time. An independent renderer also reproduced the requested 768 pixels from
every delivered SVG. All ten PNGs matched and each original file survived.
Both groups used the CLI throughout. This trial measured direct exposure to
the example. The audit has
SHA-256 `6a3882a10514f62d14441f17324cd788e17b1cda6d00165f75f917d7fd2c0689`.

## Finding the SVG editing example unaided

All five agents on the new build found `svg.quickstart` in CLI help and
requested it while revising an existing SVG. Each transcript contains the
returned guide. The agents received the ordinary B04 task in a fresh
workspace. The prompt gave them neither the example nor its lookup name.

Five pairs used the same Windows host, fixture and judge. The client was
Codex CLI 0.160.0 with `gpt-6.1-sol` and medium reasoning. The build
order alternated between pairs, with one solve at a
time. The earlier build was `4c4e4af`. The new build was `b5d678e`, which
added discovery for the example. Usage and timing figures are medians.

| Measure | Earlier build | With discoverable guide |
| --- | ---: | ---: |
| Complete workflows | 5/5 | 5/5 |
| Input plus output tokens | 206,797 | 144,578 |
| Shell commands | 8 | 6 |
| Shell output, UTF-8 bytes | 68,099 | 20,513 |
| Seconds to first verified preview on disk | 44.0 | 33.0 |
| Solve time, seconds | 59.9 | 52.3 |

Every pair used fewer tokens and returned fewer shell bytes on the new
build. Median token use fell 30.1% and median shell output fell 69.9%.
Both builds preserved the original SVG and delivered an editable revision
with the requested path still in its group. An independent SVG renderer
and a PNG pixel check matched all 768 expected pixels on all ten attempts.
Capture replay reproduced the judges' checks, usage and timings.

These ten trials cover one task and one model configuration. All used the
CLI. The source at `b5d678e` also passed all 297 verification stages on
Windows and WSL Linux.

| Retained evidence | SHA-256 |
| --- | --- |
| Earlier executable | `ecb8a3dc8e775109792d7b84df8bf454457c5733a09967bf385860b54e64e075` |
| Executable with the guide | `3ade0dc20605fb046c5125730a08fd0938ce573a5218a5a3f4de36882f4f3f13` |
| Capture and replay audit | `3df46c9f5302ac1d56853c560eb9f82dd115b642c4ca2d06f3cf73483bbd98c0` |
| Independent artifact checks | `ca4af7f386ba6af4464ac47a5dcadc7d9894d7d7716e24c360cb9e6e5e0cb422` |

[Runnable guide](SVG_EDIT_EXAMPLE.md) · [Results across twenty tasks](#results-by-task)

## Shell and MCP activity across twenty tasks

This earlier survey covers 100 Inkbolt and 85 baseline transcripts. It
predates the single-build trials above. Among the 17 paired tasks, the Inkbolt
agents used more shell commands at the median on every task. Across those
85 attempts per arm, they ran 1,069 commands with 75 nonzero exits. Baseline
agents ran 371 commands with eight nonzero exits. All exit codes were recorded.

The shell returned 5,911,947 bytes across the paired Inkbolt attempts and
3,379,271 across the baseline attempts. B03 was the exception to the usual
direction of that difference. The baseline returned a median 672,753 bytes
per trial while editing the 5,000-object layout. On B13, both arms delivered
five accepted artifacts, with medians of 22 shell commands for Inkbolt and
two for the baseline. This makes transparent artwork delivery a concrete
workflow to investigate for interaction cost.

| Task | Inkbolt shell commands | Baseline shell commands | Inkbolt shell output, bytes | Baseline shell output, bytes |
| --- | ---: | ---: | ---: | ---: |
| B01 | 6 | 4 | 6,635 | 5,366 |
| B02 | 10 | 3 | 68,639 | 5,606 |
| B03 | 10 | 4 | 54,116 | 672,753 |
| B04 | 9 | 3 | 38,236 | 394 |
| B05 | 12 | 3 | 52,733 | 813 |
| B06 | 11 | 4 | 77,316 | 7,288 |
| B07 | 10 | 8 | 46,304 | 14,133 |
| B08 | 11 | 2 | 55,290 | 2,440 |
| B09 | 11 | 3 | 45,668 | 2,445 |
| B10 | 15 | 3 | 98,054 | 291 |
| B11 | 11 | 3 | 101,137 | 754 |
| B12 | 14 | 3 | 99,968 | 5,652 |
| B13 | 22 | 2 | 68,348 | 214 |
| B14 | 10 | 5 | 103,926 | 1,032 |
| B15 | 11 | 3 | 45,408 | 1,824 |
| B16 | 12 | 6 | 77,427 | 6,222 |
| B17 | 10 | — | 37,807 | — |
| B18 | 13 | — | 34,787 | — |
| B19 | 16 | — | 260,966 | — |
| B20 | 19 | 14 | 163,083 | 77,226 |

Each cell is a median across all five attempts. The three recovery tasks have
engine-specific contracts. Five Inkbolt attempts also used direct MCP tools,
across B08, B09 and B13. Their transcripts contain 99 completed MCP calls
including 11 marked failed. The recorded MCP results and errors occupy
1,882,464 bytes as compact JSON. Shell output and MCP reply sizes measure
different representations. [Metric definitions](BENCHMARK_COMPARISON.md)

Six of the eleven MCP failures used the same request to look up the edit action
on `session.apply`. Replaying all 74 recorded MCP schema lookups on source
`1b2fa56` succeeded for 67. With direct field variant lookup, 73 succeeded.
The six new successes returned the same schema as `field:action/edit`.
Every other reply matched the pre-change build, including a refusal for the older
generated definition name `Options6`. The output options in that request are
reachable through `document.publish` with `select:"field:output"`.
Windows and Linux returned identical replies. These are replays of recorded
requests. The model timings and task outcomes above belong to the original
solves. [Schema lookup](AGENT_DISCOVERY.md#focused-schemas)

Windows and Linux produced the same tool-activity report, SHA-256
`85525e55a47dfefa21fc54053ba0b475fda2ccf515e16345c01f10b26e754235`.
It binds the comparison method, source reports, individual transcript hashes
and measured counts. The B10 tool events come from the original solves whose
saved photo stores were [rejudged separately](#b10-rejudging-the-saved-photo-stores).

## Transparent screen delivery with Luna

Luna completed the transparent PNG task in **three of five attempts with
Inkbolt and five of five with the no-engine baseline**. All ten PNGs had the
requested straight-alpha samples at every pixel. To complete the task, the
agent also had to retain the editable source and its private note, deliver a
PNG tagged as sRGB, and verify that publishing twice preserved the first file.

| Measurement | Inkbolt | No-engine baseline |
| --- | ---: | ---: |
| Accepted artifacts and complete workflows | 3/5 | 5/5 |
| PNGs with all 2,073,600 pixels correct | 5/5 | 5/5 |
| PNGs with the required sRGB declaration | 4/5 | 5/5 |
| Median completed shell commands | 20 | 3 |
| Median shell output, UTF-8 bytes | 230,399 | 373 |
| Median input + output tokens | 627,750 | 54,013 |
| Median solve time | 150.1 s | 45.3 s |
| Median time to a judge-verified preview | 93.5 s (3 observed) | 30.8 s (5 observed) |

One Inkbolt attempt delivered an SVG instead of the requested editable JSON,
and its PNG lacked the sRGB declaration. Another left the rectangle outside
the artboard hierarchy and omitted the private note from the JSON. All ten
delivery receipts matched their original PNG hashes. Every agent used the
shell. Commands containing `schema.lookup` returned a median of 53,865 bytes
per Inkbolt attempt. Those costs prompted a [second trial with a screen
quickstart](#screen-preset-quickstart-trial).

The original judge accepted only one Inkbolt workflow. It required an empty
rectangle name and looked for the private note only on the document. The
prompt leaves object names and the location of source metadata to the agent.
The corrected judge accepts names and notes on the document's artboard or
rectangle, checks the reopened source, freshly renders it, and repeats
publication into a protected copy. Rejudging the ten retained workspaces
admitted two more Inkbolt deliveries. Baseline results stayed at five. A
separate pixel check read all ten original PNGs with pinned Pillow.

Both arms used Codex CLI 0.160.0, `gpt-6-luna` with medium reasoning, the
same B13 prompt and one Windows host. Five Inkbolt attempts ran first, then
five baseline attempts. Model selection came from the external driver
configuration. Source [`03126e5`](https://github.com/skulitom/Inkbolt/commit/03126e53d590efbc4616d0ba8fbfb1f40a7fdc02)
produced the retained engine. Timing reflects uncontrolled host load. Cost
medians include failures. Only three pairs passed in both arms, below the
five required for a paired cost ratio.

| Retained evidence | SHA-256 |
| --- | --- |
| Original comparison | `f3816543980b02c5d2e3179894a9c3199a0cd46d3d6cdd63d05d3f3fcdfd7055` |
| Original-judge replay | `7b4117d214d85ce847eab26550dab09b533abd678446b69218279ef2c5171a22` |
| Corrected comparison | `4cf73ab774f12ae0c2cc896858407d00c84d2b8fe752fe07e3a9beb4cdc862dd` |
| Independent pixel and transcript checks | `d051d77a45acde2dd9767b1a33e8ddddad8021acee0882f9f641a3252ba91927` |

### Screen preset quickstart trial

With the new guide, **four of five Inkbolt attempts passed the original judge**,
up from three of five. The fresh no-engine baseline passed five of five.
All five Inkbolt agents received the guide in shell output. They used a median
of 11 shell commands, down from 20, and 61.6% fewer tokens than in the earlier
batch. The predeclared rule required the guide to reach a solver, at least
three complete workflows and a median below 20 shell commands. Keep the
pointer in CLI help. [Four-request workflow](AGENT_DISCOVERY.md#screen-artwork)

| Measurement | Earlier Inkbolt | With quickstart | Earlier baseline | Fresh baseline |
| --- | ---: | ---: | ---: | ---: |
| Complete workflows, judge frozen before the trial | 3/5 | 4/5 | 5/5 | 5/5 |
| Complete workflows after rechecking both solid paint encodings | 3/5 | 5/5 | 5/5 | 5/5 |
| Median shell commands | 20 | 11 | 3 | 3 |
| Median shell output, UTF-8 bytes | 230,399 | 34,032 | 373 | 3,146 |
| Median input + output tokens | 627,750 | 240,966 | 54,013 | 53,390 |
| Median solve time | 150.1 s | 94.9 s | 45.3 s | 33.7 s |

The attempt rejected by the frozen judge used normalized RGBA values for the editable fill.
Each channel was exactly the requested byte divided by 255. Its PNG had
every expected sample and the required sRGB declaration. The frozen judge
required the byte-array form of the editable fill. The corrected judge also
admits its exact normalized equivalent. Perturbing any one channel by one
representable floating-point step still fails the source check. Rejudging
all twenty retained workspaces with their original binaries and tools changed
only this one outcome. All ten fresh PNGs passed a separate pixel check.

The follow-up used source `91f54c5`, the same Windows host, prompt, client,
Luna settings, pinned baseline tools and arm order as the earlier trial. The
guide demonstrates an ellipse on a 256 × 256 icon. The unchanged task asks
for a translucent rectangle on a 1920 × 1080 artboard. All cost medians
include every attempt. The five pairs that passed the corrected judge still
used 4.51 times as many median tokens with Inkbolt as with the baseline. Host
load was uncontrolled and five attempts per arm leave wide uncertainty.

Four agents received the guide on their second shell command and one on its
third. Two later asked `command.fields` for one named command. The evaluated
build rejected all five such queries. Replaying them after the [single-command
lookup change](AGENT_DISCOVERY.md#focused-schemas) returned the same required
and optional fields as the family listing, in 335–347 bytes per reply on both
Windows and Linux. The trial costs above include the original five refusals.

| Retained evidence | SHA-256 |
| --- | --- |
| Fresh comparison with the frozen judge | `64fdf90163f04eda86694077fa55f7cfcf2de0145fb52ff4bef27d2073788866` |
| Earlier and fresh batches rejudged | `4ba6c2f1dc59d4c7c581ca1c4da7d84fb5f391e81b8de60ca3a8cf0b78ffd5d5` · `8f52fcc068a8221b51d96817cdb3b4872de4e77039b536570bc60cedcc28ef28` |
| Guide exposure and original-judge replay audit | `17e9a7ae65e30045618e1ac37e0a711d309ece09c5d69e0b48ca1a39fbdecdd5` |
| Independent checks of fresh PNGs and captures | `00ef48a9d43ce8d11e5e254174c9cd543ab7e22a29e904cfeddb7651c6c5eb0a` |

## Observing print previews in delivery folders

All five Inkbolt attempts published the requested PDF and identified its
receipt. Four baseline PDFs passed. The remaining PDF set
`/UseBlackPtComp false` on its paints. Its pixels passed, but the required
PDF value for disabling black-point compensation is the name `/OFF`.
[PDF Association application note](https://pdfa.org/download-area/publications/PDF20_AN001-BPC.pdf#page=4)

The client recorded all ten accepted previews, including three delivered as
`delivery/preview.png`. Each timestamp matched the final file's relative
path and SHA-256 and a passing pixel check. Replay reproduced all outcomes
and timestamps, including the preview of the failed PDF delivery.

| Median across five attempts per arm | Inkbolt | Baseline |
| --- | ---: | ---: |
| Time to client-observed preview | 66.8 s | 88.6 s |
| Solve time | 100.2 s | 93.1 s |
| Tokens | 384,883 | 79,691 |
| Completed client shell commands | 10 | 5 |
| Captured shell output, UTF-8 bytes | 103,926 | 1,032 |

A shell command can contain several engine requests. Commands whose text
included `schema.lookup` produced a median of 79,553 bytes of captured
output per Inkbolt attempt. These measurements describe what the client
received from its shell. Engine wire traffic and internal model-call counts
remain unknown for this task.

The [preceding five pairs](#identifying-the-delivered-print-pdf) used the
same engine binary, prompt, fixtures, client binary, model settings and
baseline tools. Changing the observer allows a timestamp for a file in a
subfolder. Differences in solve time or tokens between the two small batches
cannot be attributed to it.

| Evidence at `ee27237` | SHA-256 |
| --- | --- |
| Five Inkbolt attempts | `37c22037c9d74a09b26ff481654899e00193a5d199d3b6039e18898cb5b6a68e` |
| Five baseline attempts | `c01759effd9e71e5f88ced535811494aca463a82540326fb36b893f11f586df8` |
| Matched comparison | `ef4ad367db6d89200bb3c92dff5f3e1792ca96e4d60587e6dc027cde1ebef428` |

## Identifying the delivered print PDF

In the [earlier B14 batch](#b14b15-at-7d31cf9-print-delivery-and-resource-repair),
each session ledger contained a completed publication for the exact PDF.
Two agents selected the completed snapshot publication from the same revision.
Prompt version 2 asks for the request ID whose PDF hash matches the delivery.
All five new Inkbolt agents supplied it. Both arms produced five accepted
print deliveries. The earlier baseline passed four.

The original judge rejected the fourth Inkbolt snapshot because it omitted
default fields such as visibility and explicitly set knockout on the fills.
Reopening that file yielded exactly the required document. The corrected
judge compares the complete validated source with the reference and saved
session. All ten retained deliveries were rejudged against their original
inputs. The corrected check admitted this one additional workflow.

| Five Windows attempts per arm at `93ebea4` | Inkbolt | Baseline |
| --- | ---: | ---: |
| Median tokens | 466,033 | 95,336 |
| Median solve time | 115.2 s | 90.9 s |
| Median time to client-observed preview | 74.7 s (5/5 observed) | 85.4 s (3/5 observed) |

Two accepted baseline previews were saved in a delivery folder, beyond the
root-only timing of this batch. The historical and new batches used the same
client binary and model settings. Engine and driver versions differed.
The matched comparison after rejudging at `c54a7f6` has SHA-256
`32c3cf3213c888cf988091b2f82a686e973ff491b0089c9c3a9750b6a5b8e6c9`.

## Glyph order within a cluster

Prompt version 2 asks both arms to retain the shaping engine's glyph sequence
within each directional run, including when a mark is drawn to the right of
the glyph that follows it. Windows and Linux HarfBuzz builds independently
agreed on the order for the supplied font. The fixture and acceptance checks
are the same as in the [earlier batch](#b06b07-at-a7e034e-captured-trials-rejudged).

| Five Windows attempts per arm | Inkbolt | Baseline |
| --- | ---: | ---: |
| Correct rendered image | 5/5 | 5/5 |
| Exact glyph and cluster report | 5/5 | 4/5 |
| Median tokens | 240,831 | 217,180 |
| Median time to client-observed preview | 59.8 s | 99.3 s |
| Median solve time | 77.7 s | 126.6 s |

Baseline attempt two reversed the two adjacent entries for the Hebrew base
and its mark. The earlier baseline reversed those entries in all five attempts.
All five new pairs matched in the comparison, and replay reproduced every
check and reported timing. Both batches used the same pinned client and model
settings. Changes to the engine and driver between batches limit what can be
attributed to the wording alone.

| Evidence at `8c87af0` | SHA-256 |
| --- | --- |
| Inkbolt attempts | `1c9252acd6a1e94230e597339e38974c1f8e19234309b2fc393c3edfb1b428f3` |
| Baseline attempts | `71626f61f850f1e638f48fca475b67a6be59401c92923e0a6bbd7569a36aeab4` |
| Matched comparison | `fe4f1d8926d7fbfab5d528d6dd6b5fcdb0f03518471ff336c20cdaa576803abe` |

## Command discovery during export recovery

Five Windows agents recovered the interrupted export from its pinned revision.
Each agent recolored the newer revision on its first edit. All nine checks
passed in every attempt, including cancellation, source preservation and
single publication. Replay reproduced the checks, receipts and measured values.
Both batches used B19 prompt version 5, the same pinned CLI executable for the
model client, the same driver configuration and the same model settings.

| Median per attempt, five per batch | [Previous](#interrupted-export-recovery-with-a-vector-fill-edit) | With grouped field lookup available |
| --- | ---: | ---: |
| Engine commands | 43 | 28 |
| Request bytes | 3,476 | 3,487 |
| Response bytes | 220,327 | 224,505 |
| Invalid calls / retries | 4 / 3 | 2 / 3 |
| Tokens | 614,476 | 530,157 |
| Time to verified engine preview | 64.3 s | 67.1 s |
| Time to client-observed preview | 71.9 s | 78.1 s |
| Solve time | 141.2 s | 142.8 s |

The [grouped lookup](AGENT_DISCOVERY.md#focused-schemas) exposes input names
for related commands in one response. In ten earlier B19 and B20 attempts,
agents made 148 schema queries. No attempt repeated the exact same query.
Of these, 91 asked about an individual command without a field selector or a
full-schema override. Across those attempts, 26 family queries would cover the
same top-level field names. Individual responses also supply types, allowed
values or examples that a field list cannot supply.

In the new B19 batch, two agents opened the index and made 25 and 19 schema
queries respectively. The other three completed the task without a schema
lookup. None requested the grouped field list. The lower command and token
medians cannot be attributed to that lookup. Further discovery changes need
evidence of a specific input that agents struggle to supply.

| Evidence at `2d4d7d8` | SHA-256 |
| --- | --- |
| Evaluated Inkbolt executable | `eb0b5ebf939e06cb728a8b01172215b4ac65d7769bcae95ae9c03cd7367c1beb` |
| Five attempts | `9e16e364a678be7e2334c86989ed6061a9e5d15b129c1e96287fa2824f30dead` |
| Capture replay | `7b94e01e7f6cc26217155ebca2399658b908867019a1894620b14d63dae89ff3` |
| Field comparison across 96 commands with and without workspace defaults | `bd4a16b354b333401896b184453b9a8afdd28e466aec448669878bac1db941b2` |

## Interrupted export recovery with a vector fill edit

On Windows, five agents cancelled an active export, queued a fresh export,
recolored the badge in the current document, and recovered the interrupted
export from its earlier revision. Each used `op:"fill"` successfully on the
first badge edit. All five passed the nine independent checks. Rejudging
their retained captures reproduced every verdict, receipt and reported metric.
The [earlier batch](#b10b17b19-at-447bbc2-request-guidance-follow-up) passed 4/5.

| Median per accepted attempt | Earlier four | Current five |
| --- | ---: | ---: |
| Engine commands | 30 | 43 |
| Response bytes | 342,539 | 220,327 |
| Tokens | 569,666.5 | 614,476 |
| Time to verified engine preview | 61.6 s | 64.3 s |
| Solve time | 119.7 s | 141.2 s |

Four agents made 12–19 schema lookups and one completed the task without a
lookup. Keep the fill edit. The higher command and token counts leave overall
efficiency open. Both batches used prompt version 5, Codex CLI 0.160.0 and the
same model settings. Other engine and driver changes also separate the batches.
The current driver measured a median of 71.9 seconds to the first client event
observing a verified preview file across all five attempts.

The evaluated source was `a8a3617a1fa29fe5c983961880a215f3a87619cf`.
An initial launch configuration resolved to CLI 0.164.0. Its version check
stopped all five launches before any model solve. The evaluation used the
retained CLI executable with the same SHA-256 as the earlier batch.

| Retained evidence | SHA-256 |
| --- | --- |
| Evaluated Inkbolt executable | `da7a6506cfe4bec87764e7942216ba269715bea969ede4390aaa24682057f989` |
| Five model attempts | `b1fc8586cba08b336496a7d8f79debd95711b216b3ff26d4e0b79f3eab436bed` |
| Capture replay | `8d20e57ca658a15c3d9dc55f63cfb01e99295bfedba60c1dead684218ef4e156` |
| Per-attempt review | `67afec043aaf6e7fd4a7216bdc39bb7efb43e2bd24af0d0f852111774aaa7bbb` |
| Initial startup failures | `34c790706bcbf524f2d57642c644857d58590e6eac1b2fcf2f3be53d79b139f1` |

## Timed sequence handoff with one discovery example

All five Inkbolt attempts created a two-frame graphic, moved one layer and
relinked only its clip in the saved timeline. All five baselines delivered
the required artwork and video. Version 5 of the shared prompt gives a
working Cutbolt schema query and identifies the `result.handoff` field
to save. Each Inkbolt agent found `handoff.quickstart` in the index and
used the layer sequence and retiming operations to set the initial holds.
All five preserved those holds through the subsequent artwork revision.
[Evaluated prompt](https://github.com/skulitom/Inkbolt/blob/d153e39/tools/benchmark_prompts/B20.md) · [Handoff example](AGENT_DISCOVERY.md#linked-graphics)

| Windows, five measured attempts per arm | Inkbolt | Baseline |
| --- | ---: | ---: |
| Accepted artifacts and complete workflows | 5/5 | 5/5 |
| Median client observation of the delivered preview, seconds | 131.7 | 77.1 |
| Median client runtime, seconds | 192.6 | 106.0 |
| Median input + output tokens | 921,483 | 284,822 |
| Median combined engine commands | 74 | 17 |
| Median combined response bytes | 269,427 | 102,387 |

The preceding batch passed 3/5 and 4/5 respectively. Its three successful
Inkbolt attempts made 28–31 focused Inkbolt lookups. The five new attempts
made 16–19 each. They also made 15–20 Cutbolt schema calls apiece. The
remaining cost gap is 3.24 times the baseline's median tokens. The guide
and prompt changed together, so the comparison measures their combined use.

The sequential trials used the same external client, model settings, deadline
and consumer binaries as the preceding batch. Imports reproduced all ten
outcomes and measurements and matched the hashes of the deliveries and recorded
traffic. All ten clients observed the accepted final PNG. Four Inkbolt attempts
also supplied a matching preview from the engine, at a median of 113.1 seconds.

| Evidence at `d153e39` | SHA-256 |
| --- | --- |
| Evaluated Inkbolt executable | `b19d35b8d7ec03a359920418a2d0acec2d8433998564640fa894df765a536f3f` |
| Inkbolt report | `ace3fc380e104bf1f4207d0dfca926faaf353e5d3901c71c54089941c917807b` |
| Baseline report | `808159fe9821a79a0e3cc5086155ba8d167d8b50aecc4829f79f483f02593ef6` |
| Comparison report | `61df82dd3dad3431c5f3e80dc2a71872375be6a0ba06c5ce5e2e90e426754edf` |
| Replay audit | `f286aba1b73653cc3912a72638472f003a961a2b62592ad8caf7dde59fce495e` |

## Linked graphics with explicit layer visibility

The agent sets the timing of two frames, moves one layer four pixels, then
relinks one clip in a saved Cutbolt timeline. Both frame durations and the
other clip must survive the edit. Version 4 of the prompt specifies how to
preserve the editable pixel layers and their visibility when frame selection
is cleared. It also points to focused Inkbolt schema lookup and describes
how to give each bridge call a unique label. This batch used the same engine
binary, Codex CLI 0.160.0, model settings, consumer tools and 600-second
deadline as the preceding batch. The ten attempts ran sequentially on Windows.
[Evaluated prompt at `efcd3c9`](https://github.com/skulitom/Inkbolt/blob/efcd3c9/tools/benchmark_prompts/B20.md)

| Five attempts per arm | Inkbolt | Baseline |
| --- | ---: | ---: |
| Accepted artifacts and complete workflows | 3/5 | 4/5 |
| Attempts with validated solve metrics | 3/5 | 5/5 |
| Median client observation of the delivered preview, seconds | 139.8 | 85.9 |
| Median client runtime, seconds | 195.2 | 107.8 |
| Median input + output tokens | 1,057,499 | 335,799 |
| Median combined engine commands | 86 | 21 |
| Median combined response bytes | 279,136 | 109,463 |

Both Inkbolt failures put a second `command` field inside the arguments of
a Cutbolt schema request. A successful query in the same batch used
`"command":"schema"` with `"arguments":{"name":"session.create"}`. One
disqualified attempt passed all 16 individual checks. The other also saved
the complete export reply where the handoff pin was required. The baseline
failure omitted both handoff inventories and passed the preview check.

All five Inkbolt attempts used focused lookups, between 17 and 31 per
attempt, and none fetched Inkbolt's full schema. The median combined
response fell from 629,136 to 279,136 bytes across measured attempts in
the two batches. Inkbolt still used 3.15 times the baseline's median tokens
in the new batch. Each median uses every validated capture in its arm,
including the baseline failure. The two protocol-invalid Inkbolt attempts
count toward the success rate and have no validated timings or token counts.

Client preview time records the first completed client event that observed
the final, pixel-checked `preview.png`. The native engine returned those
pixels sooner, at a median of 124.6 seconds. Imports reproduced the checks
and measurements of all eight validated captures. The replay audit also
matched the hashes of their delivered files and recorded engine traffic.

| Evidence | SHA-256 |
| --- | --- |
| Evaluated Inkbolt executable | `d1290802199821ee0633f658233df3eab226f2a1c9ad2891df707e138bcff121` |
| Inkbolt report | `43e81fd5e70e1396414c3f33cce47e213d49ef5a7d391ddd298396020644fa6a` |
| Baseline report | `4774172212c8d365a2820c311567305cfedfbbf2f758812d60f2911f46294e72` |
| Comparison report | `f9f8ef5a6c910be0b1b8b688d73a44a0d825a92e3f7487d83d53e0eb302d7874` |
| Replay audit | `c131ed3a3460c8eae16cdc8fa79bf17c3cc44ff547244174f64dac2f9f3b886a` |

## Linked graphics with single-frame editing available

At `4bf68f9`, five agents tried to create and revise a two-frame graphic in
Inkbolt and relink it in a saved Cutbolt timeline. None finished the full
workflow under the version 3 prompt. All five no-Inkbolt attempts passed.
The preceding batch with this prompt passed 3/5 and 5/5 respectively.
[Version 3 prompt](https://github.com/skulitom/Inkbolt/blob/4bf68f9/tools/benchmark_prompts/B20.md) · [Earlier results](#b19b20-at-f61d952-recovery-pilot-and-five-pair-handoff-follow-up)

Four native attempts saved the second layer as hidden in the base state.
That layer needed to be visible again when the frame selection was cleared.
One of those four also used a different editable pixel representation.
Its saved timeline and retry receipt were correct. The other native attempt passed all
16 individual checks, but repeated a consumer discovery label and failed
the protocol gate. Two native attempts in total repeated discovery labels.
Those attempts have no validated capture or solve metrics.

All five native attempts fetched Inkbolt's full schema. Each reply was
204,962 bytes. None issued a `sequence_retime` edit. B20 requires the
initial holds to be preserved through the revision. Discovering how to
change an existing frame's duration would require a separate task.

| Windows, five attempts per arm | Inkbolt | Baseline |
| --- | ---: | ---: |
| Accepted artifacts and complete workflows | 0/5 | 5/5 |
| Attempts with validated solve metrics | 3/5 | 5/5 |
| Median input + output tokens, observed attempts | 1,067,109 | 288,988 |
| Median client seconds, observed attempts | 211.0 | 113.5 |
| Median combined engine commands, observed attempts | 58 | 19 |
| Median combined response bytes, observed attempts | 629,136 | 136,034 |

The arms ran sequentially with the same externally selected client, model
settings, 600-second deadline and pinned consumer tools. Independent imports
reproduced the eight validated captures, including their outcomes and original
measurements. The other two attempts remain in the denominator. No attempt
provided a verified preview time. The new client file observation requires
a fresh trial with sampling enabled.

The comparison report has SHA-256
`cd7cdd808138dc9f9ecff5b00468683ecdb83b9250465c0b2ec2008d7fc2b90a`.
The replay review has SHA-256
`7d2f28d8b26dc32ee89b7b400677d27e0de8409930a5a368e4d3d37f4720b3a1`.

The original judge marked the fifth Inkbolt attempt's undo/retry check as
failed. Between undo and retry the agent read historical revision 1, then
the restored revision 3. The judge selected the first read. It now checks the
requested project and store, the requested and returned revision, and where
the read occurred in the sequence of calls. An additional replay of the eight
validated captures changed only that check to a pass. Both workflow totals
and every original solve measurement stayed the same. The correction audit
has SHA-256 `21d4a80905e2defb2b0fc75c7f6bde422e730c602d61ace32e9bfbcc9695cbce`.

## Mixed composition with a movable source layer

All five Inkbolt attempts kept the source layer movable, changed only the
shadow offset and delivered the correct historical and revised previews.
All five baseline attempts preserved the original file and delivered the
correct editable controls and revised PNG. The three earlier Inkbolt batches
each had two unwanted layer locks. Version 2 of the shared prompt specifies
both the original file's byte identity and the ability to move the layer in a
later edit. The fixtures, editing requirements and both judges stayed the same.
[Version 2 prompt](../tools/benchmark_prompts/B11.md) · [Previous five pairs](#mixed-composition-with-the-image-quickstart)

| Five attempts per arm | Inkbolt | No-engine baseline |
| --- | ---: | ---: |
| Complete workflows | 5/5 | 5/5 |
| Median seconds to the observed revised PNG | 65.1 | 41.9 |
| Median total client seconds | 93.5 | 53.8 |
| Median input + output tokens | 367,710 | 72,324 |
| Median completed shell commands | 11 | 3 |

Inkbolt used 5.08 times the baseline's median tokens across the five successful
pairs. Every Inkbolt agent read the image placement guide. Shell commands that
mentioned `schema.lookup` produced a median of 84,448 UTF-8 bytes of combined
console output per Inkbolt attempt. Some commands requested several schemas at
once. The figure covers the captured shell output, including any other work in
those commands. Full engine traffic and model-call counts remain unmeasured.

The ten attempts ran sequentially on Windows at `0deed82`, Inkbolt first,
with the preceding batch's driver, model settings and baseline tools. The
new build also included single-frame timing edits. All ten captures replayed
with identical checks, recorded timings, token counts and workspace identities.
Preview times use the first completed client event with the delivered revised
PNG's hash. Five pairs establish the result for this batch.

| Retained report | SHA-256 |
| --- | --- |
| Inkbolt | `df8033f94efe1e9127d99cc1e931659efdd3be4f8fc37b3e26d2a42faccfe22b` |
| Baseline | `39597b47aba07016aae34f90cb0ae6dd61c8ce7a705727965385ae02164eac42` |
| Matched comparison | `25302a47dc05eb9ff3b6c3a26c43f4f611ae6e5ca12b17acbfb8a1f56c04c44f` |

## Mixed composition with the image quickstart

All five Inkbolt agents read the image placement guide, preserved the original
file and delivered a pixel-correct revised PNG. Three also delivered the requested
editable composition. In attempts one and four the sole difference in both
saved documents was `locked: true` on the source layer. The five baseline agents
all delivered the required editable manifest and PNG. [Image placement guide](AGENT_DISCOVERY.md#place-an-image)

| Five attempts per arm | Earlier Inkbolt | Inkbolt with guide | Earlier baseline | Fresh baseline |
| --- | ---: | ---: | ---: | ---: |
| Complete workflows | 3/5 | 3/5 | 5/5 | 5/5 |
| Correct revised PNGs | 5/5 | 5/5 | 5/5 | 5/5 |
| Median seconds to the observed revised PNG | 76.3 | 71.5 | 39.7 | 37.2 |
| Median total client seconds | 98.9 | 91.7 | 48.5 | 44.5 |
| Median input + output tokens, including failures | 513,525 | 375,355 | 58,445 | 57,938 |

Median Inkbolt token use fell 26.9% between these batches. The same layer
property accounts for the two failures in each of three five-attempt Inkbolt
batches. The shared prompt asks for a “pinned original image” and default
remaining properties. A future paired trial should specify directly that the
file's bytes are fixed and the placed layer must remain movable.
[Version 1 prompt used in these batches](https://github.com/skulitom/Inkbolt/blob/6605ca293f7ae33a218b4f85c86b84e5e1b9da79/tools/benchmark_prompts/B11.md) · [Previous batch](#mixed-composition-and-the-source-layer-lock)

At `6605ca2` both arms ran sequentially on Windows with the preceding batch's
prompt, judge, client and external model settings. The guide was opt-in. Its
placement instructions and snapshot example appeared in every Inkbolt transcript. Timing uses the earliest
completed client event with the delivered revised PNG's hash. All ten captures
replayed with identical check outcomes, recorded timings and file identities.
Only three pairs passed both arms' artifact checks, below the five needed for
a paired cost ratio.

| Retained report | SHA-256 |
| --- | --- |
| Inkbolt | `830271637ad2d938a2967bb716ab89f1e41127b0eb80c28eb05554dbca8b34c1` |
| Baseline | `3a93f2040176e7c09c77c343be0791627c6ea41bd2d47239434f8e02e454d340` |
| Matched comparison | `07a1af0f8e662c84f8953ee30d898c01ba4a698967364d4b189c6df72a707900` |

## Mixed composition and the source-layer lock

All five Inkbolt agents rendered the requested revised pixels. Three preserved
the full editable composition. In attempts four and five, the agent also locked
the source image layer when creating revision zero. The task specified default
layer properties. The image identity and original PNG were correct in both
failures. The same property differed in two of the five earlier attempts.
[Earlier B11 results](#b11b12-at-30c4ebd-mixed-composition-and-layout-variants)

| Five attempts per arm | Inkbolt | No-engine baseline |
| --- | ---: | ---: |
| Accepted editable compositions | 3/5 | 5/5 |
| Correct revised PNGs | 5/5 | 5/5 |
| Median seconds to the observed revised PNG | 76.3 | 39.7 |
| Median total client seconds | 98.9 | 48.5 |
| Median input + output tokens, including failures | 513,525 | 58,445 |

These timings use the first completed client event that observed the exact
delivered `preview.png` bytes. Inkbolt also required a historical preview.
The baseline retained the editable image, mask and effect manifest. Three
pairs passed all applicable checks in both arms, below the threshold for a
paired cost ratio.

Five fresh attempts per arm ran sequentially on the shared Windows workstation
at `432cbd9`, Inkbolt first. Both used the unchanged B11 prompt and judge,
Codex CLI 0.160.0 and externally configured `gpt-6.1-sol` at medium reasoning.
All ten captures replayed with identical check outcomes, timing observations
and workspace and transcript identities. The results identify a repeatable
editing error. They do not establish how often other clients or models make it.

| Retained report | SHA-256 |
| --- | --- |
| Inkbolt | `3f3184c3d2699278e5bd2fe5d74de24c50e15dda98ab7f84784175bb69e9d32f` |
| Baseline | `ea09e0fc4bb4798478f83746faa5da38ecaa6e694c4df30bacf2a26ac5524086` |
| Matched comparison | `01f44bf0720c58bf3d18b919d06a0fbb38c31cc511546e924f9b73d32c441ed1` |

## Diagram authoring with the vector quickstart

Each of five Inkbolt agents found the vector quickstart through the CLI and
delivered the correct diagram, editable snapshot and pinned font. Median time
to the first observed accepted PNG fell 36.5% from the previous timed batch.
Median input and output token use fell 59.7%. The no-engine baseline also
completed all five fresh trials and remained faster. [Quickstart request](AGENT_DISCOVERY.md#vector-quickstart)

| Five attempts per arm | Earlier Inkbolt | Inkbolt with quickstart | Earlier baseline | Fresh baseline |
| --- | ---: | ---: | ---: | ---: |
| Accepted workflows | 5/5 | 5/5 | 5/5 | 5/5 |
| Median seconds to first observed accepted PNG | 52.6 | 33.4 | 18.5 | 17.7 |
| Median total client seconds | 62.3 | 38.6 | 23.0 | 26.1 |
| Median input + output tokens | 268,880 | 108,481 | 42,310 | 57,108 |
| Median completed shell commands | 21 | 6 | 4 | 4 |

The median number of shell commands mentioning `schema.lookup` dropped from
15 to one. Their median combined console output fell from 78,265 to 2,213 UTF-8
bytes per attempt. Every new Inkbolt transcript contained the returned
quickstart. A shell command can invoke several tools. Underlying model calls
and complete engine traffic remain unknown.

The two batches used the same diagram prompt, fixtures, client, externally
selected model and settings, preview clock and independent checks. Each ran
Inkbolt first and the baseline second on the same shared Windows workstation.
The new Inkbolt executable came from `4ff86dc`. All ten fresh captures replayed
with identical outcomes, timestamps and delivered file identities.
These measurements cover one diagram task and one model configuration.
[Earlier timing evidence](#time-to-the-first-accepted-diagram-preview)

| Retained report | SHA-256 |
| --- | --- |
| Inkbolt | `2b1e55bfff631b0ff43f0e6fa1a787314e84313513949adf3971df08d32bdc5c` |
| Baseline | `1df6c47d46c06c6a5be32870f50b7722df0c255904be4f5bb631f56990318422` |
| Matched comparison | `122b28689dd87cbba5e8a2d75b8d90b07ced234d35200f9e6a239f456f1bd1d0` |

## Time to the first accepted diagram preview

All ten agents delivered editable labelled diagrams with the requested pixels
and font. The median time from client startup to the first observation of the
accepted PNG was 52.6 seconds with Inkbolt and 18.5 seconds with the no-engine
baseline. The independent judge matched the delivered bytes against the
artwork check. [Diagram task](../tools/benchmark_prompts/B01.md) · [Timing method](BENCHMARK_CODEX.md)

| Five attempts per arm at `ff66486` | Inkbolt | No-engine baseline |
| --- | ---: | ---: |
| Accepted diagrams and complete applicable workflows | 5/5 | 5/5 |
| Median seconds to first observed accepted PNG | 52.6 | 18.5 |
| Observed range in seconds | 46.9–60.8 | 18.2–20.2 |
| Median total client seconds | 62.3 | 23.0 |
| Median input + output tokens | 268,880 | 42,310 |

Both arms used Codex CLI 0.160.0 and the same externally selected model and
settings. Five Inkbolt attempts ran first, followed by five baseline attempts
with resvg 0.47.0 and Pillow 12.3.0 on the same shared Windows host. The Inkbolt
transcripts recorded 8–27 completed shell commands per attempt. Each baseline
transcript recorded four. A shell command can group several operations, so
the number of engine or model calls remains unknown. A separate one-pair pilot
passed before this batch and is excluded from the table.

The driver sampled files at completed client events. Each time is an upper
bound on when the delivered bytes first became available and includes setup,
discovery and editing. Five pairs show a gap worth addressing on this task.
They cannot attribute the delay to a particular engine operation. Replaying
all ten captures reproduced every verdict, file identity and timestamp using
the archived Inkbolt executable for the native arm.

| Retained report | SHA-256 |
| --- | --- |
| Inkbolt | `fbf7dae4cb810b64a0c1cb7c5e980cef3d7922344ffe4cba8082ca75b370b568` |
| Baseline | `bfb631d35fe2e67287dbb35859475c49d7472dce3865bc26ff1ea1121bb6333b` |
| Matched comparison | `8b318e7902089917f9c59f1b3865c3433ab66ea84ef9ccae11cf6e56bce3b9ac` |

## B10 rejudging the saved photo stores

All five Inkbolt attempts and all five baseline attempts at `447bbc2` delivered
the requested 1920 × 1080 RGBA16 repair. The previous judge looked for native
tiles in `.inkbolt/assets`. Attempts 2 and 4 used `tiles` and `native-tiles`
and recorded those stores in their saved sessions. The prompt specifies the
native samples, edit, history and deliveries. It leaves the tile directory to
the caller. [Task prompt](../tools/benchmark_prompts/B10.md)

On fresh copies of the ten original captures, the earlier judge reproduced
the recorded 3/5 Inkbolt and 5/5 baseline outcomes. The corrected judge traced
each store through the import, review and four revision receipts. It verified
the immutable blocks, every channel in both delivered and freshly exported
TIFFs, the preview, undo/redo, history and the original memory observation.
All eleven Inkbolt checks passed in each attempt. Transcript and workspace
hashes, client time and token counts matched the original reports. Median
token use was 580,184 versus 75,230 (7.71×), and median client time was 128.3
versus 63.7 seconds. These are the same ten model executions. The separate
50 MP experiment retains its own results.

Both judges used the same optimized reader rebuilt from the 898 archived source
files and locked toolchain of the original evaluation. The rebuilt executable
had a different SHA-256 from the original solve executable. Each original
client contract, capture and transcript was verified independently. New model
runs retain the executable itself for exact-binary replay.

| Retained evidence | SHA-256 |
| --- | --- |
| Original solve executable | `2b5a6275cb502d4fd31797d990a5b05e409dd3a5f33736356223fe615bac9ad2` |
| Rebuilt reader for both judges | `a419381a990f6b8d2d998aba789bda6acc3e67e443187a8cdf4d54c695e7cf51` |
| Earlier judge replay | `cb2b39be41d0f3a0d2123e6cb5f4e39fea3dd906ba85e64899dece93e1ac886b` |
| Corrected judge replay | `f6eb7a7161c5d7127bc4a20c9152ae0132ba5444067786d2ca8e8060de007351` |

## B17 with the workspace in the CLI launch command

All five agents recovered the original edit receipt on their first receipt
request when the client supplied the executable and its workspace arguments
together. All five also delivered the correct preview, restored the document
with undo and retried the original edit without disturbing the restored state.
[Recovery task](../tools/benchmark_prompts/B17.md) · [CLI workspace example](AGENT_WORKSPACE.md)

| Five Windows attempts per batch | Complete workflows | Attempts with a missing session root | Median input + output tokens | Median client seconds |
| --- | ---: | ---: | ---: | ---: |
| [Bare CLI executable at c3fd51f](#b17-at-c3fd51f-saving-a-recovered-receipt) | 5/5 | 5/5 | 222,485 | 87.2 |
| Executable with workspace arguments at 77c6a17 | 5/5 | 0/5 | 178,056 | 75.1 |

The prompt, fixtures, judge, engine executable and client/model settings were
the same across batches. The direct CLI tool description changed. All ten
agents chose the CLI with core MCP also available. The five earlier attempts
used `--result-only`. The new attempts read the result from the usual JSON
response. The first receipt calls in the new transcripts used the selected
workspace, including one through a saved PowerShell helper.

Median tokens fell 20.0% and median client time fell 13.9% in this task.
The two sequential batches ran on a shared host. Five attempts per batch leave
the size and repeatability of the cost difference uncertain. B17 has no
no-engine counterpart. Engine-call counts, traffic, retries, first verified
preview time and engine-only memory remain unmeasured.

The comparison verified both sets of workspace, transcript, result and
contract hashes. Replaying the five previous captures with the identical
engine executable passed all six checks per attempt. The fresh evaluation
report SHA-256 is `82d5809e15d032f2a4301d571084362f876459a1ef8c567d3bef8b4c6a218401`.
The previous-capture replay report SHA-256 is
`cac6498874161bfebb9adad22df236c42dfb276057a7c823709feb35b407377a`.

## B17 at c3fd51f: saving a recovered receipt

All five agents found `--result-only` in CLI help and used it to recover a lost
edit receipt. Each saved the compact receipt, delivered the correct preview and
retried the original move after undo. The independent judge reopened the saved
artwork and replayed the request on a copy. The restored document stayed at
revision 2. All six checks passed in each trial. [CLI receipt format](AGENT_RESPONSES.md)

| Five Windows trials per build | Accepted artifacts | Complete workflows | Median input + output tokens | Median client seconds |
| --- | ---: | ---: | ---: | ---: |
| [Earlier batch at 447bbc2](#b10b17b19-at-447bbc2-request-guidance-follow-up) | 5/5 | 4/5 | 194,428 | 76.4 |
| Result-only option at c3fd51f | 5/5 | 5/5 | 222,485 | 87.2 |

In the earlier batch, one agent saved the CLI envelope as the receipt. No agent
made that error in the new batch. Each initially requested a receipt without
selecting the workspace and received a missing-`session_root` error. Median
token use rose 14.4%. Keep the option for callers saving receipts and continue
tracking the cost of finding the workspace.

Both batches used the same prompt, fixtures, B17 judge, client executable
(Codex CLI 0.160.0) and externally selected model (`gpt-6.1-sol`, medium).
The new attempts ran sequentially on a shared Windows host with the core MCP
catalog available. All five chose the CLI. The different source revisions and
small samples limit attribution. B17 exercises an engine-specific recovery
contract. Engine calls, retries, wire bytes, time to first verified preview,
engine-only memory and underlying model-call counts remain unmeasured.
[Recovery task](../tools/benchmark_prompts/B17.md)

The harness confirmed stable inputs. A second read verified the recorded
workspace files, setup evidence, requests, client results and transcripts for
all ten attempts. The current report SHA-256 is
`078e04c0a1475f5c6e81e652bd7aec4bea972881fa39471aba19147393172d61`.
The tested release executable is
`1e482847bc23bed84d9eaba719184605957e0b37d45b6d8bf036d0a16e45035c`.

## B02 at c7d9f30: initial five matched icon-sheet trials

Both arms passed all five B02 artifact trials. Inkbolt's median reported
input-plus-output usage was **8.60 times** the baseline's, and median client
execution took **159.0 seconds versus 49.7 seconds**. This is a task-specific
prioritization signal under the fixed [comparison policy](BENCHMARK_COMPARISON.md),
not full-suite acceptance or a finding of statistical equivalence.

### Conditions and scope

These ten genuine trials used commit
`c7d9f30769d6be3a1aff2ad88c7cb87a21668733` on the same Windows 10.0.26200
x86-64 host with a Ryzen 9 7950X3D and 32 logical CPUs. The source candidate,
prompt, checks, client, model and settings stayed unchanged throughout. The
five Inkbolt trials ran first, followed by the five baseline trials, sequentially
on a shared development host with no concurrent local engine verification or
benchmarks. OS caches could be warm; execution order was not randomized.

The externally configured client was Codex CLI 0.160.0, with model
`gpt-6.1-sol` and `reasoning_effort: medium` in both arms. These names record this
evaluation; Inkbolt and the harness have no model default, allowlist or fallback.
See the [configurable client adapter](BENCHMARK_CODEX.md).

[B02's original synthetic task](../tools/benchmark_prompts/B02.md) asks for three
aligned rectangular icons, three independent artboard exports, prescribed exact
pixels and editable source. It measures a small structured authoring workflow,
not artistic quality. The baseline used pinned resvg 0.47.0 and Pillow 12.3.0
through an external Python 3.11 environment. Its editable delivery was SVG;
the Inkbolt arm also had to provide a valid native snapshot. Independent judges
checked the delivered files. No prompt or judge changed between these arms.

### Outcomes

| Measurement | Inkbolt arm | No-Inkbolt baseline |
| --- | ---: | ---: |
| Retained attempts | 5 | 5 |
| Artifact success | 5/5 | 5/5 |
| Complete applicable workflow | 5/5 | 5/5 |
| Native editable-source check | 5/5 | Not applicable |
| 95% Wilson interval for artifact success | 56.6%-100% | 56.6%-100% |
| Median input + output tokens | 487,207 | 56,624 |
| Input + output token range | 374,064-568,364 | 43,367-71,575 |
| Median client execution, seconds | 159.0 | 49.7 |
| Client execution range, seconds | 132.0-169.5 | 45.2-52.6 |
| Median cached input tokens, reported separately | 428,544 | 39,424 |

All ten attempts remain in the denominators. Token and execution-time observations
exist for every attempt. Input totals include cached context; cached-input and
reasoning counts are not added again. The token ratio is **not a billing ratio**.
Client execution includes startup and tool work; it is not engine-only latency.
Underlying model-call counts, complete engine-call/traffic counts, retries and
time to first verified preview remain unknown. Client-tree memory was observed
separately and does not establish engine-only memory performance.

The fixed policy flags both the artifact-success tie and the greater-than-2x
token ratio. Five trials give a wide success interval and cannot establish
equivalence, general model performance or a cause for the difference. Earlier
one-pair pilots, including the smaller-model failure, remain separate retained
evidence and are excluded from these five-pair aggregates.

### What changes next

The recorded commands show all five Inkbolt trials using CLI discovery, with
5-10 shell events containing schema lookups per trial and an unsuccessful CLI
help attempt in each. Those events are not underlying model-call counts. A
separate probe of the same executable confirms that neither `inkbolt_schema_lookup`
nor `inkbolt_run` appears on the first eight-tool compact MCP page. This suggests
an entry-point discovery problem; it does not prove that the client ignored
pagination or that pagination caused the token difference. Baseline commands
used the supplied image tools. Transcript review found no repository/judge reads,
other model use or prohibited engine use in these ten trials.

Prioritize a bounded W5.2 change that makes schema lookup and the general command
dispatcher visible on the first compact page. Preserve the catalog byte ceiling,
complete tool inventory and execution semantics. Then repeat five matched B02
trials per arm with the same client/model/settings and unchanged task/checks.
The expected benefit is fewer discovery workarounds and lower context usage,
while retaining 5/5 artifact and applicable workflow success. If discovery and
usage do not improve, reassess this hypothesis before expanding that workstream.

The other nineteen task IDs, further smaller-model trials and matched sister-engine
comparisons remain open. `actual_model_benchmark_complete`,
`matched_model_baseline_complete`, `decision_ready` and
`matched_cutbolt_comparison` are all false. No engine checkpoint credit changes.

### Evidence identities

Raw transcripts, original workspaces, per-trial results and full aggregate reports
remain external. These SHA-256 identities bind the published summary to them:

| Evidence | SHA-256 |
| --- | --- |
| Source candidate | `abdfa023c342ea73d4cd9c0b39e2806e54ba5624099559dfcdd3045b5fdcf413` |
| Inkbolt release executable | `cb5bc72591bf60ada097a698dc2835bbd70ca54ae12a9b09a4f109c153d453af` |
| Shared B02 prompt | `0911714f1c4f869bdf33ebebd9eb7d207e9ceea7c11a88046a7e18ddfbe6f67e` |
| Fixed comparison policy | `17355cd7d79018d710679efbaae7a91964b701a34be601c6eca4cceab2d2212c` |
| Inkbolt-arm report | `8cea5964bc2190d285695ea00240c0afe9994517fadab10fecf99054fbc1f20d` |
| Baseline-arm report | `1628ac44fc37b36d33f06e62c4257192d624aa5a15fa4c2b65d6d2ee6b4195de` |
| Matched comparison report | `2005145ec9ff99fab67619fa2408ebe1aaf5a77ccc78d48d7c0e00f2f4980a29` |
| First-page runtime probe | `1f08a9ebcfd082a1d748a5869747d8017bad827c1306f06a4467b7c1e7425849` |

## B02 at 9909329: first-page discovery follow-up

Commit `9909329f034b5458d984a96be4309445b2cac6a4` exposes schema lookup and
the general dispatcher on the first compact page. Five new genuine trials per
arm used the same external client/model/settings, prompt, judges and pinned
baseline tools as the initial evaluation. Both arms used the unchanged candidate
below, on the same host, sequentially with Inkbolt first and baseline second.
There were no concurrent local engine tests or benchmarks; OS caches could be
warm. The two evaluations were separate runs, not randomized paired observations
of the old and new engine revisions.

| Measurement | Inkbolt arm | No-Inkbolt baseline |
| --- | ---: | ---: |
| Retained attempts | 5 | 5 |
| Artifact success | 5/5 | 5/5 |
| Complete applicable workflow | 5/5 | 5/5 |
| Native editable-source check | 5/5 | Not applicable |
| 95% Wilson interval for artifact success | 56.6%-100% | 56.6%-100% |
| Median input + output tokens | 564,296 | 41,249 |
| Input + output token range | 420,520-636,076 | 40,913-56,432 |
| Median client execution, seconds | 123.0 | 42.4 |
| Client execution range, seconds | 97.3-135.9 | 38.1-49.4 |

Every attempt passed, with observed usage and execution time. The fixed policy
again flags the artifact tie and excessive token usage: **13.68x** the baseline
median. Inkbolt's token median increased from 487,207 to 564,296. Its execution
median decreased from 159.0 to 123.0 seconds, but this small sequential sample
does not isolate the cause or establish a general speed improvement. The same
unknown metrics and billing/memory limitations stated above apply. Full-suite,
matched-baseline and sister-comparison completion gates remain false.

All five Inkbolt trials now used MCP, with 15-21 recorded MCP call items each,
and all still used the CLI. Every trial received an invalid-operation response
after attempting a document-wide item index in the sibling-stack reorder
operation. In addition, every trial's dispatcher publication attempt was refused
by the evaluation client because tool approval was required while its unattended
approval policy was `never`: nine such refusals across five trials. These are
client refusals before engine execution, not nine failed engine publications.
Recorded MCP items are not underlying model-call counts or a complete count of
engine calls across both transports. Transcript review found only the supplied
engine/image tools and task/workspace reads, with no repository/judge reads.

The first-page change made the entry points usable for discovery, but the
predeclared token target was not met. Keep the result and stop broader interface
expansion pending a focused check of the evaluation client's explicit approval
configuration for the supplied local engine. Verify that configuration in one
pilot before another five-pair run; keep model/settings external, both arms
matched, sandboxing enabled and engine tool-effect annotations truthful. The
documented [client configuration interface](https://learn.chatgpt.com/docs/config-file/config-reference)
provides server/tool approval settings. The item-ordering errors are a separate
candidate for focused guidance after the client setup is verified.

These additional SHA-256 identities bind the follow-up evidence; its raw
captures remain separate from the initial runs:

| Evidence | SHA-256 |
| --- | --- |
| Source candidate | `5e57d183bcaa3a6d16856980590db43643f60374cf361b3190e6981b3b628edb` |
| Inkbolt release executable | `40a3c7f88ef8aa50d96a468494173287ffa864bddb5705fccc4ab9485f17562f` |
| Inkbolt-arm report | `c432074c3e97dce7fc01cf61440ad7c7b4a78a035c2b9e125901673231f13406` |
| Baseline-arm report | `2438ddeb8d7b16f87f277b0260d8c5f62119c742b104aa05d2350d346a98a6c5` |
| Matched comparison report | `ab880b37dad6e63835ec9ff5d561d90658547c6b2a4665a6d3c7c35dabd62b4f` |

## B02 client approval configuration pilot

One subsequent genuine trial used the same client/model/settings and unchanged
B02 prompt/checks, with the externally selected `--mcp-approval-mode approve`
option described in the [driver contract](BENCHMARK_CODEX.md). The engine binary
was unchanged from the first-page experiment. This pilot passed all artifact and
native-source checks, including source preservation. Its transcript records four
successful `inkbolt_run` publication calls for the snapshot and three PNGs, with
zero client approval refusals. Shell commands inspected local files/pixels and
attempted CLI discovery; they did not publish the outputs. The sibling-stack
reorder error still occurred.

The client reported 436,301 input tokens and 2,073 output tokens, with 360,320
cached input tokens tracked separately, and 103.6 seconds of agent execution.
This is one setup pilot without a paired baseline, not an efficiency comparison
or part of either five-pair aggregate. The shell sandbox, prompt, model/settings
and engine effect annotations were preserved; the external config and exact
client argument array record the server policy. Future matched trials must use
the same external config in both arms. All full-suite completion gates remain open.

| Evidence | SHA-256 |
| --- | --- |
| Tested/pilot source candidate | `bdffa598686967936c79c57e1297068e31f04422e72c757cd7b455e9d4877aa6` |
| Pilot report | `d0975df5a530a5045d94fadf793c9849c11a75edd1682ecbd2d054976c7fdafb` |
| Client transcript | `e3daf8ac7812efe4e3cb0300a62ee05c1a114f4fa42726f016fc76fed47f27d3` |
| External client configuration | `7210961872baca5a7afc9f8668aa935135d311ad9beb83156563c0e633c0cf02` |

## B02 at 8586e82: CLI-help and sibling-index guidance

Five new pairs used commit `8586e82ade30069fb2eabe6e13a112ec549e12a5`, the same
Windows host, Codex CLI 0.160.0, externally selected `gpt-6.1-sol` with medium
reasoning, unchanged B02 prompt/checks, and the same pinned baseline tools as
above. Both arms used the pilot-verified external configuration with explicit
MCP approval. The five Inkbolt runs preceded the five baseline runs; execution
was sequential, not randomized, on the shared host with no concurrent local
engine verification or benchmarks. OS caches could be warm. Candidate identity
remained unchanged, and the comparison found no evidence-matching issues.

| Measurement | Inkbolt arm | No-Inkbolt baseline |
| --- | ---: | ---: |
| Artifact success / retained attempts | 5/5 | 5/5 |
| Complete applicable workflow | 5/5 | 5/5 |
| Native editable-source check | 5/5 | Not applicable |
| 95% Wilson interval for artifact success | 56.6%-100% | 56.6%-100% |
| Median input + output tokens | 313,114 | 57,582 |
| Input + output token range | 274,123-394,769 | 56,782-70,869 |
| Median client execution, seconds | 112.8 | 46.6 |
| Client execution range, seconds | 99.9-129.7 | 40.0-54.6 |
| Median cached input tokens, reported separately | 253,312 | 35,328 |

The 5.44x token ratio still triggers the fixed cost signal. Inkbolt's observed
median was 44.5% below the previous five-run median of 564,296, but the engine
guidance, client approval configuration and execution paths differed across
batches. This small sequential sample does not isolate causes or establish
general performance, equivalence or billing savings. Cached context is included
in input totals and is not added twice. Model-call counts, complete engine
traffic/retries and first verified preview time remain unknown.

All five Inkbolt traces successfully used `--help`, looked up the `reorder`
operation, and avoided the previous sibling-reorder failure. They used 10-13
completed shell items each and no MCP calls. Thus zero approval refusals in this
batch do not measure the server policy's effect; the separate MCP pilot remains
the evidence for that setting. The agents arranged the required flat snapshot
item order explicitly before engine validation/publication. One trial attempted
an invalid global insertion index and repaired it; schema-selector and output-option
errors also remain in the captures. No prompt, judge or insertion/reorder semantics
were changed to improve the scores.

Transcript and generated-script review found only the supplied engine/image
tools, workspace inputs/outputs and owned temporary files. No repository/judge
reads, additional model use or baseline engine access were observed. All ten
attempts remain retained. These observations count client items, not underlying
model or engine calls.

The next work is broader B01/B03 and smaller-model evaluation before further
B02-specific tuning. The insertion-index and schema-discovery gaps remain
recorded, while larger W3c/W4/W5.2+/W6 priorities await evidence across tasks.
The other nineteen tasks, Linux scale evidence and sister-engine comparison
remain open. All four full-suite completion gates remain false; no checkpoint
credit or full W2/W5.2 milestone completion follows from these results.

The complete captures, reports and comparison remain outside the repository
under `w5-cli-guidance-b02-`; reviewed trace counts and final candidate hashes
are retained alongside them. The same configuration hash as the pilot above
applies to both arms.

| Evidence | SHA-256 |
| --- | --- |
| Source candidate | `cd888dde1f5765d78fee3bdac3512f56e9202ffe269608253ae47b3a82d15b27` |
| Inkbolt release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| Inkbolt-arm report | `1c1697dcd26aaccb6e760fe165f2adbb3c8940941e072e9bc1a6ac6f6f7b353b` |
| Baseline-arm report | `96c016d9bea5c7153f23ab74fb9c454f93b2df90056159c401155416f9812e1c` |
| Matched comparison report | `085294024818692b92f53dbc537925f5b583fcf5c6014310c89b99efbe752fbc` |

## B01/B03 breadth pilots and capture rejudgment

Single-attempt pilots broadened coverage to labelled diagrams (B01) and a
5,000-object edit with saved history (B03). Codex CLI 0.160.0 used externally
configured `gpt-6.1-sol` and `gpt-6-luna`, each with medium reasoning and the
explicit MCP approval option. Each model used the same configuration in its two
arms. No model is built into the harness, engine or acceptance criteria.
The pinned baseline tools and release executable match the preceding B02 batch.
Runs were sequential on the shared Windows development host; OS caches could
be warm. Each model's Inkbolt arm preceded its baseline arm. They were not
randomized, and the two model configurations are separate pilot samples.

| External model | Task | Inkbolt / baseline outcome | Input + output tokens, Inkbolt / baseline | Client seconds, Inkbolt / baseline |
| --- | --- | --- | ---: | ---: |
| gpt-6.1-sol | B01 | Pass / fail | 363,329 / 57,926 | 104.2 / 41.7 |
| gpt-6.1-sol | B03 | Pass / pass | 379,095 / 67,137 | 149.9 / 38.3 |
| gpt-6-luna | B01 | Pass / fail | 698,196 / 64,542 | 133.5 / 23.8 |
| gpt-6-luna | B03 | Pass / pass | 575,269 / 66,564 | 104.2 / 31.8 |

Outcomes above use corrected judges on the original captured bytes. Sol's B01
initially failed because the judge assumed the default font store. Luna's B03
initially failed because the judge assumed the default session store. Neither
prompt prescribes those store names. The corrected judges locate retained
resources inside the capture and still verify exact font/license identities,
editable content, all pixels and, for B03, exact original/current snapshots and
full history integrity. Missing, linked or corrupt font/license copies fail;
missing, linked, ambiguous or corrupt session stores also fail. Regression tests cover nondefault stores and
capture relocation; [verification evidence](DEVELOPMENT_STATUS.md) records the
focused Windows/Linux results. Artifact and engine requirements did not change.

Both B01 baseline failures remain. Sol delivered a `defs/style` font embedding
outside the prompt's bounded editable SVG contract. Luna's text placement
differed from the required frame positions; its renderer invocation also omitted
the supplied font. Neither failure was relaxed or retried. Both B03 baselines
passed shared artifact checks; saved history is explicitly not applicable there.

All eight transcripts and generated command/script bodies were reviewed.
Observed tools and reads stayed within the supplied engine/image tools and
workspace material; no repository/judge reads, additional model calls or baseline
engine access were observed. All Inkbolt trials used CLI execution and no MCP
calls. Shell/schema, relative-path and output-option errors remain in the raw
traces. Rejudgment preserved transcript and workspace hashes, token usage and
original client durations; it did not rerun the models or replace original
reports. Judge execution is separate from client execution.

These are pilots, not five-repetition acceptance or evidence of relative
reliability/efficiency. Input totals include cached context; cached tokens are
reported separately in the raw rows and are not added again. Model-call counts,
complete engine traffic/retries, first verified preview and engine-only memory
remain unknown. Neither comparison has matching issues for B01/B03, but both
retain false minimum-repetition and full-suite completion gates. Complete the
required repetitions and broader task coverage before further priority changes.

Original captures remain under `w2-breadth-*-pilot-01`; new reports are under
`w2-breadth-*-rejudged-02` and `w2-breadth-*-comparison-pilot-02`. The trace review
is retained separately. Sol's original candidate was
`7bac198d1f816e4907c55c1fb54a4f138839313b17efa3abc747d48fa40fa6a5`;
Luna's was `8f25bdc287d0cbc5c87609146bd58f027dc669f4cc12c9139d76a886d3e89041`.
Both used the unchanged release executable identified in the preceding table.

| Rejudged evidence | SHA-256 |
| --- | --- |
| Shared tested/judged source candidate | `115d0ecb4e8a4f3110df3936fe8c29db48cc8dd5e8fae9c171f614cd1af2f46b` |
| Sol Inkbolt report | `6b996520eac294d80e9631e722dbcb532aacd3b8e241cf436cc2c9f2ca6a72fa` |
| Sol baseline report | `c4ce824949269a14126824c3c17d8289652784a6cb43682c1bc16f723a3c22b0` |
| Sol comparison | `83dcb595c1332c8d844cfa6b5e90ef1dd31a5fed45556846786cedefcf7bc828` |
| Luna Inkbolt report | `c891df9bfde9e83f21b8b662199547bc6c1baab2c13d32f36fda11dd08f029f1` |
| Luna baseline report | `42866663ce11e65a86288c69291091e76971a2ce484c2f45a957f719f7caeac7` |
| Luna comparison | `b1c8002ea52f7aa66dce5bc3567159f75cb1221d9e7097672e8d604252c3a35f` |
| Sol external configuration | `7210961872baca5a7afc9f8668aa935135d311ad9beb83156563c0e633c0cf02` |
| Luna external configuration | `6b34578c04ebb0bb7597d48820f9e58720a0ecef42fa2b27e2145d40472320c3` |

## B01/B03 at 8bc8982: five matched pairs

Five new repetitions per task and arm used Codex CLI 0.160.0, externally selected
`gpt-6.1-sol` with medium reasoning, and the same explicit MCP approval option.
The engine and pinned baseline tools match the preceding pilots. Model choice
remains external; these names identify this evaluation only. The Inkbolt arm
preceded the baseline on the shared Windows host. No other Inkbolt verification
or benchmark ran concurrently in this chat; other host workloads were
uncontrolled and OS caches could be warm. Task order rotated by repetition.
Neither arm changed its source inputs, and both selected tasks have five matched
pairs with no global or task matching issues.

| Task | Inkbolt / baseline artifact passes | Median input + output tokens | Median client seconds |
| --- | --- | ---: | ---: |
| B01 diagram | 5/5 / 0/5 | 299,232 / 71,327 | 95.9 / 45.7 |
| B03 5,000-object edit | 5/5 / 5/5 | 349,212 / 65,011 | 128.9 / 41.8 |

Medians include all attempts, including B01 baseline failures. B03 triggers the
existing signal: matching shared artifact success and **5.37x** median observed
token use with Inkbolt. Every Inkbolt B03 trial also passed saved-revision and
history checks, which are not applicable to the baseline. Five equal artifact
outcomes do not prove equivalence or isolate the cost of those extra semantics.
The broader decision and full-suite gates remain false.

All five B01 baselines embedded the supplied font in a CSS `style` element,
usually inside `defs`, beyond the judge's supported source subset. They also
included frame metadata attributes outside that subset. Admission stopped the
original judge before pixel checks; the failures were retained without retries.
A separate post-hoc check of the unchanged delivered PNG bytes against the
existing independent pixel oracle passed all five images. It did not re-render
SVG, validate source/font semantics or convert task failures to passes. B01's
font-retention wording and bounded source contract need review before using
these failures as general reliability evidence. There is no successful-pair
token-cost signal for B01 and no demonstrated rendering advantage from this batch.

All twenty transcripts, command bodies and generated scripts were reviewed.
No repository/judge reads, additional engines/models or baseline Inkbolt access
were observed. Two Inkbolt attempts mixed MCP with shell calls: B01 repetition
one used 21 MCP items and B03 repetition five used 27; the other eight used CLI
only. Invalid schema selectors, relative resource paths and publication options
remain in the traces. Shell-item counts do not measure complete engine calls,
errors or retries. Input totals include cached context without adding cached or
reasoning tokens twice. Billing, model-call counts, full engine traffic/retries,
first verified preview and engine-only memory remain unknown.

The next work is broader B04/B05 evidence; the palette judge's unprescribed
default-store assumption now has a focused Windows/WSL correction. B03 reinforces the need to reduce
discovery overhead, while the full task matrix must still guide substantial
W3c/W4/W5.2+/W6 ordering. This batch does not complete W2 or change checkpoints.

External evidence is retained under `w2-breadth-sol-{model,baseline}-five-01`
and `w2-breadth-sol-comparison-five-01`, with separate trace reviews and
`w2-breadth-sol-b01-supplemental-pixels-01.json`.

| Evidence | SHA-256 |
| --- | --- |
| Shared source candidate | `5de6a49ce7e146936c0f7f9b04960c9200a9ca23744d157bb6c8eda9d68d4812` |
| Inkbolt report | `abf3044104010b5fc36043eb4c5edf1b8df03878da86d55539a86bb76fd920f2` |
| Baseline report | `632a0f5dda0a8de1f951f1d415b94978c546674bf0d8b2010a4a09b835982a85` |
| Matched comparison | `a3ef9a766ea7ecb721f77dbc871ab651ae4ddf9e631b06a7ee751d0e3ea5949d` |

### B01 source rendering check

The five original baseline SVGs each contain the exact supplied TrueType bytes
in a font-face declaration. All retain two editable text labels, three
rectangles and the requested frame coordinates. The supplied font and license
beside each SVG also match the input hashes.

The pinned resvg 0.47.0 freshly rendered each original SVG with system fonts
disabled and the supplied typeface loaded. Every RGBA sample in all five
128 × 56 renders matched the original diagram oracle, as did the five delivered
PNGs. The five version-2 workflow failures remain in the table under their
original source-format contract. The report SHA-256 is
`e58a0060f8c86e377258251f72dd5c4c8ae9a42ea7cba0211e5e26fc776713f4`.

Version 3 of the [diagram prompt](../tools/benchmark_prompts/B01.md) specifies
how to deliver the supplied font beside the SVG and position the labels with
standard SVG attributes. The follow-up kept the fixtures and judges fixed and
specified five fresh attempts per arm before collecting results.

## B01 at c5d9e13 font delivery

Both arms delivered the requested 128 × 56 diagram in all five attempts.
Every delivery passed the structure, font identity, pixel and source-preservation
checks. All five Inkbolt snapshots passed the native editability check. Each
baseline SVG retained the labels as text and shipped with the original font
and license.

| Measurement | Inkbolt | No-engine baseline |
| --- | ---: | ---: |
| Accepted artifacts and complete applicable workflows | 5/5 | 5/5 |
| Median input + output tokens | 284,237 | 42,600 |
| Token range, all attempts | 235,654–304,518 | 42,447–72,617 |
| Median client execution, seconds | 54.0 | 28.0 |

Three Inkbolt attempts created and published the diagram through the CLI.
The other two used MCP for that work. Of their 21 and 20 recorded MCP calls,
16 and 15 respectively were schema lookups. Each also imported the font,
created a session, checked the document and published the snapshot and PNG.
All five baseline attempts used the pinned renderer. For this task, the
remaining measurable gap is the work required to discover and express the
same diagram. The captures support measuring discovery calls in a follow-up.
They do not isolate the share of token usage attributable to those calls.

The baseline ran first on the shared Windows host. Both arms used Codex CLI
0.160.0, externally selected `gpt-6.1-sol` with medium reasoning, the same
prompt, fixtures and 600-second limit. The baseline used resvg 0.47.0 and
Pillow 12.3.0. Each of the five pairs matched on fixture bytes, prompt and
host. The diagram and baseline judges were unchanged from `8bc8982`. All
ten attempts reported token usage and elapsed time. The ratio of median token
counts was 6.67. Model-call counts and time to first verified preview remain
unknown. Five successes give a 95% Wilson interval of 56.6%–100% in each arm.

| Retained evidence | SHA-256 |
| --- | --- |
| Shared source fingerprint | `3e9c8fb47c724c4377d1c9b7d5b8044530b2b57959a26e03f1591ab602f435d8` |
| Evaluated Windows executable | `a65136303002bffec6a55e966c89036b517cd70113539ec0586fc670b10be5d6` |
| Inkbolt report | `0d6a54abb772c43eeb14566f87977ecb4b4316e1a7dd0310a4f39b78d8eef47b` |
| Baseline report | `092c1d3dba59cc11edcef4cdfc0b59dc43f899ee4adf44fb2ca6dd07c68e6d5f` |
| Matched comparison | `78c983039b7f6d64b96e4cf0121a63ca190358db504d464620854c6ea4e849d8` |

### B01 with Luna

With `gpt-6-luna`, all five Inkbolt attempts delivered the correct PNG and
three passed the full diagram task. Two of five no-engine attempts passed.
These ten fresh attempts used the same Windows host, source commit, binary,
prompt, judges, Codex CLI 0.160.0, medium reasoning and baseline-first order
as the Sol batch above. Model selection came from the external evaluation
configuration. The source and PNG each had to pass their own checks.

| Measurement | Inkbolt | No-engine baseline |
| --- | ---: | ---: |
| Accepted artifacts and complete workflows | 3/5 | 2/5 |
| Delivered PNGs matching all 7,168 expected pixels | 5/5 | 2/5 |
| Median input + output tokens across all attempts | 387,552 | 66,828 |
| Median client execution, seconds | 83.2 | 26.8 |

One Inkbolt attempt saved the CLI response envelope as `editable.json`, which
the engine could not reopen as a document. Another delivered the five requested
shapes and labels inside one SVG import group. The judge counted the group as
a sixth object. We checked each child separately on copies of that snapshot.
Removing each one left the other four intact, and every rendered pixel matched
the expected drawing for all five edits. The recorded score retains the
original item-count failure.

All five baseline SVGs rendered correctly when the judge loaded the supplied
font. Three attempts omitted the font file from their own rasterizer command.
Each delivered PNG differed from the reference at 424 pixels. The repeated
Sol batch above passed five times per arm. Only one Luna pair succeeded in
both arms, so the comparison policy reports no paired token-cost ratio.

The model and baseline reports have SHA-256
`a11757b63af7862b08727a6d8c449c85752fe594595a5165f7fa3850988f230e` and
`01e93fbdbc8071659fd87ea3496af9c2475c12a9df7ce28868396d1e4278b070`.
The matched comparison has SHA-256
`0a43bd67ada83cdcefd04cf194c14218b70b97903bb234b6f6cf4884feebbbf6`.
The five independent child-edit checks have SHA-256
`279c4e8c345dc78b06816c385412638e5e535498e0edc6a9efd68bec67221f75`.

The corrected B01 judge counts drawing objects inside groups and checks their
positions after applying parent transforms. We rejudged all twenty saved
deliveries from these Sol and Luna comparisons with the original engine
executable, renderer, fonts and transcripts. The grouped Luna drawing was
the only result that changed. Luna scored **4/5 with Inkbolt and 2/5 with the
baseline** on rejudgment. The malformed snapshot still failed. Sol retained
5/5 in both arms. The original reports and token counts are preserved. The
capture rejudgment report SHA-256 is
`9607e0f93360ddd474f478a337fa97961941fb195a8b9ad371f0240d61ef870d`.

### Testing a snapshot publication example with Luna

At [`3fdf09d`](https://github.com/skulitom/Inkbolt/commit/3fdf09d), a
`document.publish` lookup returned a complete request to save an editable
snapshot. The `session.create` example also explained how to pass a saved
revision to that command. Five new attempts per arm used the preceding Luna
configuration, task, judges and run order. The engine returned the publication
example in four attempts and the guidance about saved revisions in all five.

| Measurement | Earlier Inkbolt | New Inkbolt | Earlier baseline | New baseline |
| --- | ---: | ---: | ---: | ---: |
| Complete tasks | 3/5 | 1/5 | 2/5 | 1/5 |
| Exact delivered PNGs | 5/5 | 3/5 | 2/5 | 1/5 |
| Editable JSON files that reopened | 4/5 | 4/5 | n/a | n/a |
| Median input + output tokens | 387,552 | 684,904 | 66,828 | 64,423 |
| Median completed shell commands | 13 | 21 | 3 | 3 |
| Median client seconds | 83.2 | 116.3 | 26.8 | 25.9 |

The new attempts saved zero CLI envelopes. One produced no editable JSON and
another saved an empty session. Two used glyph baselines to place the labels
correctly in the PNG. Their text items had identity transforms, so they failed
the requested frame-position check. Four baseline
attempts omitted the supplied font from the preview command. All attempts
used the shell, so a shell-command count can include multiple engine calls.

The example passed all 278 source checks on Windows and WSL2. It did not
increase the number of snapshots that reopened. Median shell-command and token
counts increased for Inkbolt. Five attempts per arm leave the cause uncertain.
We removed the extra text from automatic discovery and kept the
[tested publication request](../examples/publish-snapshot.json) in the
workspace guide.

The Inkbolt and baseline reports have SHA-256
`a030bcdabda81010287361a6eac743c2dab86ec91ee7e30cdd281c3b12da55c2` and
`a9913944a7bc12af1406476fabda203b806066ec1f4a7202f90fd7add19e630f`.
The matched report has SHA-256
`cebc61a059df976d5117568424c4a9fca9dffee99fede67b76f23d724fe77ae9`.
The separate audit reopened the saved files from both batches, checked the
PNG pixels and verified the captures stayed unchanged. Its SHA-256 is
`edb82375137220719c5fbc246fb50485fda180afcd5b858b98e9ff68967050a2`.

## B04/B05 at dabe447: five matched pairs

Five fresh repetitions per task and arm used the same external Codex CLI
0.160.0 configuration (`gpt-6.1-sol`, medium reasoning, explicit MCP approval
option) as the preceding batch. These are evaluation metadata, not model
defaults. The engine and pinned baseline tools were unchanged. The Inkbolt arm
preceded the baseline on the shared Windows host; task order rotated within
each arm. No other Inkbolt verification or benchmark ran in this chat, other
host workloads were uncontrolled, and OS caches could be warm. Both source
candidates stayed unchanged; both tasks have five matched pairs and no matching
issues. Every attempt and its original transcript remains retained.

| Task | Inkbolt / baseline artifact passes | Median input + output tokens | Median client seconds |
| --- | --- | ---: | ---: |
| B04 SVG import/edit | 5/5 / 5/5 | 206,924 / 57,528 | 71.2 / 56.7 |
| B05 shared palette | 5/5 / 5/5 | 270,958 / 54,973 | 93.8 / 35.6 |

Both tasks trigger the existing cost signal: baseline artifact success matches
Inkbolt, whose median observed token totals are **3.60x** and **4.93x** those of
the baseline, respectively. All Inkbolt-only native-source and palette live-reference/history
checks passed; these are explicitly not applicable in the baseline. Five equal
outcomes do not prove equivalence, and this comparison does not isolate the cost
of those additional guarantees. Cached input is included in input totals, never
added twice. These ratios are not billing or causal performance estimates.

Every B04 baseline retained the original SVG IDs and description. Every Inkbolt
B04 delivery remapped IDs and omitted the description, with exact losses openly
reported and judged. All retained the requested editable path and passed pixel
checks. Every B05 Inkbolt attempt chose a nondefault session directory; the
corrected judge found and verified its original/current snapshots and history.

All twenty traces and generated command/script bodies were reviewed. No
repository/judge reads, extra models/engines or baseline Inkbolt access were
observed. All Inkbolt attempts chose CLI execution; this batch does not measure
MCP approval behavior. Invalid schema selectors, full-schema fallbacks, a JSON
property-order comparison false alarm and a mistaken historical publication
request remain in the traces and usage. Some agents also retained extra local
copies of the task prompt. Complete model-call/engine-call counts, traffic,
retries, first verified preview and engine-only memory remain unknown; completed
shell items are not substituted for these metrics.

This extends the fewer-interactions signal beyond B02/B03 into input admission
and palette authoring. Continue the remaining tasks before making a substantial
W3c/W4/W5.2+/W6 choice from the full decision rule. B06/B07 are next after their
audited resource-location assumptions are corrected and checked. Full-suite,
matched sister-project and readiness gates remain open; checkpoints are unchanged.

Reports/workspaces are retained under `w2-svg-palette-sol-{model,baseline}-five-01`
and `w2-svg-palette-sol-comparison-five-01`, with separate trace review files.

| Evidence | SHA-256 |
| --- | --- |
| Shared source candidate | `cddc5b424cf3f1154733069dc615c302621a8da7311ef21aa32f316460eeca3f` |
| Inkbolt report | `13bc20d7fc032c105037cf4b715a83034380575481372997f0a60b630343ff36` |
| Baseline report | `ef6a6603aac9534468539d097c072aeb79e027faeaf70d1638c8fe2e2fdf9e74` |
| Matched comparison | `006c77ecd151342ec6af21579bc8200b5277fb2cd8e79981fa0fcffad48be9e6` |

## B06/B07 at a7e034e: captured trials rejudged

Five new repetitions per task and arm used the same external Codex CLI 0.160.0
configuration (`gpt-6.1-sol`, medium reasoning, explicit MCP approval option).
These identify the evaluation only; the engine and harness have no model default.
The unchanged release executable and pinned baseline tools match the preceding
batch. Inkbolt ran before the baseline on the shared Windows host, with task
order rotated by repetition. This chat scheduled no concurrent Inkbolt checks
or benchmarks; other host workloads were uncontrolled and OS caches could be
warm. Both original and rejudged source candidates stayed unchanged. Both tasks
have five matched pairs with no global or task matching issues.

| Task | Inkbolt / baseline artifact passes | Median input + output tokens | Median client seconds |
| --- | --- | ---: | ---: |
| B06 linked text flow | 5/5 / 5/5 | 337,131 / 76,580 | 113.8 / 53.5 |
| B07 multilingual typography | 5/5 / 0/5 | 405,058 / 218,798 | 111.8 / 148.3 |

B06 triggers the existing cost signal: matching shared artifact success at
**4.40x** median observed token use with Inkbolt. Its saved historical-flow and
history checks also passed; those engine-only checks do not apply to the baseline.
Five equal outcomes do not prove equivalence or isolate the cost of those extra
guarantees. Medians include failed attempts. B07 has no successful-pair cost
signal because its baseline mapping checks failed.

Every B07 image passed the delivered and independent fresh-render pixel checks
in both arms. All five Inkbolt attempts originally failed only the engine's
snapshot judge: the model explicitly selected a fixed baseline of 200, while
the reference omitted that setting and obtained the same position from ascent.
Prompt version 1 prescribes positions, not a storage representation. A focused
Windows/WSL correction admits explicit controls while keeping independent
glyph/cluster positions and pixel checks; a one-pixel shift still fails. Rejudging
the existing captures changed only those five snapshot checks. All ten Inkbolt
attempts now pass their complete workflows. The original failures remain in
their original reports; no model was rerun and no attempt was added or discarded.

All five baseline B07 failures remain. Each mapping lists a Hebrew base glyph
before its zero-advance mark within the shared scalar interval [2,4); the fixed
oracle lists the mark first. The entries, glyph IDs, source intervals, origins
and advances otherwise match. Both arms rendered this sheet correctly.

Independent shaping of the same font resolved the sequence question.
HarfBuzz 8.3.0 on Windows and 2.7.4 on Linux shaped the Hebrew run
right-to-left and emitted glyphs 18, 6, 17. The mark (6) and base (17)
share the same source interval. Their positioned frame origins are (380, 50)
and (320, 200), respectively. Sorting by x therefore reverses the pair.
Prompt version 2 asks both arms for the shaped sequence and the positioned
origins separately. The authored glyph records and full-image checks are
unchanged.

All twenty transcripts and generated command/script bodies were reviewed. No
repository/judge reads, extra engines/models or baseline Inkbolt access were
observed. B07 Inkbolt repetitions two and four used 37 and 40 MCP items plus
five and three shell items respectively; the other eight used CLI only. Invalid
schema selectors, relative paths, image-option errors, JSON comparison false
alarms and Windows text-encoding errors remain in the traces and usage. This
batch does not isolate MCP's effect. Cached input is already included in input
totals. Billing, model-call counts, full engine calls/traffic/retries, first
verified preview and engine-only memory remain unknown.

Original captures/reports remain under `w2-text-sol-{model,baseline}-five-01` and
`w2-text-sol-comparison-five-01`; the new reports are under the corresponding
`rejudged-02` directories. `w2-text-capture-rejudge-integrity-01.json` verifies
all twenty original and imported workspaces, transcripts, driver results,
observed usage and client durations stayed identical. Separate trace reviews
and baseline-placement/mapping audits are retained. B08/B09 are next after
their store assumptions are checked. Full-suite, sister-project and readiness
gates remain open, with no engine checkpoint changes.

| Evidence | SHA-256 |
| --- | --- |
| Original source candidate | `bc2aac5d628d8cd3cbd5740789bda9eeb1972957a2545e7868ef461721e5d517` |
| Tested rejudging candidate | `095c7c0e1371266b168279206e01f563212f81bd44ae0f6148b2b831e593fb0f` |
| Original Inkbolt report | `3092be7bb880fe670812636786866a5b8599598876a3759d99bb139d7dfc75a9` |
| Original baseline report | `a8ff136b19a61ac2e49df022b700d148c7efa3b1006a48a3555d567f6e8576d2` |
| Original comparison | `f5a5f6943b71d9ebec479a8f5fde1d19945aeccdd9731bf4df94211f11db66d1` |
| Rejudged Inkbolt report | `8765717495fc03ba6b78949d88f24197a3b8d66d5f9dcdb577dab9bda026762c` |
| Rejudged baseline report | `4a8ac2ee3a44e629e6ef69830ea13488328099b6fc964c08372deb02662e5aeb` |
| Rejudged comparison | `d5bab3caad15ad9fe76db30dfe414a3723a8bdc57f5097dbf557c9725ec89043` |

## B08/B09 at 38f0397: five matched pairs

Five fresh repetitions per task and arm used the same external Codex CLI 0.160.0
configuration (`gpt-6.1-sol`, medium reasoning, explicit MCP approval option).
The model name identifies this evaluation only; no engine or harness default
was introduced. The release executable and pinned baseline tools were unchanged.
Inkbolt ran before the baseline on the shared Windows host, rotating task order
by repetition. This chat ran no other Inkbolt checks or benchmarks concurrently;
other host workloads were uncontrolled and OS caches could be warm. Both source
candidates stayed unchanged, and both tasks have five matched pairs with no
global or task matching issues.

| Task | Inkbolt / baseline artifact passes | Median input + output tokens | Median client seconds |
| --- | --- | ---: | ---: |
| B08 foreground mask | 5/5 / 5/5 | 327,734 / 43,824 | 93.7 / 32.3 |
| B09 local retouch | 5/5 / 5/5 | 354,590 / 43,008 | 102.0 / 29.2 |

Both tasks trigger the existing cost signal: matching shared artifact success
at **7.48x** and **8.24x** median observed token use with Inkbolt. All Inkbolt
saved-original and history checks also passed; those engine-only checks are not
applicable to the baseline. Seven Inkbolt attempts chose nondefault session
directories, and the corrected judges verified their exact original/current
states. Five equal outcomes do not prove equivalence or isolate the cost of
the extra history guarantees. These exact 16 by 16 fixtures measure basic
workflow use, not production-scale raster latency or memory.

All twenty transcripts, command bodies and MCP arguments were reviewed. No
repository/judge reads, extra engines/models or baseline Inkbolt access were
observed. Four Inkbolt attempts mixed MCP and shell calls: B08 repetitions one
and two used MCP for discovery, while B09 repetitions three and five also used
it for editing and publication. The other six used CLI only. The baseline used
the pinned Python/Pillow environment and ordinary local file inspection. Its
mask deliveries retained the original layer and separate selection/mask images;
its retouch deliveries retained the exact repaired editable pixel layer.

Invalid nested-schema selectors, full-schema fallbacks, rejected PNG options,
reversed clone transforms, and JSON text comparisons that mistook serialization
differences for state changes remain in the transcripts and usage. No attempt
was retried or discarded by the harness. Cached input is included in input totals,
never added twice; these ratios are not billing estimates. Complete model/engine
call counts, engine traffic/retries, first verified preview and engine-only
memory remain unknown. Event counts are not substituted for those measurements,
and this batch does not isolate MCP's effect.

The results extend the interaction-cost signal to these raster workflows.
Continue B10 and the remaining task coverage before the full plan decision gate;
the native photograph's exact precision and memory requirements remain distinct.
Full-suite, sister-project and readiness gates remain open, with no engine
checkpoint changes. Reports/workspaces remain under
`w2-mask-retouch-sol-{model,baseline}-five-01` and
`w2-mask-retouch-sol-comparison-five-01`. Separate trace reviews and
`w2-mask-retouch-sol-evidence-audit-01.json` retain the identity checks.

| Evidence | SHA-256 |
| --- | --- |
| Shared source candidate | `89c7856f7aada09c66da34a5e96d31ebe5f4b9a1671083cdd67a8b452c5dd36c` |
| Release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| Inkbolt report | `41bda628113e00aecf37e101fa2b883e73191d9fd4895956a8f135fab5f2d5fa` |
| Baseline report | `f22b7f737b7cb8c79f2411c41c4f1926b411a14830946cbe94f3faffec150717` |
| Matched comparison | `f3228271c9a41526e899a4937495cb26fda9aec1d87853e2cc505e493a2251bf` |

## B10/B13 at 7a07f07: five matched pairs with retained-capture corrections

Five genuine repetitions per task and arm used the same external Codex CLI
0.160.0 configuration (`gpt-6.1-sol`, medium reasoning, explicit MCP approval).
The model is evaluation metadata only. Inkbolt ran before the baseline on the
shared Windows host, rotating task order by repetition. No other Inkbolt checks
or benchmarks were scheduled by this chat during those solves; other workloads
were uncontrolled and OS caches could be warm. Both arms retained the same
source candidate, release executable and pinned baseline tools.

| Task | Inkbolt / baseline artifact passes | Median input + output tokens, all attempts | Median client seconds, all attempts |
| --- | --- | ---: | ---: |
| B10 native photograph repair | 3/5 / 5/5 | 606,589 / 75,674 | 144.9 / 83.2 |
| B13 transparent screen artwork | 5/5 / 5/5 | 313,210 / 41,717 | 101.7 / 35.6 |

Complete applicable workflow counts match artifact counts. B13 triggers the
existing cost signal at **7.51x** median input-plus-output tokens. B10 has only
three jointly successful pairs, so the fixed policy does not produce a cost
ratio; the all-attempt medians above retain failures. Five attempts give wide
95% Wilson intervals: 23.1%-88.2% for 3/5 and 56.6%-100% for 5/5. They do not
establish general reliability or statistical equivalence.

The original judge rejected every baseline B10 TIFF at an embedded ICC profile
stored with TIFF UNDEFINED byte type 7. Its byte reader now preserves that field
for both byte orders. Fresh judging verifies every 16-bit channel and pinned
Pillow reopening. Original B13 Inkbolt repetition one had the exact private
note in `metadata.note`; the judge had demanded `metadata.private.note`, which
the prompt never prescribed. It now admits placement within the engine's
metadata schema while requiring the exact note value and all original source,
pixel, color and create-only publication checks. Regression controls cover
changed/missing notes, geometry, alpha, private delivery records, file identity,
overwrite protection and native low-bit corruption.

All twenty unchanged captures were rejudged after focused Windows/WSL checks.
The five baseline photo failures and one screen-source failure now pass; the
other outcomes are unchanged. Original reports remain alongside the new reports.
Full workspace hashes, transcripts, client results, token/time observations and
captured process-memory evidence match their originals. No model was rerun and
no attempt was added or discarded.

B10 Inkbolt repetitions two and five still fail. Their commands omitted the
workspace option, then interpreted the resulting import error as requiring an
explicit store. They departed from the prompt's `storage:{}` contract and used
`native-tiles`. Immutable-store checks fail and fresh rendering cannot find the
tiles at the required default root. Missing downstream checks remain failures;
the delivered TIFFs from those attempts do not receive independent pixel credit.
The three successful attempts pass exact native samples, immutable tiles,
proposal/history checks and the 256 MiB per-process bound. That bound uses
captured peaks across owned client/tool processes; it is not exact engine-only
memory. The baseline passes its applicable sample, preview and memory checks;
Inkbolt history guarantees remain explicitly inapplicable there. This is a
2.07 MP fixture, not the larger W4 workload gate.

All completed command/MCP events and retained generated helper bodies were
reviewed. No prohibited repository/judge reads, extra model/engine use or
baseline Inkbolt access were observed. File-change events omit patch bodies,
so earlier overwritten helper versions are not fully retained. No image-view
tool was observed; numerical validation does not prove visual review. Only
B13 Inkbolt repetition one used MCP alongside shell calls; the other nine used
CLI only. Every Inkbolt photo attempt first tried an unsupported repair operation
before finding native retouch. Invalid schema selectors and workspace/path
errors remain in the recorded usage. Client-written error summaries are not
substituted for captured command responses.

Prioritize actionable workspace errors and clearer native-operation discovery,
then remeasure their effect with the same task contracts. Continue B11/B12 and
the remaining coverage before the full plan decision gate. Token totals already
include cached input and are not billing estimates. Full model/engine call
counts, traffic/retries, first verified preview and engine-only memory remain
unknown. Extra native-source/history obligations and mixed transports prevent
a causal attribution of the cost difference. No checkpoint credit changes.

Evidence is retained under `w2-photo-screen-sol-{model,baseline}-five-01` and
the corresponding `rejudged-01` directories, with original/rejudged comparison
reports. `w2-photo-screen-capture-rejudge-integrity-01.json` and separate trace
reviews retain the identity and review checks.

| Evidence | SHA-256 |
| --- | --- |
| Original source candidate | `a6fbc0f46e6e4875b1e93a67864df5246d7b3fa34732e061eb4ff1c06e42aaa5` |
| Tested rejudging candidate | `2d7fa5e3eddaa00f616189c548d16d0c7d0e4d974687861c6fdf232e27c4ebeb` |
| Release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| Original Inkbolt report | `2c882673d3e268effddb16b57adf4bb8b11b276ab5b043c4769a065a6380715c` |
| Original baseline report | `ea9feb88f29fa5abed557eb5142c57d84e2351c0e461fbbbeaae183f1214d4f4` |
| Original comparison | `44a342ab7214ed60e4c5a1d77254fe0e980578321592e1fbbc5f0228f45f2556` |
| Rejudged Inkbolt report | `54ebcd79653411ec490cb90be67f8b8d913e47c2676de70f6f41c8c535590ad1` |
| Rejudged baseline report | `6f5468d57866598014ac6fc07435b956ad6e2bfe7075abdd0cde8135df56b770` |
| Rejudged comparison | `b5ae766dcb21748c2dc38ac87ab359c8a001a66e1ea6a8601922563a1eba7b98` |

## B11/B12 at 30c4ebd: mixed composition and layout variants

Five genuine repetitions per task and arm used the same external Codex CLI
0.160.0 configuration (`gpt-6.1-sol`, medium reasoning, explicit MCP approval).
These are evaluation settings, not product or harness defaults. Inkbolt ran
before the baseline on the shared Windows host, rotating task order between
repetitions. Sources and tools stayed fixed through both arms. No other local
Inkbolt verification or benchmarks ran during those solves; other host workloads
were uncontrolled and OS caches could be warm. The baseline retained pinned
resvg 0.47.0 and Pillow 12.3.0 in the external Python 3.11 environment.

| Task | Inkbolt / baseline artifact passes | Median input + output tokens, all attempts | Median client seconds, all attempts |
| --- | --- | ---: | ---: |
| B11 mixed masked composition | 3/5 / 5/5 | 395,699 / 72,214 | 114.8 / 46.8 |
| B12 shared layout variants | 5/5 / 5/5 | 566,966 / 61,799 | 128.8 / 46.0 |

Complete applicable workflow counts match artifact counts. B12 triggers the
fixed cost signal at **9.17x** median input-plus-output tokens. B11 has only
three jointly successful pairs, so the fixed policy does not publish a cost
ratio; all-attempt medians retain its failures. Five trials give wide 95% Wilson
intervals: 23.1%-88.2% for 3/5 and 56.6%-100% for 5/5. These small 32 by 24
composition and three-artboard fixtures do not establish production scale,
general reliability, statistical equivalence or the cause of the token gap.

The original B12 judge stopped three Inkbolt attempts at a fixed array-position
assumption. Native `add` operations produced a different cross-parent item
interleaving while preserving the requested hierarchy and sibling order.
A synthetic client reproduced the same failure before the correction. The
judge now locates roles by content and parent and compares all fields plus each
parent's ordered children. It still rejects changed parents, sibling order,
binding targets, resources, properties, receipts and saved history. One attempt
also used the exact names from the prompt's artboard table as display labels.
Those labels and default empty labels are accepted; unrelated labels fail.
The prompt and its fixed IDs, geometry and other defaults are unchanged.

All twenty original captures were rejudged after focused Windows and WSL
verification. The three B12 errors now pass every artifact and engine check;
all other outcomes remain unchanged. Original reports, full workspace hashes,
transcripts, client results, token/time observations and captured process-memory
evidence match the originals. No model attempt was rerun, added or discarded.
The separate synthetic before/after capture also passes unchanged and receives
no model credit.

B11 Inkbolt repetitions one and three still fail: both added `locked:true` to
the original image although the prompt requires default remaining properties.
That is the sole difference between each saved original and the independent
template. Current pixels and original resource identity pass, while complete
composition and saved-state/history checks fail. The judge correction does not
waive those lock changes. Inkbolt's saved-revision and typed-binding guarantees
remain engine-only requirements, inapplicable to the baseline.

All completed direct command/MCP events and available generated script bodies
were reviewed. All ten Inkbolt attempts used CLI only. No prohibited access was
observed, but file-change events omit patch bodies; some intermediate versions
are unavailable. B11 repetition four removed its helper after further edits,
so its final nested helper behavior cannot be fully attested. No image-view tool
was observed; clients' claims of visual review are not independently verified.
Repeated schema lookups, invalid selectors and relative-path imports without a
workspace remain in the usage. Token totals include cached input and are not
billing estimates. Full model/engine call counts, traffic/retries, first verified
preview and engine-only memory remain unknown. Captured client-tree memory is
separate evidence, not an engine memory measurement.

The results reinforce workspace guidance and operation discovery as priorities.
Continue B14-B20 and the separate sister-project comparison before the full W2
decision gate. No engine checkpoint or complete readiness gate gains credit.
Evidence remains under `w2-mixed-variants-sol-{model,baseline}-five-01` and the
corresponding `rejudged-01` directories. The original and rejudged comparisons,
`w2-mixed-variants-capture-rejudge-integrity-01.json`, arm reviews and retained
script bodies preserve the outcome and review boundaries.

| Evidence | SHA-256 |
| --- | --- |
| Original source candidate | `278a9c1f7ace6247504ea3e29f2b9b0f19d6db071a2c57051aa9e7c1485636a1` |
| Tested rejudging candidate | `04f6923675698f2f3451127b137c259988fef43962209db01cf5adeb52e05f46` |
| Release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| Original Inkbolt report | `efda116a63ec37d1c305f1e9d835979320b1a9345385cf2467f20fe4f8b5b9e9` |
| Original baseline report | `2687b06b3d2def5c871464e0ccf0c8447f24c1b313f2198b5469a1efa4a1a536` |
| Original comparison | `aebceb45d795b2a3979926c0536e68f5ebc632113d5c113ee0cfac7a3c377526` |
| Rejudged Inkbolt report | `b6b886736298b1756630d6dfc07243454af49f78f66390d37a44672323737c9c` |
| Rejudged baseline report | `57380085b0485a31a0c24596ff1756c05f8cb798aa7e9fd47f5194a71f0e3123` |
| Rejudged comparison | `8f76b4837778e02596cf4703fc793b04c4fcb9b200f06f66a7a4cc3dffdfbd9f` |

## B14/B15 at 7d31cf9: print delivery and resource repair

Five attempts per task and arm used the same external Codex CLI 0.160.0,
`gpt-6.1-sol` medium configuration, explicit MCP approval mode, shared Windows
host and pinned baseline tools as the preceding batches. The Inkbolt arm ran
first, then the baseline; task order rotated per repetition. The repository and
engine stayed unchanged throughout, with no concurrent local verification or
benchmarks from this chat. Other host workloads were uncontrolled and caches
could be warm. Model names describe this evaluation only, not product defaults.

| Task | Inkbolt / baseline artifact passes | Complete workflow passes | Median input + output tokens, all attempts | Median client seconds, all attempts |
| --- | --- | --- | ---: | ---: |
| B14 physical print | 5/5 / 4/5 | 3/5 / 4/5 | 531,200 / 97,120 | 114.0 / 97.0 |
| B15 resource repair | 5/5 / 5/5 | 5/5 / 5/5 | 274,948 / 56,972 | 89.8 / 44.2 |

The initial B14 judge rejected every baseline PDF at the rendering-intent
operator `ri`. Public-specification review exposed other unprescribed encoding
restrictions: direct-only page/spot color-space arrays, a fixed first corner and
traversal direction, and page-group flags that are equivalent for the exact
standalone page's two opaque, disjoint rectangles. Tested corrections now admit
those representations, while preserving scoped rendering intent, cumulative
graphics state, exact profiles, geometry, native inks and conversion settings.
The original prompt and all check IDs/classes remain unchanged.

Four unchanged baseline captures now pass every artifact check. Repetition one
still fails native-ink delivery because both paints omit `UseBlackPtComp OFF`.
The prompt requires compensation off; absence leaves the choice to the PDF
processor, as explained in the [PDF Association application note](https://pdfa.org/resource/pdf-2-0-application-note-001-black-point-compensation/).
Its physical boxes, profiles, exact preview, source preservation and declared
losses pass. No delivery was edited and no model was rerun. B14 has four jointly
successful artifact pairs, below the fixed five-pair cost threshold; its cost
ratio remains unavailable. Five trials cannot establish a reliability advantage.

B15 triggers the fixed cost signal at **4.83x** median input-plus-output tokens.
Its five paired artifact successes give a wide 95% Wilson interval of
56.6%-100% in either arm. The small synthetic repair fixture does not establish
general reliability, production-scale recovery or a cause for the cost gap.
All attempts remain in the distributions; cached input is already included and
the ratio is not a billing estimate.

The original judge stopped B14 outputs stored in valid subfolders or carrying
unprescribed swatch display names. B15 repetitions three and four retained the
complete successful CLI response around their dry-run result. Tested corrections
now admit those choices, retaining all native controls, source/profile identities,
preview pixels, review proposals and history requirements. Additional print-loss
disclosures are accepted only when every required limitation remains present.
Native receipt binding is checked under the existing engine-only history check;
the common artifact check remains independent. No check ID or class was removed.

B14 Inkbolt repetitions two and five still select snapshot publication receipts
in session.json. Correct PDF receipts also exist, but the judge must verify the
delivered request ID, not silently choose another. Their artifacts and saved
history otherwise pass; the complete workflow remains failed. This identifies
receipt selection and clearer delivery guidance as follow-up work, not corrupt
PDFs or broken session history.

After focused Windows/WSL checks, all twenty original captures were imported into
new judge directories. Original reports and every original workspace, transcript,
client result and capture identity were checked, as were imported workspace bytes,
usage, execution times and captured memory. No model attempt was rerun or removed.
Evidence is under `w2-print-resources-sol-{model,baseline}-five-01`, corresponding
`rejudged-03` roots and `w2-print-resources-capture-rejudge-integrity-03.json`.
The first correction and intermediate PDF-reader reports remain retained as
`rejudged-01` and `rejudged-02`; their report identities are also unchanged.

All completed direct commands and MCP arguments were reviewed. File-change helper
bodies omitted from event logs were read and archived; inline creation/edit
commands remain available for deleted helpers. No direct prohibited access was
observed. This is not authenticated isolation or complete nested-process evidence.
Inkbolt B14 repetition two used MCP schema tools; the other Inkbolt trials used
CLI commands. No image-view tool call was observed, so numerical pixel checks do
not establish visual review. Full model/engine call counts, traffic/retries,
first verified preview time and engine-only memory remain unknown. Observed
client-tree memory has a separate scope.

These results reinforce operation discovery and workspace guidance priorities.
Finish B17-B20 and review the remaining B01/B07 caveats before the full W2 decision
gate. The separate sister-project comparison and B10 Linux memory evidence remain
open. No engine checkpoint or complete readiness gate gains credit.

| Evidence | SHA-256 |
| --- | --- |
| Original source candidate | `4e36bcaf30056c01e2343a1596caf796204cc775a4e8c4f319bd33b22efb3a89` |
| First tested rejudging candidate | `3e8a23d1dadbe3b1e77f128afd83516fda6e7a0055bd89a48efb259d6daacb6d` |
| Final tested rejudging candidate | `94a18f910c738e3f2ff1f3949ecf081046a459506ec137a432eb6a3bb4a95024` |
| Release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| Original Inkbolt report | `6b4ad8e0bae50d8e05f57dcc3fcf578002256db8b5caca420c9045671b1f0f0c` |
| Original baseline report | `b0e084662a8b05395495bee8ec447e8862dbc4c20ac2211330835b24e48cb600` |
| Original comparison | `04b595810e96b7c82cc45feca8a40005383c887616378c43c0b52caac3726288` |
| Final rejudged Inkbolt report | `983965514e72661f02a05d6634088a7d0b49b214fb8de813a02719e8e120b77f` |
| Final rejudged baseline report | `5790ddd9509286d35d314ebd78a251a37afd3a44dc39892393ff0c3ddb7b0342` |
| Final rejudged comparison | `1f2be28adb7fa535d53842fc171a2b4d846ec7d22515998d671e242acdfe8655` |

## B16 at 3c52ce4: preliminary text-repair trials

Five attempts per arm used Codex CLI 0.160.0 with externally selected
`gpt-6.1-sol`, medium effort, and the same pinned baseline tools as the preceding
batches. Inkbolt ran first, then the baseline on the shared Windows host. Inputs
and the engine stayed unchanged, with no concurrent local engine verification
or benchmarks from this chat. Other host workloads were uncontrolled and caches
could be warm. Model selection is evaluation configuration only.

| Measurement, prompt version 1 | Inkbolt | Baseline |
| --- | ---: | ---: |
| Retained attempts | 5 | 5 |
| Original complete passes | 0/5 | 0/5 |
| Complete passes after default-field correction | 1/5 | 0/5 |
| Median input + output tokens, all attempts | 481,327 | 129,382 |
| Median client execution, seconds, all attempts | 114.6 | 94.3 |

The first four Inkbolt attempts saved hand-written repaired recipes without a
revision field. Reopening them yields revision 0, so they do not deliver the
committed revision-1 source. Those failures remain. Attempt five saved revision
1 correctly but omitted ordinary default fields. Its independently reopened
before/after documents already matched the complete expected states; the judge
incorrectly required the raw JSON to include every serialized default. Comparing
the reopened values corrects that restriction while preserving exact controls,
revision, fonts, pixels, proposals and durable history. Tested negatives still
reject missing/stale revisions, altered resolution and changed artwork.

The baseline recipes used alternative font containers, tagged paint objects,
string wrap controls or base64 font data in the byte-length field. The judge
rejects those forms, but the version-1 prompt did not fully specify their JSON
types. These results therefore do not establish a reliability advantage for
either arm. Prompt version 2 states the types and native snapshot revisions
explicitly, without changing fixtures, check IDs/classes or required outcomes.
The matched version-2 batch below uses that contract in both arms and is not
pooled with these preliminary attempts.

A separate post-hoc diagnostic found all ten review/final PNG pairs exact at
every pixel. That does not waive failed editable-source checks or turn checks
skipped after source refusal into passes. No successful matched pair supports a
cost ratio. All attempts remain in the token/time distributions; cached input is
already included, and client time includes tool work. Full model/engine call
counts, traffic, retries, first verified preview time and engine-only memory
remain unknown. Client-tree memory has a separate observed scope.

All completed direct command bodies, including inline helper creation/edits,
were reviewed. No direct prohibited access or image-view call was observed;
this is not authenticated isolation, nested-process attestation or visual review.
All ten original captures, reports, workspace files, transcripts, usage, times
and memory observations remained unchanged during rejudging. Evidence is under
`w2-repair-sol-{model,baseline}-five-01` and corresponding `rejudged-01` roots,
with `w2-repair-capture-rejudge-integrity-01.json` and arm-review records.
This advances benchmark preparation and snapshot-delivery guidance; no engine
checkpoint or complete readiness gate gains credit.

| Evidence | SHA-256 |
| --- | --- |
| Original source candidate | `429238a8bdc98f74a71f985cadc0e8f6fd2bd8545e2208b28f398034280e5885` |
| Tested default-field judge | `b145613796e741388e7ca9599db61ae8d67957247010e5d5bb8400e2ec2aa2a5` |
| Release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| Original Inkbolt report | `ed11b72ff22cab8c2fbf5d866833e2996964dae9948331d22eb1fc55209c8f61` |
| Original baseline report | `52ff8cbd110e454da73acecb647e65ee510bebc0b6b755c38e9a7b950483fa13` |
| Original comparison | `9997c4a7d37625eb84064a7cfc0696fcfb199ef18746ba0b46a280d36d17812a` |
| Rejudged Inkbolt report | `f823f698f2749a6e1a189bbe3da6d3919d8947947b7e376222144c739bc84367` |
| Rejudged baseline report | `da500971d4d94e13b97dd3873aba7654e47da66ce52728e2dc3593b1434e0618` |
| Rejudged comparison | `b76ede6bd8f1ede6cf5852e84c80413fe4b8e630f576e66e3e42afdac8100fa8` |

## B16 at a048690: explicit version-2 repair contract

Both arms passed all five artifact trials under prompt version 2. All five
Inkbolt trials also passed the proposal, saved-revision and durable-publication
history checks. The baseline's engine-specific history check remains not
applicable. No B16 judge correction or prompt change was needed for this batch.

| Measurement, five attempts per arm | Inkbolt | Baseline |
| --- | ---: | ---: |
| Artifact passes | 5/5 | 5/5 |
| Median input + output tokens | 584,833 | 130,703 |
| Median client execution, seconds | 112.9 | 82.4 |

Median token use was **4.47x** the baseline's. Cached input is already included
in input tokens; this is not a billing-cost ratio. Five equal outcomes do not
prove reliability equivalence: the 95% Wilson interval is approximately
0.566-1.000 for each arm, assuming independent trials. Under the fixed policy,
this task supplies another signal to reduce interface cost. Completed traces
show repeated schema/definition searches, full-schema fallbacks and workspace
path corrections. These observations motivate changes, but do not isolate how
much of the cost any single change would remove. Remeasure after implementation.

Commit `a048690fa443dfb57a986d1a4d5dc38b8bc740fc` and prompt
`f3cf3d806e477b57d847130050c063be0636ed53d207cfe756ec78d9ef0abd85`
stayed fixed. Both arms used externally configured Codex CLI 0.160.0 with
`gpt-6.1-sol`, medium effort. Baseline tools remained resvg 0.47.0 and Pillow
12.3.0. Model selection is evaluation configuration only. Inkbolt ran first,
then the baseline, on the same shared Windows host without concurrent local
engine verification or benchmarks from this chat. Other host workloads were
uncontrolled, caches could be warm, and order was not randomized.

All completed direct commands, inline helpers and retained scripts created by
file-change calls were reviewed. No direct prohibited access or image-view call
was observed. This is not authenticated isolation, complete nested-process
attestation or visual review. Numeric pixel checks and independent artifact
judging remain distinct from seeing the image. Full model/engine call counts,
traffic, retries, first verified preview time and engine-only memory remain
unknown; observed client-tree memory has a separate scope.

The 487 retained files under `w2-repair-v2-sol-{model,baseline,comparison}-five-01`
have a complete hash inventory in `w2-repair-v2-complete-hashes-01.json`;
arm-review records retain trace and helper identities. Version-1 failures remain
separate. B17-B20, further smaller-model trials, complete metric coverage and
the sister-project comparison remain open. No engine checkpoint or complete
readiness gate gains credit.

| Evidence | SHA-256 |
| --- | --- |
| Source candidate | `17387bb11cd57c5a0624516de999355a698858c8bd0e657b60063a0583d33af5` |
| Release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| Inkbolt report | `5678475448a41cc96e7cbb6d3c00fb6873b536cda15906fcb66032006b4bf35e` |
| Baseline report | `b340d8340f9c0312a2d57d12794f59523f4d3e0c2abc39e6a223fa67798322da` |
| Comparison | `6772c4e6ceb20b8341d1c48f21588214b121965e2756db87b4be32e20a7b5cd9` |

## B17/B18 at cae530a: receipt and concurrent-edit recovery

Five genuine attempts per task exercised recovery from a withheld editing
response and recovery from another writer's intervening change. Both tasks
passed all artifact checks. B17 passed its complete workflow in three attempts;
B18 passed all five. Their no-engine baselines remain explicitly not applicable,
so these results establish no comparative advantage or full-suite acceptance.

| Measurement, five attempts per task | B17 lost response | B18 concurrent edit |
| --- | ---: | ---: |
| Artifact passes | 5/5 | 5/5 |
| Complete workflow passes | 3/5 | 5/5 |
| Median input + output tokens | 269,176 | 249,608 |
| Median client execution, seconds | 94.6 | 125.0 |

B17 attempts 1 and 3 put the CLI's `ok`/`result` envelope where
[the prompt](../tools/benchmark_prompts/B17.md) explicitly requires the compact
result itself. Their `original-receipt` and `retry-idempotent` checks failed with
`KeyError: document_ref`. Edited pixels, restored source, undo preservation and
history checks passed. These remain failed deliveries; the receipt contract was
not relaxed and neither attempt was replaced. B18 preserved the other writer's
edit and passed stale-request rejection, proposal, source, pixel and history
checks in every attempt.

All ten attempts remain in the totals, including the two failures. Cached input
is included in input tokens and is not added again. Client execution includes
startup and tool work. Full model/engine call counts, traffic, retries, time to
first verified preview and engine-only memory remain unknown. Observed
client-tree memory is retained under its separate scope. Five trials cannot
establish general reliability; even 5/5 has a 95% Wilson interval of approximately
0.566-1.000, assuming independent trials.

Commit `cae530a9986cbb056616d7cf7ed6a0e311529ab1`, both version-1 prompts,
the executable and source candidate stayed unchanged. The external configuration
selected Codex CLI 0.160.0, `gpt-6.1-sol`, medium effort. These settings describe
this evaluation only. Tasks ran sequentially, rotating order by repetition, on
the shared Windows host. This chat ran no other local engine verification or
benchmarks during measurement; other host workloads were uncontrolled and
caches could be warm.

Every completed direct command and inline helper was reviewed. No prohibited
direct access or image-view tool call was observed. Some solver-authored
transcripts reconstruct earlier responses; the retained driver event traces
are separate evidence, and reconstructed text is not authenticated telemetry.
This review does not establish isolation, complete nested-process attestation
or visual inspection. Independent artifact judging remains separate.

The comparison retained all ten not-applicable baseline rows and both native
failures, with no global matching issues. Its exit 2 correctly reports the lack
of applicable baseline pairs. The external batch wrapper incorrectly expected
exit 0 and exited 1 after writing all reports; no trial was restarted. The
wrapper error and original reports are retained.

The 746 files under `w2-retry-conflict-sol-{model,baseline,comparison}-five-01`
have a complete hash inventory in `w2-retry-conflict-complete-hashes-01.json`.
`w2-retry-conflict-model-arm-review-01.json` records trace and helper identities;
`w2-retry-conflict-summary-01.json` retains task statistics and batch outcomes.
Repeated workspace/path corrections and discovery searches, together with the
receipt-format failures, reinforce the existing priority for actionable errors,
focused discovery and snapshot/receipt delivery guidance. Remeasure after changes.
B19/B20, broader metric coverage, smaller-model trials and the separate
sister-project comparison remain open. No engine checkpoint gains credit.

| Evidence | SHA-256 |
| --- | --- |
| Source candidate | `3f199ad5c1f30cf1d6ccc7569d586a897fa248d6e62acee9887d88d98c12c064` |
| Release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| B17 prompt | `f575638fd7aeda0c5faaee06affa8eec1297b006aa0824e5edffc373d57be4e6` |
| B18 prompt | `5b604b46bd953456eddb22e87e08751ba41a3c0d9e8dca39bf02fb7cf99049ef` |
| Native report | `55914818081c13dd82605ba6cd508768584f6889f3c712e4d28f539cb6ac8cb7` |
| Not-applicable baseline report | `5c5730689621b479cb069c522068a68087fb3f2d28ff2aaf162411216d05bf1c` |
| Comparison | `64d1e1f895aa6684bb0046909ba962a1b529b3af9e1c5e1827494ee749b9db3d` |

## B19 at 2cf3869: retained evaluation setup failures

All five genuine attempts failed before issuing an engine command. Each trace
records a `PermissionError` when the supplied bridge tried to create its first
control-channel request outside the client's writable workspace. Harness lifetime
accounting confirms zero engine processes and no leaked processes for every
attempt. These are evaluation setup failures, not evidence of job-recovery
reliability. The five baseline rows remain not applicable.

The source stayed fixed at `2cf3869d2a6ab98de6fb497851339d4ca93973ca`, candidate
`e71211286f39516068bfe297560e87cf41b3fbde7dc53bd4faa2a31ae03fb7b1`, using
version-3 prompt `ed2b7ba79fa7a76daff271f792c19153f1570d1793ceaf8ba8616c493c483886`.
External settings remained Codex CLI 0.160.0, `gpt-6.1-sol`, medium effort.
All completed direct commands were reviewed; no prohibited direct access or
image-view call was observed. This is not authenticated isolation. All 65 files
under `w2-job-recovery-sol-{model,baseline,comparison}-five-01` are hashed in
`w2-job-recovery-setup-failure-hashes-01.json`; the companion review records trace
identities and zero-process observations. None of these attempts was replaced.

The adapter now grants the exact validated control-channel folder through
`--add-dir`, while retaining the client's sandbox and excluding the enclosing
evidence directory. A genuine pilot must verify that correction before another
batch; source changes and later results remain separate from this failed setup.

| Evidence | SHA-256 |
| --- | --- |
| Native report | `55cc71a4105c22d9b5481b6c080ee5a54924a31281f1cc75f4f3ceda8bc96dc7` |
| Not-applicable baseline report | `8cd835415e481c562daaa3aca811121085e0ca332327bc7ea5af7da7496a085f` |
| Comparison | `821948612b33097741d4cf5f9ae75de371b23b476038865e0a64bd915483080a` |

## B19 at 5079c5a: bridge pilot and publication observation gap

The genuine pilot confirmed that the narrow directory grant lets the client
reach the engine. It delivered the requested files and passed the independent
preview/recovered-pixel, cancellation, interrupted-state, revision/resource,
history and source-preservation checks. The complete trial still failed.

During discovery, the client put `command` inside bridge arguments as well as
at message level. This malformed message triggered a controller protocol error;
later successful operations do not erase it. Separately, the client validly used
`session.publish` for the required overwrite refusal. The controller recognized
only `document.publish`, leaving the final output checkpoint absent and failing
the publication/no-partial-final checks. A synthetic run reproduced that missing
checkpoint without the malformed request.

The controller now observes either valid publish command and explicitly rejects
reserved nested fields before engine execution. The pilot remains failed; no
checkpoint is invented afterward, and its capture is not used as passing workflow
evidence. A new batch uses the corrected controller and retains this pilot
separately. Native and baseline task criteria are unchanged.

The pilot used commit `5079c5a4fe0f24387571556fd275c0503f8a0119`, candidate
`d1166a0fd05568e97e663c30068be00e0e8da323ff4a8ae52cc5b37b09a214f3`, the unchanged
version-3 prompt and the previous external client/model settings. Inputs stayed
unchanged. Its report SHA-256 is
`96ef4d6130fbfe6138f06df5f3811ab675d52d93c4dc02b186c55c2a610dde3c`.
All 254 files under `w2-job-recovery-bridge-pilot-01` are hashed in
`w2-job-recovery-bridge-pilot-hashes-01.json`. The companion review records all
39 completed items and the two retained helper files. No prohibited direct access
or image-view tool was observed; numeric pixel checks are not visual inspection,
and direct traces/final helper hashes do not authenticate every nested operation
or intermediate helper version.

## B19 at 30ecf5b: five recovery attempts with protocol failures

All five genuine client attempts remain failed overall. The first four passed
all nine independent artifact, recovery and source-preservation checks. The fifth
saved its preview and editable source but never admitted a cancellation job;
only source preservation was scored, with eight checks missing. This is 0/5
complete workflows, not a recovery reliability claim or completed model batch.

Attempts 1, 3 and 4 supplied a reserved nested `command` field while discovering
schemas. Attempt 2 first used an inline snapshot without its resource binding,
then attached an unsupported retry annotation to a fault control. Attempt 5
repeatedly supplied an extra `resources` field and varied the cancellation
destination; it finally requested the queue gate before successful cancellation.
The broad destination error did not identify that extra field. Later successful
commands cannot erase a controller protocol failure. No criterion was relaxed.

The controller rejected each attempt before accepting its driver evidence, so
the reports retain `model_trials:false` and unknown accepted usage, timing,
engine-count and memory aggregates. Genuine client execution and directly judged
artifacts are retained separately; unvalidated client-result files are not
promoted into accepted metrics. Harness process accounting records 44, 45, 57,
65 and 13 owned processes respectively, all exited with no observer error.

The five baseline rows are not applicable. The comparator reports no matching
issues but is not decision-ready; its expected exit 2 is preserved. Runs used
commit `30ecf5b2442902db23364c5f0a2ea4cd6ed85ec4`, the unchanged version-3 prompt,
and the same external Codex CLI 0.160.0 / `gpt-6.1-sol` medium configuration.
Inputs stayed fixed. Trials ran sequentially on the shared Windows host with no
concurrent local engine verification or benchmarks; caches could be warm.

All completed direct commands and retained helper files were reviewed. No
prohibited direct access or image-view call was observed; numeric pixel checks
are not visual review. Trial 3 manually reconstructed its returned-value file;
this remains distinct from harness observations. Final helper hashes and direct
traces do not attest every intermediate version or nested operation.
The 1,305 files under `w2-job-recovery-sol-{model,baseline,comparison}-five-02`
are hashed in `w2-job-recovery-complete-hashes-02.json`, with companion arm review
and summary files. Earlier setup and pilot failures remain separate.

Prioritize actionable discovery errors, saved-reference and snapshot guidance,
and precise bridge argument errors before remeasuring this workflow. B20,
accepted metric coverage and full W2 acceptance remain open. No engine
checkpoint receives additional credit.

| Evidence | SHA-256 |
| --- | --- |
| Source candidate | `3c9e4d73ed167cee08e03993b213e576e894af8aed1e75caad46bfdf4f6ddd08` |
| Release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| B19 prompt | `ed2b7ba79fa7a76daff271f792c19153f1570d1793ceaf8ba8616c493c483886` |
| Native report | `835a4c4dd806dbeb6c27700005af0e1575656208b34249d256fedfba45ea1543` |
| Not-applicable baseline report | `fc319d392ced4b6694d67eb04ce43bf936591e8e239f4776b25bb328a5aa9f47` |
| Comparison | `35ff00fe37146565b910be7e73b21bc45a47bfbad124bb0204986c9d93be8a4d` |

## B20 at fe7786d: linked-graphic delivery prerequisite failures

The first genuine five-pair B20 batch passed **0/5 complete native workflows**
and **5/5 baseline workflows**. Native artifact quality remains unjudged: only
source preservation was scored, with fifteen checks missing per native attempt.
The baseline passed its seven task artifact checks plus source preservation;
its eight engine-specific checks are not applicable. This is a workflow failure
signal, not a finding that native rendered pixels failed comparison.

All five native attempts used `session_id:"linked-graphic"` instead of the
required `"work"`; the prompt assigns `linked-graphic` to the document ID.
Attempts 2-5 passed driver-evidence validation but failed the judge's session-store
prerequisite. Attempt 1 also requested consumer `media.inspect`, outside the
bridge allowlist, causing a fatal protocol failure. The prompt instructs use of
public discovery but does not disclose that exact allowlist. Preserve this setup
limitation and failure; a later prompt/control clarification needs a separately
versioned run. Neither the allowed commands nor the session-ID requirement was
waived afterward.

Trace review also found nondefault item names in attempts 1-4 and a stale-error
envelope instead of the requested error object in attempt 5. These observations
receive no independent artifact/history score because earlier prerequisites
stopped judging. Delivered files and client assertions cannot supply that credit.

| Observation | Native arm | No-Inkbolt baseline |
| --- | ---: | ---: |
| Retained attempts | 5 | 5 |
| Complete applicable workflow | 0/5 | 5/5 |
| Attempts with accepted driver metrics | 4 failed attempts | 5 successful attempts |
| Median input + output tokens in that accepted subset | 1,029,586.5 | 326,203 |
| Median client execution, seconds | 237.3 | 138.5 |
| Median total engine commands | 54.5 | 19 |

Native total command counts include Inkbolt and the consumer; baseline counts
include only the consumer. The baseline authored graphics with pinned Pillow
and used the same consumer to render the required videos. Native work includes
additional revision/history guarantees. These are observations of different
outcomes and applicable scopes, not cost per successful native workflow.
Input totals include cached context and are not billing estimates. Attempt 1's
unaccepted client-result metrics stay excluded; native time to first independently
verified preview is unknown. Reports retain traffic, retries and the distinct
engine, consumer-tree and client-tree memory scopes.

Both arms used commit `fe7786d1eaad316e5986edf0b804cac228481ebd`, unchanged
version-2 prompt, Codex CLI 0.160.0 and the same external `gpt-6.1-sol` medium
configuration. Model choice remains external evaluation metadata. All five native
attempts ran before the five baseline attempts, sequentially on the shared
Windows host with no concurrent local engine verification or benchmarks. Inputs
stayed unchanged; order was not randomized and caches could be warm.

All completed direct commands and final retained helpers were reviewed. No
prohibited direct engine/evidence access or image-view tool was observed.
Numeric pixel/hash assertions are not visual review, and these traces do not
authenticate every intermediate helper version or nested operation. Consumer
lifetime accounting observed 525 native-arm and 353 baseline-arm processes,
including inherited encoders/probes, all exited with memory observation available.
Those counts exclude other engine/client trees and are not command counts.

All 3,019 files under `w2-linked-animation-sol-{model,baseline,comparison}-five-01`
are hashed in `w2-linked-animation-complete-hashes-01.json`; companion review and
summary records bind the ten traces and retained helpers. The comparator reports
no matching issues and categorizes B20 as a losing task by workflow completion.
Its full-suite `decision_ready`, `matched_model_baseline_complete` and
`actual_model_benchmark_complete` gates remain false. B19/B20 guidance repairs
and the trace-motivated B03/B16 discovery remeasurement remain separate next steps.
No engine-checkpoint credit changes.

| Evidence | SHA-256 |
| --- | --- |
| Source candidate | `3514eda7f794db9083a3a300e11ef126d155162d118541b561103eceb2b37433` |
| Inkbolt release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| B20 prompt | `ca5e7d5b97f0e8fecb605c203fea6e195066f9b5cf8183972f77d830eeae62a8` |
| Consumer executable | `3d9aa4644525c84108b9ec276605595e3d115b6d1fc8d4523b7a48a934f5f536` |
| Native report | `d51c73faba3bba6ea0a8be4f802c4dcafa9ca2a45d1ed3e70c94226bf8d40f40` |
| Baseline report | `f5e84eb6ae82f2b4604f8f8ceac3ca6618ac553c0dd9d0c1fb59af4c6988badf` |
| Comparison | `71b23175cc57ef35d5cd30cd5ce9e9f986fadb5ba92d4fa9f8290b45b64f17cd` |

## B03/B16 at d34851e: nested discovery follow-up

All twenty attempts passed: five per task in each arm, including every applicable
artifact and workflow check. The native arm also passed its separate history and
revision checks. Five successes give a 95% Wilson interval of 56.6%-100%; this
small sample does not establish equivalence or a reliability advantage.

| Task | Native / baseline passes | Native median tokens | Baseline median tokens | Token ratio | Native / baseline median seconds |
| --- | --- | ---: | ---: | ---: | ---: |
| B03: 5,000-object layout | 5/5 / 5/5 | 300,182 | 65,030 | 4.62x | 111.2 / 43.0 |
| B16: text overflow repair | 5/5 / 5/5 | 574,154 | 110,396 | 5.20x | 160.9 / 105.6 |

B03 token ranges were 244,561-322,369 native and 62,799-70,794 baseline; B16
ranges were 471,075-635,301 and 96,052-154,251. Input totals include cached
context; cached and reasoning tokens are not added again. These are not billing
ratios. Client time includes startup, authoring and tool work, not just engine
execution. Complete engine/model call counts, traffic, retries, first independently
verified preview and engine-only memory remain unknown. Client-tree memory is a
separate observation. Both tasks remain losing tasks under the fixed token policy.

### Comparison with the earlier native batches

The earlier B03 and version-2 B16 batches used the same prompts, client, model and
settings. Both already passed 5/5. They ran on different revisions and at different
times, so this is an observational comparison, not randomized causal attribution.

| Task | Earlier / current median tokens | Change | Earlier / current median seconds | Change |
| --- | ---: | ---: | ---: | ---: |
| B03 | 349,212 / 300,182 | -14.0% | 128.9 / 111.2 | -13.7% |
| B16 | 584,833 / 574,154 | -1.8% | 112.9 / 160.9 | +42.5% |

The visible error inventory finds fewer schema-error occurrences: B03 shell
outputs fall from six to three, plus two earlier MCP errors and none currently;
B16 shell outputs fall from two to zero. These count distinct error codes per
completed output event with a complete JSON envelope. Repeated reads can repeat
errors, truncated outputs are excluded, and the transport mix differs. They are
not complete engine-call or retry counts. All ten current native attempts use
CLI; one earlier B03 attempt mixed CLI and MCP. Full-schema and broad capability
requests remain, alongside path and request-field mistakes.

Retain the working nested selector contract, but stop broadening discovery under
the recorded stop condition. The mixed time/token signal and missing call metrics
do not justify a general efficiency claim. Address demonstrated request-field,
path and snapshot/reference friction separately. B19/B20 prompt and controller
guidance are separate versioned follow-ups; none of their previous failures changes.

### Conditions and retained evidence

Both current arms used `d34851ef5ec8f43acf4457826c6fa407f5d36189`, unchanged B03
version 1 and B16 version 2 prompts, Codex CLI 0.160.0 and the same externally
configured `gpt-6.1-sol` medium settings. Model names remain evaluation metadata,
with no engine or harness default. The current driver's only change from the
earlier driver grants a bridge directory for B19/B20; neither of these tasks gets
that bridge. Baseline tools remain pinned resvg 0.47.0 and Pillow 12.3.0.

Native attempts ran before baseline attempts, sequentially on the shared Windows
host, with rotating task order. This chat ran no concurrent local engine checks
or benchmarks. Other host workloads were uncontrolled and caches could be warm.
Both reports confirm unchanged inputs. Every completed direct command and final
retained Python helper was reviewed; no prohibited repository/judge reads, other
engine or additional model access was observed. No image-view tool was observed.
Numeric pixel/font/hash checks do not establish visual review or authenticate
every intermediate helper version and nested operation.

All 715 raw files under the external
`w5-nested-discovery-sol-{model,baseline,comparison}-five-01` roots are hashed in
`w5-nested-discovery-complete-hashes-01.json`. Earlier per-trial inventories were
rechecked unchanged. Companion review and summary records retain all twenty
attempts. The comparator finds no matching issues; `actual_model_benchmark_complete`,
`matched_model_baseline_complete`, `decision_ready` and `matched_cutbolt_comparison`
remain false. No checkpoint credit changes.

| Evidence | SHA-256 |
| --- | --- |
| Source candidate | `4626af3ad8a6023683a54d9cf441d3dd83c81b93d547b429979675da91027081` |
| Release executable | `c4e06dff137c3c710b9837f0d02900b0b5243f732092ca4d0706cb7791b9f281` |
| B03 prompt | `3e72bb258a2b271bf6722bd290bc8c2e481b31c905c0dd9e085d86fbab9c4c3d` |
| B16 prompt | `f3cf3d806e477b57d847130050c063be0636ed53d207cfe756ec78d9ef0abd85` |
| Native report | `589aa15b08e57691db94879d42bcb81ebfccaaf179b6a24ee625a8d9521614d1` |
| Baseline report | `f3172498f91405b221d34422f101db2412826e499cc628e3cd25cb635c8cf8d7` |
| Comparison report | `4caa8a2bef19610db1b9d287164c00ee91333e2d4236c799c229e4ad13951cae` |
| Raw evidence inventory | `2306d4b69eef8c6814d8b0a6fcb48a8335382a8984513daafed2fe23a5fbc842` |

## B19/B20 at 1d5b960: guidance pilots and observation corrections

One native B19 and one B20 attempt per arm used prompt versions 4 and 3,
respectively, with the same external Codex CLI 0.160.0 / gpt-6.1-sol medium
configuration as the preceding trials. Model selection remains external
evaluation metadata. Source and executable identities stayed unchanged.
All three runs have accepted model evidence and no driver failure; B19's
baseline remains not applicable.

B19 passed five checks, including all four artifact/source checks, and failed
four engine checks. The agent manually wrote `attempts.json`; fifteen fields
across seven retained objects differ from actual bridge replies, all process
creation integers. For example, `134364244084953616` became
`134364244084953620`. The raw command outputs retain the exact integer.
The evidence locates the mismatch at the saved objects but does not establish
which hidden client/model step introduced rounding. Keep the failure; exact
process identities cannot be relaxed. Next measure programmatic preservation of
returned objects without manual reconstruction. The run used 1,586,239 total
tokens, 31 engine commands and 237.93 seconds, with a verified preview at 97.52s.

B20 originally failed both arms because of judge defects. The native agent read
the current consumer head immediately after relinking; its actual response was
revision 2, but role lookup demanded an explicit revision argument. The baseline
retained unchanged `inspection.json` files inside both deliveries; the judge
mistook the extra files for changed required files. The corrected judge binds
head reads to the observed revision and pre-undo order. Both arms still require
every mandatory file, and now check every additional observed file for unchanged
bytes as well. Wrong revisions, late reads, missing or altered files still fail.

Rejudging copied, unchanged captures passes all sixteen native checks and eight
baseline artifact/source checks; eight baseline engine checks remain not
applicable. No agent reran, no output was repaired, and original failures remain
retained. Solve metrics and controller captures match the originals exactly:

| B20 arm | Total tokens | Agent seconds | Combined engine commands | Verified preview time |
| --- | ---: | ---: | ---: | --- |
| Inkbolt | 978,624 | 184.50 | 57 | Unknown |
| Baseline | 287,125 | 131.43 | 19 | Unknown |

This one-pair artifact tie at 3.41x tokens is a pilot, not repeated acceptance or
evidence of a reliability advantage. It does not replace or pool with the older
five-pair prompt. All 98 completed trace items and fourteen retained Python
helpers were reviewed. No prohibited repository/judge reads or additional engine
or model access was observed; numeric image checks do not establish visual review.

The original 957 files are retained under `w2-bridge-guidance-`; the 329 rejudge
files are under `w2-handoff-observation-rejudge-`. Both source inventories were
checked unchanged. Focused regression/lifecycle/verifier checks passed on Windows
in 66.1s (40 Python tests) and WSL in 18.3s (30 executed, ten explicit Windows
process skips), with seven fresh stages each and no failures or pending checks.
This does not establish full W2, current full-suite acceptance or checkpoint credit.

| Evidence | SHA-256 |
| --- | --- |
| Original source candidate | `d8f5ce14e0a3c7d81a2d6f1d9db7e7f37314ffa8cd4ea8f4d33329a61068f3c9` |
| Release executable | `c4e06dff137c3c710b9837f0d02900b0b5243f732092ca4d0706cb7791b9f281` |
| Original complete review | `7f15837ce015378732f2313a09e699d7e6aeb8ea35996f7795c2c2be48b9731c` |
| Rejudge review and inventory | `1c9fa7a6ae595b7bebb52faa511cfb802627cde3337dbbcf7d5657ce0cc67753` |
| Native rejudge report | `c458908a0be842bf22f6dad19e848796287e7f68185d05297e39c0aa4d68ba85` |
| Baseline rejudge report | `9c80c63efc3f145df69cefead42210f6d8ada8fd6af74b07d68f86e0526f757b` |
| Focused verification inputs | `e35f8374bc7040c22a69e77b14ecc0753413a94f2d29622b223b0d8e6223fa92` |

## B19/B20 at f61d952: recovery pilot and five-pair handoff follow-up

B20's prompt-3 follow-up passes **3/5 native workflows versus 5/5 baseline**
after a tested judge correction. Original full-workflow scores were 1/5 and 5/5;
artifact success was already 3/5 and 5/5. Repetitions 2 and 3 attempted a different
stale mutation, as the prompt permits, but the original judge additionally
required the relink's operation list. The corrected check requires a nonempty
mutation of revision 1 in the same saved project/store and the actual recorded
`REVISION_CONFLICT`. Exact retry still repeats the entire relink request and
returns its saved receipt. Undo, restored snapshots and history checks remain.

All ten captures were imported and rejudged without launching a client or
repairing artifacts. Original solve metrics and all 4,171 original evidence files
were checked unchanged. The new reports retain the two remaining native failures:
attempts 4 and 5 changed `/variants/base/1/value` from `true` to `false` in the
required source base. This violates exact source/history preservation.

The judge now checks delivery-file preservation independently of the source and
pixel comparisons. It reads the required names and hashes from each delivery's
inventory, then rehashes every file observed at compilation, including optional
diagnostics. Previously a source mismatch stopped the inventory collection.
Rechecking this one criterion against the ten original captures passed for all
112 observed files. It corrected the file-preservation result for native attempts
4 and 5. Both still fail the editable-source checks, so workflow scores stay at
3/5 for Inkbolt and 5/5 for the baseline. The retained recheck report has SHA-256
`f853787f3329ff81bb01affc9a23704eee63f48aeac92e606fbc2bc03244d3a1`.

### Outcomes and costs

Both arms retain eight artifact/source checks. Eight additional native engine
checks remain not applicable in the baseline. Every attempt, including failures,
is included in the following distributions; no earlier pilot or prompt is pooled.

| Measurement | Inkbolt arm | No-Inkbolt baseline |
| --- | ---: | ---: |
| Artifact and complete applicable workflow success | 3/5 | 5/5 |
| 95% Wilson interval for artifact success | 23.1%-88.2% | 56.6%-100% |
| Median input + output tokens | 1,065,545 | 280,910 |
| Token range | 768,825-1,664,926 | 237,737-357,983 |
| Median client execution, seconds | 209.790 | 115.934 |
| Client execution range, seconds | 185.140-263.562 | 100.889-120.825 |
| Median combined bridge engine commands | 60 | 19 |
| Median bridge request / response bytes | 43,922 / 588,125 | 7,426 / 111,580 |
| Median combined bridge retries | 1 | 0 |
| Median Inkbolt process peak commit, bytes | 11,239,424 | Not applicable |
| Median consumer job-tree peak commit, bytes | 110,239,744 | 110,579,712 |
| First verified preview, median seconds | 140.779 (4/5 observed) | Unknown |

Native median token use is 3.79x baseline; median client time is 1.81x. Cached
and reasoning tokens are not added again, and token ratios are not billing
ratios. Time includes client startup and tool work. Native attempts 1, 2 and 5
also invoked the configured encoder/probe directly for read-only media checks;
these are included in client time but outside bridge command/traffic accounting.
Memory scopes are distinct, underlying model-call counts remain unknown, and
first useful preview remains unknown in every attempt. Five trials establish
neither statistical equivalence nor a general reliability or efficiency claim.

The separate B19 prompt-5 pilot programmatically preserved returned objects and
passed all nine independent artifact/recovery checks. It nevertheless failed the
protocol gate: a schema lookup put `command` inside `arguments`, where that field
is reserved for the message envelope; the lookup expects `name`. The retained
error is `Command and step belong at message level, not in arguments`. Later
successful calls cannot erase it. `model_trials` remains false and accepted solve
metrics remain unavailable. No larger B19 batch followed; its baseline is not
applicable.

### Conditions, review and next work

The eleven original attempts used frozen commit
`f61d952f7733ca80eaf75ca377ce5a96d8e14043`, B19 prompt 5, B20 prompt 3 and the
same externally configured Codex CLI 0.160.0 / `gpt-6.1-sol` medium settings
with a 600-second per-trial limit. Model selection remains evaluation metadata,
with no engine or harness default. The baseline used pinned resvg 0.47.0,
Pillow 12.3.0 and Python 3.11; both B20 arms shared the pinned video consumer.
The recovery pilot ran first, then five native and five baseline B20 attempts.
The shared Windows host had no concurrent engine verification from this chat;
other host work was uncontrolled, caches could be warm and order was not randomized.

Completed direct commands and available helper bodies were reviewed. Native
attempt 1 deleted five helpers and baseline attempt 3 deleted `build_delivery.py`;
their bodies are absent from the capture, so nested behavior cannot be fully
audited. Native attempt 4 deleted nineteen helpers, but their inline constructions
were retained and reviewed. No repository/judge reads or additional model use
were observed in available commands/helpers. No image-view event was observed;
numeric pixel/hash checks are not visual review. Capture hashes neither
authenticate hidden behavior nor establish a filesystem security sandbox.

The fixed comparison policy flags B20 as losing on artifact success. Keep its
source-preservation and overhead findings open, along with B19 protocol usability.
Proceed to W3a.3 embedded SVG styling under the existing input-admission priority,
without claiming CSS caused these failures. Further prompt tuning is not the next
substantial stream. Full-suite, matched-baseline and separate sister-project
comparison gates remain false; engine checkpoint credit is unchanged.

Focused checks passed in 54.7s on Windows (39 executed, three optional baseline
skips) and 18.3s on WSL (31 executed, eleven Windows-process skips). A separate
Windows run with both real tool configurations passed all six external lifecycle
tests without skips in 53.2s, covering the previously skipped baseline checks.
All stages were fresh with no failures or pending checks. The real consumer test
verifies a different stale mutation while retaining undo/history/exact-retry checks.
These are focused harness checks, not fresh full-engine acceptance.

Original evidence is retained under `w2-recovery-record-pilot-01` and
`w2-handoff-followup-{model,baseline,comparison}-five-01`; the complete review
inventory binds all 4,171 files. Rejudging uses separate
`w2-handoff-stale-rejudge-{model,baseline,comparison}-01` roots, with 1,529 files
in its review inventory. Both sets remain available externally.

| Evidence | SHA-256 |
| --- | --- |
| Original source candidate | `185dbec33e8f9de49afe1679023742011bae4e6b31c66028d20f5fee49e87bbc` |
| Release executable | `c4e06dff137c3c710b9837f0d02900b0b5243f732092ca4d0706cb7791b9f281` |
| B19 prompt 5 | `7752a6b12ca4748875418f211a375c42b123b8f222907b1a915712928ef64892` |
| B20 prompt 3 | `debb75263f2202141f93412d3aeb44206cc2af26f6fe82f22f7995fe72b52e9e` |
| Consumer executable | `3d9aa4644525c84108b9ec276605595e3d115b6d1fc8d4523b7a48a934f5f536` |
| B19 pilot report | `9c61c42bd96d6926a32263a6760d667b356c7839a2ccbe7e0ce0f64c167d7626` |
| Original native report | `ab22c222f75f4b559748e4f28ae3bafb64f285e81df1b5ffbda65ff8f7612594` |
| Original baseline report | `5406a06be71ed622e367204199f94187ba046ef0cd85f61d6b2ba5919a781f08` |
| Original comparison | `93ea37b5c4022c8fa6b84065319635f842b43fca20591dac4eb6802613c4ee44` |
| Original complete review | `5c1ff14395744ede1a8493bd4cd10ee90650879b079d7ee939c35b8868e6f792` |
| Rejudge candidate / focused verification inputs | `f2f7d412de0c52a035f48c6b70dabade35af153d5dd3dfc0240b930733d24014` |
| Rejudged native report | `088cfed0e9e06b84f051725556631d967253a3324e186b8ad8528bf13cc8fffa` |
| Rejudged baseline report | `cc5cea6a47832dfdeebe1325cd02855aa19da9eeb91d1b5ab5a042e29eff8e40` |
| Rejudged comparison | `85b6f4ebf72aa7eed18dbc6a1bac159f6f360b8114f794f1e8911f5f822a0cea` |
| Rejudge integrity report | `03041604a8a915ebce3136e20247e4371e9af06db2b9efa692a9f05a3c90c8d4` |
| Rejudge review inventory | `be67b2bd3a303df954c6d8d654b40ee80b65f295dd3e72346ea6e8092ece160e` |

## B10/B17/B19 at 447bbc2: request-guidance follow-up

The B10 counts below record the original judge. Reopening the same captures
with their recorded tile stores gave 5/5 for both arms. [Corrected B10 results](#b10-rejudging-the-saved-photo-stores)

Five native attempts per task and five B10 baseline attempts used unchanged
prompts (B10/B17 version 1, B19 version 5) and the same external Codex CLI 0.160.0
configuration, `gpt-6.1-sol` with medium reasoning. These are evaluation settings,
with no engine or harness model default. The native task order rotated over five
repetitions, followed by the baseline batch. The shared Windows host had no
concurrent local engine checks from this chat; other work was uncontrolled and
caches could be warm. Both arms report unchanged source and tool identities.

| Task | Accepted artifact passes | Complete workflow passes | Median input + output tokens | Median client seconds |
| --- | ---: | ---: | ---: | ---: |
| B10 native photograph repair | 3/5 | 3/5 | 580,184 | 128.3 |
| B10 no-engine baseline | 5/5 | 5/5 | 75,230 | 63.7 |
| B17 lost response | 5/5 | 4/5 | 194,428 | 76.4 |
| B19 interrupted output | 4/5 | 4/5 | 569,666.5 (4 observed) | 119.7 (4 observed) |

B17/B19 have no applicable baseline. They were omitted from the baseline
selection, so the comparison preserves that selection issue and does not form
pairs for them. B10 has five matched pairs and no identity issues. Its fixed
comparison policy flags lower artifact success; only three pairs succeeded in
both arms, so no token/call cost ratio is awarded. All-attempt medians include
failures where usage is observed. The 95% Wilson intervals are 23.1%-88.2% for
3/5, 37.6%-96.4% for 4/5 and 56.6%-100% for 5/5; these small samples do not prove
equivalence or general reliability.

### Failures and observed repairs

B10 attempts 2 and 4 received the new missing-`store_root` guidance, then chose
a custom `tiles` store instead of restoring workspace defaults. The required
immutable-base/root contract fails; the independent renderer cannot find pinned
tiles at the required root. Downstream sample, preview, history and memory
checks remain missing. Model-written sample checks do not supply that credit.
Attempt 5 also encountered missing-field guidance and restored the workspace
option successfully. B10 remains 3/5, the same count as its earlier five-attempt
batch. This 2.07 MP task does not establish the larger W4 workload target.

All five B17 attempts encountered missing-`session_root` guidance and subsequently
restored the workspace option. Every independent artifact check passes. Attempt
4 saves CLI envelopes where the prompt requires compact result objects; two
receipt/retry checks therefore fail. The earlier workflow count was 3/5 and its
median tokens/time were 269,176/94.6 seconds. Current counts and medians are
descriptive: intervening engine changes and five attempts do not isolate the
effect of diagnostics.

B19 attempt 1 passes all nine independent checks but violates the controller's
required operation order before the corrected recovery sequence. It remains a
failed protocol/model trial, receives no accepted artifact credit and has unknown
accepted usage. Attempts 2-5 pass the complete workflow. Attempt 5 repairs a
missing `name` in `schema.lookup` with a subsequent `name:"session.create"`
query. The earlier prompt-5 run was one failed pilot, so it cannot serve as a
five-attempt before/after control.

Across these five B19 captures, four agents first tried `op:"fill"` on the
vector badge. The build rejected the edit, and all four then resubmitted its
geometry with `op:"vector"`. Attempt 1 also requested interruption before
the corrected edit succeeded. Source builds now let an agent change just the
vector fill. The 4/5 result above belongs to the evaluated build.

The four accepted B19 attempts have median 30 observed engine commands, 2.5
invalid calls, three retries, 3,636.5 request bytes, 342,539 response bytes and
61.6 seconds to a verified preview. These measurements exclude judge work.
Their median maximum individual engine-process commit is 84,566,016 bytes;
it is not a concurrent sum or client-tree total. B10/B17 engine calls, traffic,
retries, preview timing and engine-only memory remain unknown. All ten B10
client/tool trees have captured process peaks below 256 MiB; the two failed
native workflows still receive no completed memory-check credit. Underlying
model-call counts remain unknown for every attempt.

### Evidence and decision

The comparison reader validated retained requests, client results and transcript
identities without changing a judge or rerunning a model. Manual review covered
reported failures and missing-field repair sequences; a separate inventory
records all completed event types and retained helper hashes. This is not a
complete audit of every helper version or authenticated hidden behavior.
No image-view event appears in the native event inventory; numerical checks do
not establish visual review. Source preservation and independent artifact
checks retain their original criteria.

Retain the bounded missing-field contract and stop expanding this diagnostic
approach on the present evidence. It repairs individual requests, but the batch
does not establish the W5 acceptance requirement of fewer tokens and calls per
successful task without correctness loss. Storage-context and receipt-format
workflow failures, missing metrics, the full twenty-task run and the separate
sister-project comparison remain open. No original engine checkpoint gains credit.

The complete external inventory binds 2,897 files across both arms, their
comparison, the recorded evaluation plan, process exits and review. Every listed
file hash was reread. Source commit `447bbc2e632936f23567552375ec922856e84314`
also passed fresh complete Windows/Linux implementation acceptance before these
trials; that acceptance is separate from model usability.

| Evidence | SHA-256 |
| --- | --- |
| Source candidate | `29c47929d8119c4d984e58664644374390f6ad95d916c83d2981d8fb4800b0af` |
| Release executable | `2b5a6275cb502d4fd31797d990a5b05e409dd3a5f33736356223fe615bac9ad2` |
| Native report | `cc35b8ae41d13128e9967d483dff758f22cd2c90b420c539e6474d0f9c1f6d3d` |
| Baseline report | `5286cf6527ccfb7d4311c23ef19a4000942e9dff39d99df41a7b5c217f402e83` |
| Comparison | `477c6ab2d5113ee6187db773a18b58ab1409a2d1f9e48404b57a5e8ff87fb0a6` |
| Review of failures/repairs | `f7d2155bd39665c8fb3c5ae023dd2c7161cceb00afee0db8300f3df169118470` |
| Complete file inventory | `8cd4ca7dfda26d227f02944d7f847b1df2e5aea005dfc69ad19087966e17e7ce` |
| Windows/Linux implementation audit | `a9935f43fa7275af45c539081a34af28b04714ecd7963de2fc3b67db3ab17e71` |
