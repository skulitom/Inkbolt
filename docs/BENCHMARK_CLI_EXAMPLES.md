# Focused CLI examples: text-repair evaluation at d18ac62

Five fresh B16 attempts passed every applicable check with Inkbolt, as did five
no-engine baseline attempts. Inkbolt's median input-plus-output token count was
**377,956**, 35.8% below the preceding essentials batch's 588,300. It still used
**2.94x** the fresh baseline's tokens. This is a descriptive result for one task,
not a causal or general efficiency claim; full W5 acceptance remains open.

## Setup and retained attempts

The hypothesis was recorded before implementation: expose small, complete
examples through focused schema lookup and put workspace defaults in CLI help
to reduce the discovery work observed in text repair. The seven examples and
their bounds are described in [tool discovery](AGENT_DISCOVERY.md).

The 26 October 2026 evaluation used clean source
`d18ac628f35f63bf3f75f4480dc49da69b55d9ef`, with no source or Git changes during
either arm. Five engine attempts ran before five baseline attempts on the same
Windows desktop. Both arms used externally configured Codex CLI 0.160.0,
`gpt-6.1-sol`, medium reasoning and the essentials catalog configuration.
These are evaluation choices; the engine requires no model and the driver has
no model default. The baseline used pinned resvg 0.47.0 and Pillow 12.3.0.

An earlier batch retained five setup failures: the globally installed client had
updated to 0.164.0, so the exact-version check rejected every launch before any
model ran. Those failed reports and fixtures remain in `cli-examples-evaluation-01`.
The retry used a separate 0.160.0 installation whose executable hash exactly
matches the previous evaluation's client. Only the executable path changed;
the global installation, model settings, task prompt, fixtures and judges did
not change. All ten genuine attempts remain in `cli-examples-evaluation-02`.

No concurrent Inkbolt verification or second benchmark client ran during the
trials. Other host activity was not isolated, caches could be warm and order
was not randomized. Fresh Linux acceptance and retained Windows acceptance of
identical engine sources are recorded in [development status](DEVELOPMENT_STATUS.md#implementation-and-retained-checks-26-october-2026).

## Results

[B16](../tools/benchmark_prompts/B16.md) requires diagnosis of text overflow,
changing only the frame width, reviewing the repair and delivering exact pixels
while preserving the original font and license. Inkbolt additionally retains
the reviewed proposal, committed revisions and durable publication receipt.
Baseline engine-only checks are not applicable.

Tokens include input and output, counting cached input once; they are not billing
ratios. Seconds measure client execution, including startup and tool work.

| Batch | Artifact passes | Applicable workflow passes | Median tokens | Token range | Median seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Focused examples at d18ac62 | 5/5 | 5/5 | 377,956 | 346,235-430,131 | 98.75 |
| Fresh no-engine baseline | 5/5 | 5/5 | 128,438 | 94,744-168,775 | 71.92 |
| Prior essentials at 81e8830, separate batch | 5/5 | 5/5 | 588,300 | 456,983-677,439 | 120.36 |

The unchanged [comparison policy](BENCHMARK_COMPARISON.md) accepts the five
current pairs without identity issues and retains B16's losing-task signal:
the baseline matches artifact success with less than half the median token use.
The preceding batch is context only and is not pooled with the current trials.
Each 5/5 rate has a 95% Wilson interval of approximately 56.6%-100%, assuming
independent trials. These samples do not prove equivalence or causation.

## Trace findings and decision

All five engine attempts chose the CLI, with zero MCP tool-call events. Every
attempt received example fields and workspace defaults in captured output.
That establishes delivery, not how much any example influenced the model.
Median completed shell events fell from 16 to 12; the median count of shell
events containing schema lookups stayed at five. Individual shell events can
batch many engine requests, so these are not complete engine-call counts.

Two attempts first omitted the workspace setting and recovered. Script syntax,
shell parsing and font-inspection assertion failures also remain in the traces.
All ultimately passed the unchanged independent judges. The baseline's recovered
script/render failures remain too. Captured file inventories still match every
workspace; command traces and retained scripts show no repository/judge reads,
other-trial access, network calls or delegation. Hashes identify evidence and
do not authenticate client behavior.

Keep these bounded examples and workspace guidance. Do not expand examples
indiscriminately: repeated schema queries and missed workspace selection remain
visible, and broad operation coverage still needs evidence. The next usability
increment should address a demonstrated setup or interaction failure and retain
the same remeasurement and stop conditions. Further catalog deferral stays paused.

Complete model/engine-call counts, traffic and first verified preview time remain
unknown. Client-process memory does not establish engine-only memory performance.
Full-suite, smaller-model, MCP-specific and sister-project evaluations remain
separate gates. This partial run leaves `actual_model_benchmark_complete` and
`decision_ready` false and awards no engine checkpoint or whole-goal completion.

## Evidence identities

The 993-file archive matches source fingerprint
`84e828761576d331826052f0da0bccb1544eeb13f5dcf76b3946cda91e554f24`.
The retained optimized executable is
`af11b96c53eda9f82b7f73e9a2c61641f18ee806aa0a4e4f3438fb83f2f97652`.
The pre-implementation hypothesis hash is
`7003b877a4bfb3d61ab866a1b3c7f5142ee71d5986269cd8afd7c3b1d88aa99f`;
the retry plan hash is
`118df210e8d41076607a06cf8d9ecbd0132f055fae9403a479884372d9ec2d54`.

| Retained report | SHA-256 |
| --- | --- |
| Engine | `c5b3121f4e24ac038cb63061da0578e101af03089f9c9e0a7028b9bdac5c5bd7` |
| Baseline | `66b8ea637744ce2b23b7bf5f2982fec8573545b3666d6a9d2f52529b702e065c` |
| Matched comparison | `69da083090d841de9fec2b6e68b04dc9622c6574ad15e28a34cd62687716bbd7` |
| Source, configuration and capture audit | `dcb4f229ccc7fdc1dd5738dc26bc068f593d8b22fb10ee7b3c9838afd92ca1ba` |
| Trace-count audit | `e025239aabc25ff3a0da8c49161e621a8198d86464827bf4cf445d5985880736` |
| Manual review record | `3feeab1b0334511de5a5bd4931e4f7b02fe5dccce81d7deb786f719a39538dcb` |

The first supplementary audit helper incorrectly required identical complete
arm contracts. Its correction requires exactly the expected arm, engine and
baseline-tool differences and equality of every shared field. Both helper
versions and the failure record are retained. No judge, result or comparison
policy changed during that correction.
