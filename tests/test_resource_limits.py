"""Prevent drift between compiled limits, discovery, generated docs and admission."""
import re
import sys
import unittest
import test_cli
from test_cli import ROOT
from advertised_limits import capabilities

sys.path.insert(0, str(ROOT/'tools'))
import update_limits


# These paths cover the document, native-raster, delivery and job budgets wired
# in the first W0 consolidation. Remaining inline policies are still an open audit.
BINDINGS = {
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
        ]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                update_limits.catalog(source(body))


if __name__ == '__main__':
    unittest.main()
