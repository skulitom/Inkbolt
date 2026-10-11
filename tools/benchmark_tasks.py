"""The unchanged readiness tasks; implementation and measurement are separate."""

SUITE = 'agent-tasks-v1'
# These outcomes are copied from the accepted readiness plan. An absent adapter
# remains a visible not_implemented result, never a reduced benchmark denominator.
TASKS = {
    'B01': ('Create a labelled diagram', 'Correct objects, labels and geometry; editable sources'),
    'B02': ('Produce an aligned icon sheet', 'Stable IDs, expected spacing and independent artboards'),
    'B03': ('Revise one object in a large layout', 'Intended object changes; unrelated state/output retained'),
    'B04': ('Import and revise vector artwork', 'Required structure retained; declared losses; source bytes intact'),
    'B05': ('Recolor a shared palette', 'All intended dependents change; unrelated paints unchanged'),
    'B06': ('Correct linked-frame text overflow', 'Reading order, content and font identity preserved'),
    'B07': ('Produce multilingual typography', 'Correct glyph/cluster order and bounded visual reference error'),
    'B08': ('Select and mask a foreground region', 'Expected coverage with retained source pixels'),
    'B09': ('Retouch a local image defect', 'Independent numerical/region checks and unaffected pixels'),
    'B10': ('Edit a multi-megapixel photograph', 'Native precision/editability within memory budget'),
    'B11': ('Revise a mixed masked/effect document', 'Composition and resource identity preserved'),
    'B12': ('Generate a family of layout variants', 'Correct bindings and independently verified output sizes'),
    'B13': ('Deliver transparent screen artwork', 'Correct alpha, color, dimensions and no unintended matte'),
    'B14': ('Deliver a print page', 'Correct physical boxes, profiles, inks and declared losses'),
    'B15': ('Recover missing or changed resources', 'Actionable diagnosis; explicit content-checked repair'),
    'B16': ('Repair a seeded layout/export problem', 'Inspect, propose, preview and apply without collateral changes'),
    'B17': ('Recover a lost editing response', 'Original receipt; no duplicate operation'),
    'B18': ('Resolve conflicting writers', 'Stale proposal rejects; reviewed replacement preserves intent'),
    'B19': ('Cancel/interruption/restart during output', 'No partial final file, overwrite or duplicate publication'),
    'B20': ('Revise a linked graphic used by Cutbolt', 'Pinned manifest, explicit revision, correct alpha/color/timing'),
}

# Required independent checks are separate from a solver's return value.
CHECKS = {
    'B01': ('diagram-structure', 'font-identity', 'diagram-pixels', 'editable-source'),
    'B02': ('sheet-structure', 'board-0-pixels', 'board-1-pixels', 'board-2-pixels', 'editable-source'),
    'B03': ('only-target-changed', 'large-layout-pixels', 'historical-pixels', 'history-valid'),
    'B04': ('imported-structure', 'declared-losses', 'revised-pixels', 'editable-source'),
    'B05': ('live-dependencies', 'palette-pixels', 'historical-pixels', 'history-valid'),
    'B06': ('original-overflow', 'reading-order', 'retained-source', 'flow-pixels', 'historical-flow', 'history-valid'),
    'B07': ('glyph-cluster-order', 'editable-text-and-font', 'typography-pixels', 'history-valid'),
    'B08': ('selection-coverage', 'retained-pixels', 'masked-pixels', 'historical-pixels', 'history-valid'),
    'B09': ('exact-local-repair', 'repaired-pixels', 'historical-pixels', 'history-valid'),
    'B10': ('native-import', 'editable-exact-patch', 'photo-preview', 'edited-native-samples',
            'historical-native-samples', 'undo-editability', 'redo-editability', 'immutable-tiles', 'history-valid', 'memory-budget'),
    'B11': ('composition-retained', 'resource-identity', 'mixed-pixels', 'historical-pixels', 'history-valid'),
    'B12': ('wide-pixels', 'square-pixels', 'tall-pixels', 'variant-bindings', 'base-preserved', 'outputs-preserved', 'history-valid'),
    'B13': ('transparent-pixels', 'screen-color', 'editable-source', 'no-overwrite'),
    'B14': ('print-preview', 'physical-boxes', 'profile-identities', 'native-inks', 'declared-losses', 'editable-print-source', 'history-valid'),
    'B15': ('located-diagnostics', 'verified-replacements', 'unchanged-artwork', 'repaired-pixels', 'old-bindings-preserved', 'history-valid'),
    'B16': ('seeded-diagnosis', 'no-collateral-edits', 'repair-pixels', 'preflight-delivery', 'history-valid'),
    'B17': ('original-receipt', 'retry-idempotent', 'edited-pixels', 'undo-preserved', 'history-valid'),
    'B18': ('stale-rejected', 'both-intents-preserved', 'conflict-pixels', 'historical-pixels', 'history-valid'),
    'B19': ('review-pixels', 'active-cancellation', 'interrupted-unpublished', 'recovered-pixels',
            'revision-resource-pinning', 'single-publication-no-overwrite', 'no-partial-final', 'history-valid'),
    'B20': ('delivery-0-pixels-clock', 'reviewed-source-only', 'revised-preview', 'delivery-1-pixels-clock',
            'pinned-successor', 'no-implicit-relink', 'explicit-consumer-revision', 'consumer-undo-retry',
            'original-timeline', 'revised-timeline', 'undone-timeline', 'old-source-history',
            'immutable-deliveries', 'history-valid', 'consumer-processes'),
}

