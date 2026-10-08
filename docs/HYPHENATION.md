# Discretionary break inspection

`text.hyphenate` computes reproducible break opportunities from explicitly supplied rules. It is a read-only library, JSON CLI and MCP stdio operation. It preserves exact input tokens and reports source scalar offsets, grapheme boundaries and diagnostic segments. [Shared stories](STORIES.md) now use these same rules to select and render hyphenated lines through frames/columns, alongside structural lists and saved history. Inspection alone does not change layout.

## Rules

Each pattern has `text`, `weights`, and optional `at_start` / `at_end` booleans. `weights` has one integer in 0 through 9 per Unicode scalar gap, including the outside gaps. Every matching occurrence contributes weights; the maximum at a gap wins. Odd maxima permit candidate breaks; even maxima suppress them. Anchors restrict matches to the whole token's beginning or end. Overlapping matches participate. Duplicate and reordered patterns have the same matching behavior.

The original implementation follows the weighted-pattern principle in [Liang's published research](https://tug.org/docs/liang/) and [the primary account of competing patterns](https://tug.org/tugboat/tb27-1/tb86nemeth.pdf). The structured rule format, validation and inspection interface are Inkbolt's. No dictionary, external implementation, application data or language-specific accuracy claim is bundled.

`case` defaults to `exact`. Explicit `ascii_lower` changes ASCII uppercase letters only during matching. Patterns and exception keys must already use canonical case. Original strings remain unchanged. There is no implicit Unicode case folding, language selection, locale lookup or normalization; composed and decomposed strings can match different patterns. Callers supply selected tokens, not unsegmented paragraphs. Digits and punctuation are literal characters with no parser syntax.

`exceptions` maps canonical tokens to strictly increasing internal scalar offsets. An exception replaces all pattern candidates for that token; an empty array disables automatic breaks. Exception positions must lie on extended grapheme boundaries. Both exception and pattern candidates are filtered by `min_left` and `min_right`, each in 1 through 128 **graphemes**, defaulting to 2. Minima refer to the complete token, not successive segments. Candidates inside a grapheme or too near an edge remain visible in diagnostics but cannot appear in `breaks`.

[hyphenate.json](../examples/hyphenate.json) contains original synthetic tokens and illustrative rules, not a language dictionary.

## Results and preservation

The result contains `rules_sha256`, `indices:unicode_scalars`, `minima_units:extended_graphemes` and ordered `words`. Each word reports:

- `word`: exact source; `matching_word`: the matching copy.
- `source`: `patterns` or `exception`.
- `weights`: maxima at every scalar gap, or `null` for exception overrides.
- `candidates`: internal odd-weight gaps or the complete exception list.
- `grapheme_boundaries`: source boundaries including zero and end.
- `breaks`: candidates passing grapheme and minimum checks.
- `parts`: original text split at **all** eligible positions, without inserted hyphens. These are diagnostics, not a selected multiline layout.

The SHA-256 covers UTF-8 compact JSON serialization of validated `Rules`: fields `case`, `min_left`, `min_right`, `patterns`, `exceptions`, with defaults materialized; pattern fields `text`, `weights`, `at_start`, `at_end`; exception keys sorted. It identifies declared rule data, not linguistic quality or mathematical equivalence. Pattern order and duplicates can change the hash without changing opportunities.

An empty input array validates and fingerprints rules. No files are read or written except explicit cancellation marker checks. No font, document or network access is needed. Compiled rules own their values and can be reused without retaining the previous batch's work count. Errors discard the complete result.

## Limits

| Resource | Maximum |
| --- | ---: |
| Patterns | 32,768 |
| Scalars per pattern | 64 |
| Total pattern scalars | 262,144 |
| Exceptions | 4,096 |
| Total exception scalars | 65,536 |
| Scalars per token or exception key | 256 |
| Tokens per batch | 256 |
| Input scalars per batch | 4,096 |
| Matching edge/weight work per batch | 4,194,304 |

The existing 1 MiB CLI request limit may reject rules before library limits. Aggregate limits also apply to direct library calls. Compilation and matching check cooperative cancellation and deadlines. Invalid rules return `INVALID_HYPHENATION`; work/storage limits return `RESOURCE_LIMIT`; transport limits and strict JSON retain their existing codes.

Empty tokens, whitespace, control characters, bidi controls, soft hyphens and U+FFFE/U+FFFF are rejected. Joiners and combining marks may participate in graphemes. This matcher does not implement Unicode line-breaking rules. Dictionary file formats, spelling-changing hyphenation, discretionary input characters and automatic dictionary selection remain unsupported. Language dictionaries are caller-managed external data with retained licenses. The story renderer performs Unicode word segmentation and explicit visible-hyphen placement under the separate [story contract](STORIES.md).

The distinction between break opportunities, selected lines and language-specific visible changes is described in [Unicode line breaking, sections 5.3–5.4](https://www.unicode.org/reports/tr14/tr14-53.html#SoftHyphen). Story token selection uses the pinned Unicode segmenter's lexical words; [Unicode text segmentation](https://www.unicode.org/reports/tr29/tr29-45.html) describes the broader boundary model. Inkbolt's explicit greedy fit, temporary display source and generated-glyph provenance are original integration choices; no general line-breaking conformance or dictionary quality is implied.
