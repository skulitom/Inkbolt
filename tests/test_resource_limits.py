"""Prevent drift between compiled limits, discovery, generated docs and admission."""
import re
import sys
import unittest
import test_cli
from test_cli import ROOT
from advertised_limits import capabilities

sys.path.insert(0, str(ROOT/'tools'))
import update_limits


# These paths cover document, raster, delivery, jobs, parsers and geometry budgets.
# Remaining inline policies outside these modules are still an open W0 audit.
BINDINGS = {
    'native_vector_import/source_bytes': 'vector_native.MAX_SOURCE_BYTES',
    'native_vector_import/decoded_bytes': 'vector_native.MAX_DECODED_BYTES',
    'native_vector_import/blocks': 'vector_native.MAX_BLOCKS',
    'native_vector_delivery/output_bytes': 'vector_native.MAX_DECODED_BYTES',
    'native_vector_delivery/normal_canvas_coordinate_limit': 'vector_native_write.MAX_COORDINATE',
    'interpolation/count/1': 'interpolation.MAX_COUNT',
    'interpolation/spine_leaves': 'path_text.MAX_LEAVES',
    'interpolation/document_spine_leaves': 'interpolation.MAX_DOCUMENT_SPINE_LEAVES',
    'dimensions/work': 'dimensions.MAX_WORK',
    'dimensions/subdivision_depth': 'dimensions.MAX_SUBDIVISION_DEPTH',
    'snapping/target_limit': 'snapping.MAX_TARGETS',
    'snapping/maximum_logical_distance': 'model.MAX_COORDINATE',
    'meshes/axis_range/1': 'meshes.MAX_AXIS',
    'meshes/inverse_steps': 'meshes.INVERSE_STEPS',
    'meshes/inspection_samples': 'meshes.MAX_SAMPLES',
    'meshes/svg_samples_per_cell/1': 'meshes.MAX_SVG_SAMPLES_PER_CELL',
    'meshes/svg_default_samples_per_cell': 'meshes.DEFAULT_SVG_SAMPLES_PER_CELL',
    'meshes/max_texture_pixels': 'meshes.MAX_TEXTURE_PIXELS',
    'meshes/max_svg_texture_pixels': 'meshes.MAX_SVG_TEXTURE_PIXELS',
    'limits/request_bytes': 'request.MAX_REQUEST_BYTES',
    'limits/document_bytes': 'model.MAX_DOCUMENT_BYTES',
    'limits/dimension_pixels': 'model.MAX_DIMENSION',
    'limits/items': 'model.MAX_ITEMS',
    'limits/path_commands': 'model.MAX_SEGMENTS',
    'limits/stored_pixels': 'model.MAX_STORED_PIXELS',
    'limits/hierarchy_depth': 'scene.MAX_DEPTH',
    'limits/batch_operations': 'edit.MAX_OPERATIONS',
    'limits/render_pixels': 'render.MAX_RENDER_PIXELS',
    'limits/render_work': 'render.MAX_RENDER_WORK',
    'limits/group_buffer_pixels': 'render.MAX_BUFFER_PIXELS',
    'limits/render_scale/1': 'render_quality.MAX_SCALE',
    'limits/image_assets': 'assets.MAX_ASSETS',
    'limits/asset_pixels': 'assets.MAX_ASSET_PIXELS',
    'limits/import_bytes': 'assets.MAX_IMPORT_BYTES',
    'limits/control_timeout_ms': 'control.MAX_TIMEOUT_MS',
    'limits/session_states': 'sessions.MAX_STATES',
    'limits/session_requests': 'sessions.MAX_REQUESTS',
    'limits/session_snapshots': 'sessions.MAX_SNAPSHOTS',
    'limits/session_state_bytes': 'sessions.MAX_STATE_BYTES',
    'limits/session_history_bytes': 'sessions.MAX_HISTORY_BYTES',
    'limits/session_database_bytes': 'sessions.MAX_DATABASE_BYTES',
    'limits/session_receipt_bytes': 'sessions.MAX_RECEIPT_BYTES',
    'session_backups/maximum_database_bytes': 'sessions.MAX_DATABASE_BYTES',
    'durable_publication/maximum_history_bytes': 'sessions.MAX_DATABASE_BYTES',
    'agent_discovery/large_schema_outline_bytes': 'schema.OUTLINE_BYTES',
    'agent_discovery/mcp_compact_budget_bytes': 'mcp.CORE_CATALOG_BYTES',
    'paged_inspection/maximum_records': 'inspection.MAX_PAGE_ITEMS',
    'paged_inspection/maximum_result_bytes': 'inspection.MAX_PAGE_BYTES',
    'metadata/record_bytes': 'metadata.MAX_RECORD_BYTES',
    'metadata/document_bytes': 'metadata.MAX_DOCUMENT_BYTES',
    'metadata/envelope_bytes': 'metadata.MAX_PACKET_BYTES',
    'mcp/message_bytes': 'mcp.MAX_MESSAGE_BYTES',
    'mcp/response_bytes': 'mcp.MAX_RESPONSE_BYTES',
    'mcp/pending_requests': 'mcp.MAX_PENDING',
    'mcp/request_ids_per_connection': 'mcp.MAX_REQUEST_IDS',
    'mcp/default_timeout_ms': 'control.MAX_TIMEOUT_MS',
    'mcp_preview/maximum_attached_base64_bytes': 'mcp_preview.MAX_IMAGE_BASE64_BYTES',
    'mcp_preview/maximum_png_attachments': 'mcp_preview.MAX_IMAGES',
    'document_checks/default_issues': 'checks.DEFAULT_ISSUES',
    'document_checks/maximum_issues': 'checks.MAX_ISSUES',
    'document_checks/maximum_report_bytes': 'checks.MAX_REPORT_BYTES',
    'contact_sheets/maximum_views': 'contact_sheets.MAX_VIEWS',
    'contact_sheets/maximum_aggregate_evaluation_pixels': 'contact_sheets.MAX_PIXELS',
    'contact_sheets/maximum_sheet_pixels': 'contact_sheets.MAX_PIXELS',
    'contact_sheets/maximum_cell_axis': 'contact_sheets.MAX_CELL_AXIS',
    'contact_sheets/columns/1': 'contact_sheets.MAX_COLUMNS',
    'contact_sheets/gap/1': 'contact_sheets.MAX_GAP',
    'device_color_conversion/max_samples': 'profiles.MAX_CONVERSION_SAMPLES',
    'resource_profiles/large_vector/items': 'model.MAX_LARGE_VECTOR_ITEMS',
    'resource_profiles/large_vector/geometry_commands': 'model.MAX_LARGE_VECTOR_COMMANDS',
    'resource_profiles/large_vector/snapshot_bytes': 'model.MAX_LARGE_VECTOR_BYTES',
    'resource_profiles/large_raster/items': 'model.MAX_LARGE_RASTER_ITEMS',
    'resource_profiles/large_raster/geometry_commands': 'model.MAX_LARGE_RASTER_COMMANDS',
    'resource_profiles/large_raster/snapshot_bytes': 'model.MAX_LARGE_RASTER_BYTES',
    'sample_precision/import/max_inline_pixels': 'model.MAX_STORED_PIXELS',
    'sample_precision/import/max_source_bytes': 'assets.MAX_IMPORT_BYTES',
    'sample_precision/import/max_tiff_padded_tile_bytes': 'sample_import.MAX_TIFF_PADDED_BYTES',
    'sample_precision/import/native_storage/max_source_pixels': 'sample_store.MAX_PIXELS',
    'sample_precision/import/native_storage/max_native_bytes': 'sample_import.MAX_NATIVE_DECODED_BYTES',
    'native_sample_store_library/tile_edge': 'sample_store.TILE_EDGE',
    'native_sample_store_library/max_pixels': 'sample_store.MAX_PIXELS',
    'native_sample_store_library/max_tiles': 'sample_store.MAX_TILES',
    'native_sample_store_library/max_region_pixels': 'sample_store.MAX_REGION_PIXELS',
    'native_sample_store_library/retained_edits/max_patches': 'stored_samples.MAX_PATCHES',
    'native_sample_store_library/retained_edits/max_aggregate_patch_pixels': 'stored_samples.MAX_PATCH_PIXELS',
    'native_sample_store_library/render_cache/max_decoded_pixels': 'stored_samples.CACHE_PIXELS',
    'native_sample_store_library/render_cache/maximum_source_decoding_passes': 'stored_samples.MAX_SOURCE_DECODING_PASSES',
    'render_quality/internal_scale_maximum': 'render_quality.MAX_INTERNAL_SCALE',
    'render_quality/padding_document_units/1': 'render_quality.MAX_PADDING',
    'render_quality/evaluation/whole_evaluation_pixels': 'render.MAX_RENDER_PIXELS',
    'render_quality/evaluation/tiled_evaluation_pixels': 'render_tiled.MAX_PIXELS',
    'render_quality/evaluation/tile_edge': 'render_tiled.EDGE',
    'render_quality/evaluation/spatial_index/minimum_items': 'render_spatial.MIN_ITEMS',
    'render_quality/evaluation/spatial_index/edge': 'render_spatial.EDGE',
    'render_quality/evaluation/spatial_index/maximum_memberships': 'render_spatial.MAX_REFERENCES',
    'render_quality/evaluation/spatial_index/coverage_cache_pixels': 'render_coverage_cache.MAX_PIXELS',
    'render_quality/evaluation/native_strip_bytes': 'sample_tiff_tiled.MAX_STRIP_BYTES',
    'render_quality/evaluation/tiled_filters/mapping_limits/path_references': 'render_filter_regions.MAX_REFERENCES',
    'render_quality/evaluation/tiled_filters/mapping_limits/radial_samples': 'render_filter_regions.MAX_REFERENCES',
    'layered_interchange/dimensions_by_version/standard': 'layered.MAX_STANDARD_DIMENSION',
    'layered_interchange/dimensions_by_version/large': 'model.MAX_DIMENSION',
    'layered_interchange/canvas_pixels': 'layered.MAX_CANVAS_PIXELS',
    'layered_interchange/file_bytes': 'layered.MAX_FILE_BYTES',
    'layered_interchange/maximum_layers': 'model.MAX_ITEMS',
    'layered_interchange/stored_pixels': 'model.MAX_STORED_PIXELS',
    'layered_interchange/embedded_objects/limits/nesting': 'objects.MAX_NESTING',
    'layered_interchange/embedded_objects/limits/decoded_sample_bytes': 'layered.MAX_DECODED_BYTES',
    'layered_interchange/embedded_objects/limits/source_snapshot_bytes': 'model.MAX_DOCUMENT_BYTES',
    'layered_interchange/embedded_objects/limits/aggregate_snapshot_allocation_bytes': 'layered.MAX_DECODED_BYTES',
    'layered_interchange/text_delivery/limits/characters': 'text.MAX_TEXT_CHARS',
    'layered_interchange/text_delivery/limits/font_faces_across_nested_sources': 'fonts.MAX_FONTS',
    'layered_interchange/text_diagnostics/font_bindings/maximum_faces': 'fonts.MAX_FONTS',
    'pixel_brushes/maximum_window_pixels': 'sample_store.MAX_REGION_PIXELS',
    'pixel_brushes/maximum_processing_memory_bytes': 'pixel_brush.MAX_MEMORY_BYTES',
    'pixel_assistance/maximum_pixels': 'assistance_segment.MAX_PIXELS',
    'pixel_assistance/maximum_work': 'assistance_segment.MAX_WORK',
    'job_process/default_lifetime_ms': 'job_process.DEFAULT_LIFETIME_MS',
    'job_process/maximum_lifetime_ms': 'job_process.MAX_LIFETIME_MS',
    'job_process/default_committed_memory_mib': 'job_process.DEFAULT_MEMORY_MIB',
    'job_process/maximum_committed_memory_mib': 'job_process.MAX_MEMORY_MIB',
    'jobs/active_jobs': 'jobs.MAX_ACTIVE',
    'jobs/maximum_jobs': 'jobs.MAX_JOBS',
    'jobs/attempts': 'jobs.MAX_ATTEMPTS',
    'jobs/maximum_input_bytes': 'jobs.MAX_INPUT_BYTES',
    'jobs/maximum_state_bytes': 'jobs.MAX_STATE_BYTES',
    'jobs/maximum_reserved_store_bytes': 'jobs.MAX_STORE_BYTES',
    'jobs/maximum_database_bytes': 'jobs_store.DATABASE_BYTES',
    'jobs/maximum_wait_ms': 'jobs.MAX_WAIT_MS',
    'jobs/cancel_grace_ms': 'jobs.CANCEL_GRACE_MS',
    'jobs/listing/default_records': 'jobs_listing.DEFAULT_PAGE_RECORDS',
    'jobs/listing/maximum_records': 'jobs_listing.MAX_PAGE_RECORDS',
    'jobs/listing/maximum_result_bytes': 'jobs_listing.MAX_PAGE_BYTES',
    'layered_interchange/descriptor_limits/bytes': 'layered_descriptor.MAX_BYTES',
    'layered_interchange/descriptor_limits/depth': 'layered_descriptor.MAX_DEPTH',
    'layered_interchange/descriptor_limits/values': 'layered_descriptor.MAX_NODES',
    'layered_interchange/descriptor_limits/container_entries': 'layered_descriptor.MAX_CONTAINER',
    'layered_interchange/groups/ancestor_levels': 'scene.MAX_DEPTH',
    'layered_interchange/groups/serialized_records': 'layered.MAX_SERIALIZED_RECORDS',
    'layered_interchange/embedded_objects/limits/decoded_items': 'layered.MAX_DECODED_ITEMS',
    'layered_interchange/text_diagnostics/limits/record_bytes': 'layered_text.MAX_RECORD_BYTES',
    'layered_interchange/text_diagnostics/limits/data_values': 'layered_text_data.MAX_NODES',
    'layered_interchange/text_diagnostics/limits/data_depth': 'layered_text_data.MAX_DEPTH',
    'layered_interchange/text_diagnostics/limits/container_entries': 'layered_text_data.MAX_CONTAINER',
    'layered_interchange/text_diagnostics/limits/string_bytes': 'layered_text_data.MAX_STRING_BYTES',
    'layered_interchange/text_diagnostics/limits/runs': 'layered_text.MAX_RUNS',
    'layered_interchange/text_diagnostics/limits/referenced_fonts': 'fonts.MAX_FONTS',
    'layered_interchange/text_diagnostics/global_story/limits/data_bytes': 'layered_text_data.MAX_GLOBAL_BYTES',
    'layered_interchange/text_diagnostics/global_story/limits/data_values': 'layered_text_data.MAX_GLOBAL_NODES',
    'layered_interchange/text_diagnostics/global_story/limits/data_depth': 'layered_text_data.MAX_GLOBAL_DEPTH',
    'layered_interchange/text_diagnostics/global_story/limits/container_entries': 'layered_text_data.MAX_GLOBAL_CONTAINER',
    'layered_interchange/text_diagnostics/global_story/limits/tagged_records': 'layered_text.MAX_TAGGED_RECORDS',
    'layered_interchange/text_diagnostics/global_story/limits/stories': 'model.MAX_ITEMS',
    'layered_interchange/text_diagnostics/global_story/limits/characters': 'text.MAX_TEXT_CHARS',
    'layered_interchange/text_diagnostics/global_story/limits/runs': 'layered_text.MAX_RUNS',
    'layered_interchange/text_diagnostics/global_story/limits/referenced_fonts': 'fonts.MAX_FONTS',
    'layered_interchange/text_diagnostics/global_story/frame/frame_resources': 'model.MAX_ITEMS',
    'layered_interchange/text_diagnostics/global_story/frame/coordinate_bound': 'model.MAX_COORDINATE',
    'layered_interchange/text_diagnostics/character_controls/source_dash_values': 'layered_text.MAX_DASH_VALUES',
    'layered_interchange/text_diagnostics/character_controls/unmapped_fields_reported': 'layered_text.MAX_UNMAPPED_FIELDS',
    'layered_interchange/text_diagnostics/paragraph_controls/preset_table_records': 'layered_text_preset_records.MAX_RECORDS',
    'layered_interchange/text_diagnostics/paragraph_controls/preset_name_utf8_bytes': 'layered_text_preset_records.MAX_NAME_BYTES',
    'layered_interchange/text_diagnostics/paragraph_controls/reported_preset_records': 'layered_text_preset_records.MAX_REPORTED',
    'layered_interchange/text_diagnostics/paragraph_controls/preset_name_preview_characters': 'layered_text_preset_records.PREVIEW_CHARACTERS',
    'layered_interchange/text_diagnostics/paragraph_controls/unmapped_fields_reported': 'layered_text.MAX_UNMAPPED_FIELDS',
    'layered_interchange/text_import/inheritance/max_reference_depth': 'layered_text.MAX_REFERENCE_DEPTH',
    'layered_interchange/text_import/inheritance/max_resolved_character_runs': 'layered_text.MAX_RUNS',
    'layered_interchange/text_import/inheritance/max_property_references': 'layered_text.MAX_PROPERTY_REFERENCES',
    'layered_interchange/text_import/source_fonts/table_records': 'layered_text_font_records.MAX_RECORDS',
    'layered_interchange/text_import/source_fonts/selected_records': 'layered_text_font_records.MAX_SELECTED',
    'layered_interchange/text_import/source_fonts/version_utf8_bytes': 'layered_text_font_records.MAX_VERSION_BYTES',
    'layered_interchange/text_delivery/limits/runs': 'layered_text.MAX_RUNS',
    'layered_interchange/text_delivery/limits/paragraphs': 'layered_text.MAX_RUNS',
    'layered_interchange/text_delivery/limits/text_record_bytes': 'layered_text.MAX_RECORD_BYTES',
}