# These are scored identically across arms. The complementary engine list is
# explicit too: adding a check requires a classification decision, not a default.
ARTIFACT_CHECKS = {
    'B01': ('diagram-structure','font-identity','diagram-pixels'),
    'B02': ('sheet-structure','board-0-pixels','board-1-pixels','board-2-pixels'),
    'B03': ('only-target-changed','large-layout-pixels'),
    'B04': ('imported-structure','declared-losses','revised-pixels'),
    'B05': ('palette-pixels',),
    'B06': ('original-overflow','reading-order','retained-source','flow-pixels'),
    'B07': ('glyph-cluster-order','typography-pixels'),
    'B08': ('selection-coverage','retained-pixels','masked-pixels'),
    'B09': ('exact-local-repair','repaired-pixels'),
    'B10': ('photo-preview','edited-native-samples','memory-budget'),
    'B11': ('composition-retained','resource-identity','mixed-pixels'),
    'B12': ('wide-pixels','square-pixels','tall-pixels','base-preserved','outputs-preserved'),
    'B13': ('transparent-pixels','screen-color','no-overwrite'),
    'B14': ('print-preview','physical-boxes','profile-identities','native-inks','declared-losses'),
    'B15': ('located-diagnostics','verified-replacements','unchanged-artwork','repaired-pixels'),
    'B16': ('seeded-diagnosis','no-collateral-edits','repair-pixels','preflight-delivery'),
    'B17': ('edited-pixels',),
    'B18': ('both-intents-preserved','conflict-pixels'),
    'B19': ('review-pixels','recovered-pixels','no-partial-final'),
    'B20': ('delivery-0-pixels-clock','reviewed-source-only','revised-preview','delivery-1-pixels-clock',
            'original-timeline','revised-timeline','immutable-deliveries'),
}
ENGINE_CHECKS = {
    'B01': ('editable-source',), 'B02': ('editable-source',),
    'B03': ('historical-pixels','history-valid'), 'B04': ('editable-source',),
    'B05': ('live-dependencies','historical-pixels','history-valid'),
    'B06': ('historical-flow','history-valid'), 'B07': ('editable-text-and-font','history-valid'),
    'B08': ('historical-pixels','history-valid'), 'B09': ('historical-pixels','history-valid'),
    'B10': ('native-import','editable-exact-patch','historical-native-samples','undo-editability',
            'redo-editability','immutable-tiles','history-valid'),
    'B11': ('historical-pixels','history-valid'), 'B12': ('variant-bindings','history-valid'),
    'B13': ('editable-source',), 'B14': ('editable-print-source','history-valid'),
    'B15': ('old-bindings-preserved','history-valid'), 'B16': ('history-valid',),
    'B17': ('original-receipt','retry-idempotent','undo-preserved','history-valid'),
    'B18': ('stale-rejected','historical-pixels','history-valid'),
    'B19': ('active-cancellation','interrupted-unpublished','revision-resource-pinning',
            'single-publication-no-overwrite','history-valid'),
    'B20': ('pinned-successor','no-implicit-relink','explicit-consumer-revision','consumer-undo-retry',
            'undone-timeline','old-source-history','history-valid','consumer-processes'),
}
for _task, _checks in CHECKS.items():
    _classified = ARTIFACT_CHECKS[_task] + ENGINE_CHECKS[_task]
    if len(_classified) != len(set(_classified)) or set(_classified) != set(_checks):
        raise RuntimeError('Incomplete or duplicate benchmark check classification: '+_task)

BASELINE_NOT_APPLICABLE = {
    'B17': 'Lost Inkbolt editing receipts have no no-engine counterpart.',
    'B18': 'Inkbolt revision conflicts have no no-engine counterpart.',
    'B19': 'Inkbolt durable job recovery has no no-engine counterpart.',
}


def check_class(task, name):
    if name == 'source-preservation' or name in ARTIFACT_CHECKS.get(task, ()):
        return 'artifact'
    if name in ENGINE_CHECKS.get(task, ()):
        return 'engine'
    return 'unclassified'  # Controlled unit-test probes; never comparable evidence.