class ResourceLimitTests(unittest.TestCase):
    invoke = test_cli.CliTests.invoke

    def test_generated_reference_is_current_and_discovery_matches_constants(self):
        source = (ROOT/'src/limits.rs').read_text(encoding='utf-8')
        self.assertEqual((ROOT/'docs/LIMITS.md').read_text(encoding='utf-8'), update_limits.report(source))
        values = {key: value for key, _, value, _ in update_limits.catalog(source)}
        for path, key in BINDINGS.items():
            with self.subTest(path=path, constant=key):
                value = capabilities()
                for part in path.split('/'):
                    value = value[int(part)] if isinstance(value, list) else value[part]
                self.assertEqual(value, values[key])

        def numeric_fields(value, path):
            if isinstance(value, dict):
                return set().union(*(numeric_fields(v, path+'/'+k) for k, v in value.items()))
            if isinstance(value, list):
                return set().union(*(numeric_fields(v, path+'/'+str(i)) for i, v in enumerate(value)))
            return {path} if type(value) in (int, float) else set()

        prefix = 'layered_interchange'
        reported = numeric_fields(capabilities()[prefix], prefix)
        # Version/code enumerations and the single selected frame are format
        # semantics, not tunable allocation or traversal ceilings.
        semantics = {
            'file_version', 'additional_file_versions/0',
            'embedded_objects/export_source_record_version',
            *(f'embedded_objects/source_record_versions/{i}' for i in range(8)),
            'text_diagnostics/global_story/versions/0',
            'text_diagnostics/global_story/frame/selected_frames',
            'text_import/source_fonts/technology_codes/0',
            'text_import/source_fonts/technology_codes/1',
        }
        self.assertEqual(reported - {prefix+'/'+p for p in semantics},
                         {p for p in BINDINGS if p.startswith(prefix+'/')})

    def test_named_limit_definitions_stay_in_the_catalog(self):
        pattern = re.compile(r'\bconst\s+(?:MAX|MIN)_[A-Z_]+\s*:\s*(?:usize|u64|u32|i64|f64)\s*=')
        for path in (ROOT/'src').rglob('*.rs'):
            if path.name != 'limits.rs':
                self.assertIsNone(pattern.search(path.read_text(encoding='utf-8')), str(path))

    def test_document_dimension_and_delivery_errors_follow_advertised_bounds(self):
        import json
        caps = capabilities()
        maximum = caps['limits']['dimension_pixels']
        request = dict(command='document.create', id='bounds', kind='raster', width=maximum, height=1)
        code, response = self.invoke(json.dumps(request).encode())
        self.assertEqual(code, 0, response)
        code, response = self.invoke(json.dumps(dict(request, width=maximum+1)).encode())
        self.assertEqual(code, 1)
        self.assertEqual(response['error']['code'], 'INVALID_DOCUMENT')
        self.assertIn(str(maximum), response['error']['message'])
        request['width'] = 1
        _, response = self.invoke(json.dumps(request).encode())
        document = response['result']
        scale = caps['limits']['render_scale'][1]
        export = dict(command='document.export', document=document, format='png', scale=scale)
        code, response = self.invoke(json.dumps(export).encode())
        self.assertEqual(code, 0, response)
        for extra in [dict(scale=scale+1), dict(render_options=dict(padding=caps['render_quality']['padding_document_units'][1]+1))]:
            code, response = self.invoke(json.dumps(dict(export, **extra)).encode())
            self.assertEqual(code, 1)
            self.assertEqual(response['error']['code'], 'INVALID_REQUEST')
            self.assertIn(str(scale), response['error']['message'])

    def test_generator_rejects_cycles_duplicates_and_executable_expressions(self):
        def source(body):
            return 'pub mod example {\n'+body+'\n}\n'
        for body in [
            'pub const MAX_A: usize = MAX_A;',
            'pub const MAX_A: usize = 1;\npub const MAX_A: usize = 2;',
            'pub const MAX_A: usize = dangerous();',
            'pub const MAX_A: usize = 1;\npub const MAX_B: usize = MAX_A.div_ceil(0);',
            'pub const MAX_A: usize = 1;\npub const MAX_B: usize = MAX_A.div_ceil(-1);',
            'pub const MAX_A: usize = 1;\npub const MAX_B: usize = MAX_A.div_ceil(other=2);',
            'pub const MAX_A: usize = 1;\npub const MAX_B: usize = MAX_A.unknown(2);',
        ]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                update_limits.catalog(source(body))


if __name__ == '__main__':
    unittest.main()
