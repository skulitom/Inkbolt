"""Prevent drift between compiled limits, discovery, generated docs and admission."""
import ast
import re
import sys
import unittest
import test_cli
from test_cli import ROOT
from advertised_limits import capabilities

sys.path.insert(0, str(ROOT/'tools'))
import update_limits


# These paths cover document, raster, delivery, jobs, parsers and geometry budgets.
# Format and mathematical semantics are checked separately from resource policies below.
BINDINGS = {
    'request_diagnostics/maximum_error_bytes': 'request.MAX_DIAGNOSTIC_BYTES',
    'pixel_warps/maximum_absolute_joint_angle_degrees': 'pixel_warps.MAX_JOINT_ANGLE_DEGREES',
    'repeats/maximum_absolute_radial_angle_degrees': 'repeats.MAX_RADIAL_ANGLE_DEGREES',
    'layered_interchange/maximum_import_channels_per_layer': 'layered.MAX_IMPORT_LAYER_CHANNELS',
    'numerical_limits/booleans_quadratic_min_root_enclosure_bits': 'booleans_topology_quadratic.MIN_ROOT_ENCLOSURE_BITS',
    'numerical_limits/booleans_quadratic_root_bits_per_depth': 'booleans_topology_quadratic.ROOT_BITS_PER_DEPTH',
    'numerical_limits/booleans_quadratic_root_guard_bits': 'booleans_topology_quadratic.ROOT_GUARD_BITS',
    'numerical_limits/booleans_quadratic_initial_parameter_bits': 'booleans_topology_quadratic.INITIAL_PARAMETER_BITS',
    'numerical_limits/booleans_quadratic_parameter_growth_factor': 'booleans_topology_quadratic.PARAMETER_GROWTH_FACTOR',
    'image_io/gif/literal_run': 'image_io_gif.LITERAL_RUN',
    'blending/comparison_tie_epsilons': 'blending.COMPARISON_TIE_EPSILONS',
    'canvas_operations/sampling_boundary_epsilon_factor': 'assets.PIXEL_BOUNDARY_EPSILONS',
    'numerical_limits/boards_guide_alignment_tolerance': 'boards.GUIDE_ALIGNMENT_TOLERANCE',
    'numerical_limits/layered_affine_closure_tolerance': 'layered.AFFINE_CLOSURE_TOLERANCE',
    'numerical_limits/meshes_control_inset_epsilons': 'meshes.CONTROL_INSET_EPSILONS',
    'numerical_limits/meshes_inverse_tolerance': 'meshes.INVERSE_TOLERANCE',
    'numerical_limits/meshes_svg_error_margin': 'meshes.SVG_ERROR_MARGIN',
    'numerical_limits/path_text_rounding_epsilons': 'path_text.ROUNDING_EPSILONS',
    'numerical_limits/pixel_brush_endpoint_epsilons': 'pixel_brush.ENDPOINT_EPSILONS',
    'numerical_limits/pixel_warps_orientation_epsilons': 'pixel_warps.ORIENTATION_EPSILONS',
    'numerical_limits/pixel_warps_weight_sum_tolerance': 'pixel_warps.WEIGHT_SUM_TOLERANCE',
    'numerical_limits/profiles_min_matrix_determinant': 'profiles.MIN_MATRIX_DETERMINANT',
    'numerical_limits/render_filter_regions_absolute_margin': 'render_filter_regions.ABSOLUTE_MARGIN',
    'numerical_limits/render_filter_regions_rounding_epsilons': 'render_filter_regions.ROUNDING_EPSILONS',
    'numerical_limits/strokes_brush_min_bisector_length': 'strokes_brush.MIN_BISECTOR_LENGTH',
    'numerical_limits/strokes_brush_rounding_epsilons': 'strokes_brush.ROUNDING_EPSILONS',
    'numerical_limits/strokes_outline_rounding_epsilons': 'strokes_outline.ROUNDING_EPSILONS',
    'numerical_limits/vector_native_integer_tolerance': 'vector_native.INTEGER_TOLERANCE',
    'numerical_limits/visual_diff_grid_phase_tolerance': 'visual_diff.GRID_PHASE_TOLERANCE',
    'numerical_limits/volumes_partition_epsilons': 'volumes.PARTITION_EPSILONS',
    'numerical_limits/render_coverage_path_ellipse_arcs': 'render_coverage_path.ELLIPSE_ARCS',
    'numerical_limits/work_paths_coverage_max_root_steps': 'work_paths_coverage.MAX_ROOT_STEPS',
    'numerical_limits/work_paths_coverage_cubic_crossing_work': 'work_paths_coverage.CUBIC_CROSSING_WORK',
    'numerical_limits/dimensions_pi_atan_terms': 'dimensions.PI_ATAN_TERMS',
    'numerical_limits/geometry_point_fast_term_bound': 'geometry_point.FAST_TERM_BOUND',
    'native_prepress/color_conversion_batch_samples': 'profiles.MAX_CONVERSION_SAMPLES',
    'native_prepress/color_buffer_values': 'prepress.COLOR_BUFFER_VALUES',
    'session_backups/lock_wait_ms': 'sqlite.BUSY_TIMEOUT_MS',
    'session_backups/retry_interval_ms': 'sessions.BACKUP_RETRY_INTERVAL_MS',
    'jobs/launch_lock_timeout_ms': 'jobs.LAUNCH_LOCK_TIMEOUT_MS',
    'jobs/launch_retry_interval_ms': 'jobs.LAUNCH_RETRY_INTERVAL_MS',
    'jobs/monitor_interval_ms': 'jobs.MONITOR_INTERVAL_MS',
    'jobs/state_poll_interval_ms': 'jobs.STATE_POLL_INTERVAL_MS',
    'job_process/maximum_wait_slice_ms': 'job_process.MAX_WAIT_SLICE_MS',
    'objects/minimum_extent': 'objects.MIN_EXTENT',
    'geometry_limits/primitives/minimum_extent': 'primitives.MIN_EXTENT',
    'geometry_limits/primitives/rotation_degrees/1': 'primitives.MAX_ROTATION_DEGREES',
    'geometry_limits/minimum_placed_image_extent': 'model.MIN_PLACED_IMAGE_EXTENT',
    'paint_limits/minimum_linear_span': 'paint.MIN_LINEAR_SPAN',
    'paint_limits/minimum_radial_radius': 'paint.MIN_RADIAL_RADIUS',
    'paint_limits/maximum_radial_radius': 'model.MAX_COORDINATE',
    'paint_limits/minimum_anchor_separation': 'paint.MIN_ANCHOR_SEPARATION',
    'pixel_warps/minimum_frame_extent': 'pixel_warps.MIN_FRAME_EXTENT',
    'path_text/minimum_baseline_length': 'path_text.MIN_BASELINE_LENGTH',
    'print_proof/delta_e76_threshold/1': 'proof.MAX_DELTA_E76_THRESHOLD',
    'color_profiles/lut_curve_entries/1': 'profiles.MAX_LUT_CURVE_ENTRIES',
    'meshes/maximum_svg_coverage_coordinate': 'svg.MAX_MESH_COVERAGE_COORDINATE',
    'svg_import/validation_limits/canvas_extent/0': 'vector_canvas.MIN_LOGICAL_SIZE',
    'svg_import/validation_limits/canvas_extent/1': 'model.MAX_DIMENSION',
    'svg_import/validation_limits/stroke_width/1': 'strokes.MAX_WIDTH',
    'svg_import/validation_limits/miter_limit/0': 'strokes.MIN_MITER_LIMIT',
    'svg_import/validation_limits/miter_limit/1': 'strokes.MAX_MITER_LIMIT',
    'svg_import/validation_limits/font_size/0': 'text.MIN_FONT_SIZE',
    'svg_import/validation_limits/font_size/1': 'text.MAX_FONT_SIZE',
    'pdf/mark_limits/gap_pt/0': 'pdf_marks.MIN_GAP',
    'pdf/mark_limits/gap_pt/1': 'pdf_marks.MAX_GAP',
    'pdf/mark_limits/defaults/gap_pt': 'pdf_marks.DEFAULT_GAP',
    'pdf/mark_limits/length_pt/0': 'pdf_marks.MIN_LENGTH',
    'pdf/mark_limits/length_pt/1': 'pdf_marks.MAX_LENGTH',
    'pdf/mark_limits/defaults/length_pt': 'pdf_marks.DEFAULT_LENGTH',
    'pdf/mark_limits/line_width_pt/0': 'pdf_marks.MIN_LINE_WIDTH',
    'pdf/mark_limits/line_width_pt/1': 'pdf_marks.MAX_LINE_WIDTH',
    'pdf/mark_limits/defaults/line_width_pt': 'pdf_marks.DEFAULT_LINE_WIDTH',
    'pdf/mark_limits/registration_radius_pt/0': 'pdf_marks.MIN_REGISTRATION_RADIUS',
    'pdf/mark_limits/registration_radius_pt/1': 'pdf_marks.MAX_REGISTRATION_RADIUS',
    'pdf/mark_limits/defaults/registration_radius_pt': 'pdf_marks.DEFAULT_REGISTRATION_RADIUS',

    'agent_inputs/document_file/file_bytes': 'request.MAX_REQUEST_BYTES',
    'agent_inputs/expanded_request_bytes': 'request.MAX_REQUEST_BYTES',
    'agent_inputs/request_bytes': 'request.MAX_REQUEST_BYTES',
    'agent_outputs/compact_target_bytes': 'responses.COMPACT_TARGET_BYTES',
    'blending/knockout_max_work': 'render.MAX_RENDER_WORK',
    'components/max_definitions': 'instances.MAX_DEFINITIONS',
    'components/max_evaluated_items': 'model.MAX_ITEMS',
    'components/max_evaluated_items_by_profile/large_raster': 'model.MAX_LARGE_RASTER_ITEMS',
    'components/max_evaluated_items_by_profile/large_vector': 'model.MAX_LARGE_VECTOR_ITEMS',
    'components/max_evaluated_items_by_profile/standard': 'model.MAX_ITEMS',
    'components/max_nesting': 'instances.MAX_NESTING',
    'durable_publication/maximum_ledger_payload_bytes': 'publications.MAX_LEDGER_BYTES',
    'durable_publication/maximum_output_bytes': 'publish.MAX_FILE_IMAGE_BYTES',
    'durable_publication/maximum_receipt_bytes': 'publications.MAX_RECEIPT_BYTES',
    'durable_publication/maximum_receipts': 'publications.MAX_RECORDS',
    'image_io/gif/maximum_delay_centiseconds': 'image_io_gif.MAX_DELAY_TICKS',
    'image_io/gif/palette_entries': 'image_io_gif.MAX_PALETTE_ENTRIES',
    'image_io/gif/plays/1': 'image_io_gif.MAX_PLAYS',
    'image_io/jpeg/default_quality': 'image_io.DEFAULT_JPEG_QUALITY',
    'image_io/jpeg/quality/0': 'image_io.MIN_JPEG_QUALITY',
    'image_io/jpeg/quality/1': 'image_io.MAX_JPEG_QUALITY',
    'image_tracing/output_commands': 'model.MAX_SEGMENTS',
    'image_tracing/result_colors': 'tracing.MAX_COLORS',
    'image_tracing/source_pixels': 'tracing.MAX_PIXELS',
    'image_tracing/unit_edges': 'tracing.MAX_EDGES',
    'meshes/max_contraction': 'meshes.MAX_CONTRACTION',
    'native_sample_store_library/import/max_decoded_bytes': 'sample_import.MAX_NATIVE_DECODED_BYTES',
    'native_sample_store_library/import/max_codec_allocation_bytes': 'sample_import.MAX_NATIVE_CODEC_BYTES',
    'native_sample_store_library/import/max_tiff_padded_tile_bytes': 'sample_import.MAX_NATIVE_TIFF_PADDED_BYTES',
    'native_sample_store_library/private_import_staging/max_bytes': 'sample_import.MAX_PRIVATE_STAGING_BYTES',
    'native_sample_store_library/private_import_staging/input_buffer_bytes': 'sample_import.INPUT_BUFFER_BYTES',
    'native_sample_store_library/private_import_staging/maximum_name_attempts': 'sample_import.MAX_SCRATCH_ATTEMPTS',
    'objects/max_nesting': 'objects.MAX_NESTING',
    'objects/max_rendered_objects': 'objects.MAX_RENDERED_OBJECTS',
    'objects/surface_scale/1': 'render_quality.MAX_SCALE',
    'pdf/image_pixels': 'pdf.MAX_IMAGE_PIXELS',
    'pdf/maximum_page_coordinate': 'pdf.MAX_PAGE_COORDINATE',
    'pdf/maximum_user_unit': 'pdf.MAX_USER_UNIT',
    'pdf/objects': 'pdf.MAX_OBJECTS',
    'pdf/output_bytes': 'publish.MAX_OUTPUT_BYTES',
    'pdf/pages': 'boards.MAX_ARTBOARDS',
    'pdf/path_commands': 'pdf.MAX_COMMANDS',
    'print_cmyk/max_profile_bytes': 'profiles_cmyk.MAX_PROFILE_BYTES',
    'print_proof/output_bytes': 'publish.MAX_OUTPUT_BYTES',
    'print_proof/samples': 'proof.MAX_SAMPLES',
    'publication/output_bytes': 'publish.MAX_OUTPUT_BYTES',
    'render_quality/evaluation/encoded_output_bytes': 'publish.MAX_OUTPUT_BYTES',
    'render_quality/evaluation/traversal/neighborhood_document_units': 'render_traversal.NEIGHBORHOOD_UNITS',
    'render_quality/supersample_factors/1': 'render_quality.MAX_ANTIALIAS_FACTOR',
    'resource_profiles/large_vector/svg_nodes': 'svg_import.MAX_LARGE_NODES',
    'resource_profiles/large_vector/svg_source_bytes': 'svg_import.MAX_LARGE_BYTES',
    'resource_profiles/per_path_commands': 'model.MAX_SEGMENTS',
    'resource_profiles/standard/geometry_commands': 'model.MAX_SEGMENTS',
    'resource_profiles/standard/items': 'model.MAX_ITEMS',
    'resource_profiles/standard/snapshot_bytes': 'model.MAX_DOCUMENT_BYTES',
    'resource_profiles/standard/svg_nodes': 'svg_import.MAX_NODES',
    'resource_profiles/standard/svg_source_bytes': 'svg_import.MAX_BYTES',
    'sample_profiles/profile_encoded_bytes_per_document': 'sample_profiles.MAX_ENCODED_PROFILE_BYTES',
    'sequences/max_distinct_import_states': 'variants.MAX_DATASETS',
    'sequences/max_evaluated_scene_work': 'render.MAX_RENDER_WORK',
    'sequences/max_frames': 'sequences.MAX_FRAMES',
    'sequences/max_output_bytes': 'publish.MAX_OUTPUT_BYTES',
    'sequences/max_total_output_or_import_pixels': 'sequences.MAX_PIXELS',
    'supported/text/axis_controls': 'fonts.MAX_AXES',
    'supported/text/fallback_fonts': 'fonts.MAX_FALLBACK_FONTS',
    'supported/text/feature_controls': 'fonts.MAX_FEATURES',
    'svg_import/definition_limit': 'svg_import_definitions.MAX_DEFINITIONS',
    'svg_import/reference_depth': 'svg_import_definitions.MAX_REFERENCE_DEPTH',
    'svg_import/arcs/max_radial_error_local': 'svg_import.ARC_RADIAL_TOLERANCE',
    'svg_import/arcs/max_normalized_radius': 'model.MAX_COORDINATE',
    'svg_import/source_bytes': 'svg_import.MAX_BYTES',
    'svg_import/unsupported/max_attempts': 'svg_import.MAX_OMISSION_ATTEMPTS',
    'svg_import/unsupported/max_source_processing_bytes': 'svg_import.MAX_OMISSION_SOURCE_BYTES',
    'svg_import/insertion/unsupported/max_attempts': 'svg_import.MAX_OMISSION_ATTEMPTS',
    'svg_import/insertion/unsupported/max_source_processing_bytes': 'svg_import.MAX_OMISSION_SOURCE_BYTES',
    'svg_import/insertion/source_bytes': 'request.MAX_REQUEST_BYTES',
    'svg_import/insertion/prefix_bytes': 'transfer.MAX_PREFIX_BYTES',
    'svg_import/text/font_bindings': 'fonts.MAX_FONTS',
    'svg_import/xml_nodes': 'svg_import.MAX_NODES',
    'svg_import/css/rules': 'svg_import.MAX_CSS_RULES',
    'svg_import/css/selectors_per_rule': 'svg_import.MAX_CSS_RULES',
    'svg_import/css/selector_components': 'svg_import.MAX_CSS_SELECTOR_COMPONENTS',
    'svg_import/css/declarations': 'svg_import.MAX_CSS_DECLARATIONS',
    'svg_import/css/match_work': 'svg_import.MAX_CSS_MATCH_WORK',
    'variants/max_bindings': 'variants.MAX_BINDINGS',
    'variants/max_datasets': 'variants.MAX_DATASETS',
    'variants/max_inheritance': 'variants.MAX_INHERITANCE',
    'visual_comparison/maximum_output_pixels': 'visual_diff.MAX_PIXELS',

    'geometry_limits/minimum_rectangle_extent': 'geometry.MIN_RECTANGLE_EXTENT',
    'geometry_limits/minimum_ellipse_radius': 'geometry.MIN_ELLIPSE_RADIUS',
    'geometry_limits/cubic_linear_threshold': 'geometry.CUBIC_LINEAR_THRESHOLD',
    'assistance/geometry_error_limit': 'assistance.PLACEMENT_ERROR',
    'assistance/maximum_items': 'assistance.MAX_ITEMS',
    'snapping/guide_parallel_threshold': 'snapping.PARALLEL_THRESHOLD',
    'snapping/minimum_guide_length': 'snapping.MIN_GUIDE_LENGTH',
    'snapping/grid_spacing/0': 'snapping.MIN_GRID_SPACING',
    'snapping/grid_spacing/1': 'model.MAX_COORDINATE',
    'vector_canvas/size_range_px/0': 'vector_canvas.MIN_LOGICAL_SIZE',
    'vector_canvas/size_range_px/1': 'model.MAX_DIMENSION',
    'pixel_assistance/smoothness/1': 'assistance_segment.MAX_SMOOTHNESS',
    'pixel_assistance/edge_scale/1': 'assistance_segment.MAX_EDGE_SCALE',
    'pixel_assistance/defaults/smoothness': 'assistance_segment.DEFAULT_WEIGHT',
    'pixel_assistance/defaults/edge_scale': 'assistance_segment.DEFAULT_WEIGHT',
    'pixel_assistance/maximum_seeds_per_class': 'assistance_segment.MAX_SEEDS',
    'volumes/source_tolerance/0': 'warps.MIN_TOLERANCE',
    'volumes/source_tolerance/1': 'warps.MAX_TOLERANCE',
    'volumes/default_source_tolerance': 'volumes.DEFAULT_SOURCE_TOLERANCE',
    'volumes/depth/1': 'volumes.MAX_DEPTH',
    'volumes/rotation_degrees/1': 'volumes.MAX_ROTATION',
    'volumes/normalization_norm/0': 'volumes.MIN_DIRECTION_NORM',
    'volumes/normalization_norm/1': 'volumes.MAX_DIRECTION_NORM',
    'volumes/perspective_distance/0': 'volumes.MIN_CAMERA_DISTANCE',
    'volumes/perspective_distance/1': 'volumes.MAX_CAMERA_DISTANCE',
    'volumes/minimum_camera_near': 'volumes.MIN_CAMERA_NEAR',
    'volumes/maximum_camera_far': 'volumes.MAX_CAMERA_FAR',
    'volumes/maximum_perspective_magnification': 'volumes.MAX_MAGNIFICATION',
    'volumes/lights': 'volumes.MAX_LIGHTS',
    'volumes/light_intensity/1': 'volumes.MAX_LIGHT_INTENSITY',
    'volumes/maximum_profile_edges': 'volumes.MAX_EDGES',
    'volumes/maximum_projected_faces': 'volumes.MAX_FACES',

    'limits/resolution_ppi/0': 'model.MIN_RESOLUTION_PPI',
    'limits/resolution_ppi/1': 'model.MAX_RESOLUTION_PPI',
    'limits/default_resolution_ppi': 'model.DEFAULT_RESOLUTION_PPI',
    'hdr/exposure_stops/1': 'hdr.MAX_EXPOSURE_STOPS',
    'hdr/channel_gain/1': 'hdr.MAX_CHANNEL_GAIN',
    'swatches/max_swatches': 'swatches.MAX_SWATCHES',
    'swatches/max_chain': 'swatches.MAX_DEPTH',
    'swatches/name_bytes': 'swatches.MAX_NAME_BYTES',
    'reconstruction/max_axis_taps': 'resample.MAX_AXIS_TAPS',
    'reconstruction/max_work': 'resample.MAX_WORK',
    'reconstruction/max_index_coordinate': 'resample.MAX_INDEX_COORDINATE',
    'raw_development/exposure_stops/1': 'raw.MAX_EXPOSURE_STOPS',
    'raw_development/resolution_ppi/0': 'model.MIN_RESOLUTION_PPI',
    'raw_development/resolution_ppi/1': 'model.MAX_RESOLUTION_PPI',
    'raw_development/calibration_limits/camera_coefficient/1': 'raw.MAX_CAMERA_COEFFICIENT',
    'raw_development/calibration_limits/minimum_absolute_determinant': 'raw.MIN_CAMERA_DETERMINANT',
    'raw_development/calibration_limits/white_balance_component/1': 'raw.MAX_WHITE_BALANCE_COMPONENT',
    'raw_development/calibration_limits/effective_white_balance_gain/1': 'raw.MAX_WHITE_BALANCE_GAIN',
    'raw_development/calibration_limits/max_source_bytes': 'assets.MAX_IMPORT_BYTES',
    'raw_development/retained/neighborhood_radius/1': 'raw_corrections.MAX_RADIUS',
    'raw_development/retained/correction_limits/threshold/1': 'raw_corrections.MAX_THRESHOLD',
    'raw_development/retained/correction_limits/detail_amount/1': 'raw_corrections.MAX_DETAIL_AMOUNT',
    'raw_development/retained/correction_limits/focal_length/0': 'raw_corrections.MIN_FOCAL_LENGTH',
    'raw_development/retained/correction_limits/focal_length/1': 'raw_corrections.MAX_FOCAL_LENGTH',
    'raw_development/retained/correction_limits/radial_coefficient/1': 'raw_corrections.MAX_RADIAL_COEFFICIENT',
    'raw_development/retained/correction_limits/tangential_coefficient/1': 'raw_corrections.MAX_TANGENTIAL_COEFFICIENT',
    'raw_development/retained/correction_limits/jacobian_perturbation_maximum_exclusive': 'raw_corrections.MAX_JACOBIAN_PERTURBATION',

    'text_limits/frame_extent/0': 'text.MIN_FRAME_EXTENT',
    'text_limits/frame_extent/1': 'model.MAX_COORDINATE',
    'text_limits/leading/0': 'text.MIN_LEADING',
    'text_limits/leading/1': 'text.MAX_LEADING',
    'text_limits/font_size/0': 'text.MIN_FONT_SIZE',
    'text_limits/font_size/1': 'text.MAX_FONT_SIZE',
    'text_limits/tracking/1': 'text.MAX_TRACKING',
    'text_limits/language_bytes': 'text.MAX_LANGUAGE_BYTES',
    'text_limits/layout_overflow_tolerance': 'text.LAYOUT_OVERFLOW_TOLERANCE',
    'text_character_geometry/scale_range/0': 'text.MIN_CHARACTER_SCALE',
    'text_character_geometry/scale_range/1': 'text.MAX_CHARACTER_SCALE',
    'text_character_geometry/baseline_shift_range/1': 'model.MAX_COORDINATE',
    'paragraph_flow/stories': 'text_flow.MAX_STORIES',
    'paragraph_flow/paragraphs_per_story': 'text_flow.MAX_PARAGRAPHS',
    'paragraph_flow/slots_per_story': 'text_flow.MAX_SLOTS',
    'paragraph_flow/columns_per_slot': 'text_flow.MAX_COLUMNS',
    'paragraph_flow/aggregate_characters': 'text.MAX_TEXT_CHARS',
    'paragraph_flow/visible_hyphenation/rule_sets_per_story': 'text_flow_hyphens.MAX_RULE_SETS',
    'paragraph_flow/structural_lists/levels': 'text_flow_lists.MAX_LEVELS',
    'paragraph_flow/structural_lists/ids_per_story': 'text_flow_lists.MAX_LISTS',
    'paragraph_flow/structural_lists/max_counter': 'text_flow_lists.MAX_COUNTER',
    'paragraph_flow/structural_lists/roman_max': 'text_flow_lists.MAX_ROMAN_COUNTER',
    'paragraph_flow/structural_lists/affix_characters': 'text_flow_lists.MAX_AFFIX',
    'paragraph_flow/layout_limits/slot_extent/0': 'text.MIN_FRAME_EXTENT',
    'paragraph_flow/layout_limits/slot_extent/1': 'model.MAX_COORDINATE',
    'paragraph_flow/layout_limits/minimum_column_extent': 'text.MIN_FRAME_EXTENT',
    'paragraph_flow/layout_limits/gutter/1': 'model.MAX_COORDINATE',
    'paragraph_flow/layout_limits/spacing_and_indents/1': 'model.MAX_COORDINATE',
    'paragraph_flow/layout_limits/first_indent/1': 'model.MAX_COORDINATE',
    'paragraph_flow/layout_limits/list_gap/1': 'model.MAX_COORDINATE',
    'paragraph_flow/layout_limits/layout_overflow_tolerance': 'text.LAYOUT_OVERFLOW_TOLERANCE',
    'coordinate_precision/geometry_control_point_absolute_limit': 'model.MAX_COORDINATE',
    'coordinate_precision/transform_component_absolute_limit': 'model.MAX_COORDINATE',
    'coordinate_precision/point_arithmetic/ordinary_or_compensated_absolute_error': 'geometry_point.MAX_ROUNDOFF',
    'coordinate_precision/hierarchy/fast_composition_point_error': 'scene_hierarchy.MAX_FAST_POINT_ERROR',
    'coordinate_precision/hierarchy/maximum_ancestors': 'scene.MAX_DEPTH',
    'coordinate_precision/hierarchy/shared_chain_cache_entries': 'scene.MAX_CACHED_CHAINS',
    'coordinate_precision/affine_inverse/minimum_absolute_determinant': 'geometry_affine.MIN_DETERMINANT',
    'coordinate_precision/relative_edits/maximum_factors': 'geometry_affine.MAX_RELATIVE_FACTORS',
    'coordinate_precision/coordinate_conversions/maximum_expression_factors': 'geometry_affine.MAX_TRANSFORM_FACTORS',
    'coordinate_precision/affine_inverse/fast_coefficient_point_error': 'geometry_affine.MAX_FAST_POINT_ERROR',
    'coordinate_precision/affine_inverse/point_coordinate_absolute_limit': 'geometry_affine.MAX_POINT_COORDINATE',
    'coordinate_precision/relative_edits/fast_coefficient_point_error': 'geometry_affine.MAX_FAST_POINT_ERROR',
    'coordinate_precision/relative_edits/point_coordinate_absolute_limit': 'geometry_affine.MAX_POINT_COORDINATE',
    'coordinate_precision/coordinate_conversions/fast_coefficient_point_error': 'geometry_affine.MAX_FAST_POINT_ERROR',
    'coordinate_precision/coordinate_conversions/point_coordinate_absolute_limit': 'geometry_affine.MAX_POINT_COORDINATE',

    'dimensions/angle_degrees/1': 'dimensions.MAX_ANGLE_DEGREES',
    'dimensions/length_tolerance/0': 'dimensions.MIN_LENGTH_TOLERANCE',
    'dimensions/length_tolerance/1': 'dimensions.MAX_LENGTH_TOLERANCE',
    'dimensions/default_length_tolerance': 'dimensions.DEFAULT_LENGTH_TOLERANCE',
    'dimensions/area_tolerance/0': 'dimensions.MIN_AREA_TOLERANCE',
    'dimensions/area_tolerance/1': 'dimensions.MAX_AREA_TOLERANCE',
    'dimensions/default_area_tolerance': 'dimensions.DEFAULT_AREA_TOLERANCE',
    'dimensions/requested_logical_dimensions/0': 'dimensions.MIN_LOGICAL_DIMENSION',
    'dimensions/requested_logical_dimensions/1': 'dimensions.MAX_LOGICAL_DIMENSION',
    'layer_effects/effect_scale/0': 'effects.MIN_SCALE',
    'layer_effects/effect_scale/1': 'effects.MAX_SCALE',
    'layer_effects/shadow_sigma/1': 'effects.MAX_SHADOW_SIGMA',
    'layer_effects/shadow_offset/1': 'effects.MAX_SHADOW_OFFSET',
    'layer_effects/shadow_distance/1': 'effects.MAX_SHADOW_OFFSET',
    'layer_effects/stroke_radius/1': 'effects.MAX_STROKE_RADIUS',
    'layer_effects/light_azimuth/1': 'effects.MAX_LIGHT_AZIMUTH',
    'layer_effects/default_light_azimuth': 'effects.DEFAULT_LIGHT_AZIMUTH',
    'layer_effects/contour_knots/1': 'effects.MAX_CONTOUR_KNOTS',
    'layer_effects/max_per_item': 'effects.MAX_STACK',
    'layer_effects/max_per_document': 'effects.MAX_DOCUMENT_EFFECTS',
    'layer_effects/max_work': 'effects.MAX_WORK',
    'appearance/passes/1': 'appearance.MAX_PASSES',
    'appearance/vector_tolerance/0': 'warps.MIN_TOLERANCE',
    'appearance/vector_tolerance/1': 'warps.MAX_TOLERANCE',
    'appearance/default_vector_tolerance': 'warps.DEFAULT_TOLERANCE',
    'appearance/bake/pixels': 'model.MAX_STORED_PIXELS',
    'appearance/bake/scale/1': 'render_quality.MAX_SCALE',
    'document_transfer/prefix_characters/1': 'transfer.MAX_PREFIX_BYTES',
    'document_transfer/item_id_bytes': 'model.MAX_ID_BYTES',
    'pixel_brushes/diameter/0': 'pixel_brush.MIN_DIAMETER',
    'pixel_brushes/spacing_range/0': 'pixel_brush.MIN_SPACING',
    'pixel_brushes/spacing_range/1': 'pixel_brush.MAX_SPACING',
    'pixel_brushes/default_spacing': 'pixel_brush.DEFAULT_SPACING',
    'pixel_brushes/scatter_range/1': 'pixel_brush.MAX_SCATTER',
    'pixel_brushes/texture_scale/0': 'pixel_brush.MIN_TEXTURE_SCALE',
    'pixel_brushes/texture_scale/1': 'pixel_brush.MAX_TEXTURE_SCALE',
    'pixel_brushes/coverage_numeric_tolerance': 'pixel_brush.COVERAGE_TOLERANCE',
    'pixel_brushes/coverage_max_depth': 'pixel_brush.MAX_COVERAGE_DEPTH',
    'repair/fill_patch_radius/1': 'repair.MAX_FILL_PATCH_RADIUS',
    'repair/guide_radius/1': 'repair.MAX_GUIDE_RADIUS',
    'repair/maximum_patches': 'repair.MAX_PATCHES',
    'repair/work': 'repair.MAX_WORK',
    'repair/native_region_pixels': 'sample_store.MAX_REGION_PIXELS',
    'repair/native_memory_bytes': 'repair.MAX_MEMORY_BYTES',
    'repair/native_source_preparation_work': 'native_pixels.MAX_PREPARATION_WORK',
    'repair/patch_search_radius/1': 'repair.MAX_SEARCH_RADIUS',
    'repair/patch_context_radius/1': 'repair.MAX_CONTEXT_RADIUS',
    'repair/patch_source_origin/1': 'model.MAX_COORDINATE',
    'repair/synthesized_weight/0': 'repair.MIN_SYNTHESIZED_WEIGHT',
    'repair/default_synthesized_weight': 'repair.DEFAULT_SYNTHESIZED_WEIGHT',
    'repair/guide_range_sigma/0': 'repair.MIN_RANGE_SIGMA',
    'repair/guide_minimum_effective_samples/1': 'repair.MAX_EFFECTIVE_SAMPLES',
    'retouch/maximum_iterations_per_channel': 'retouch.MAX_ITERATIONS',
    'retouch/default_iterations_per_channel': 'retouch.DEFAULT_ITERATIONS',
    'retouch/default_residual_tolerance': 'retouch.DEFAULT_RESIDUAL_TOLERANCE',
    'retouch/maximum_processing_memory_bytes': 'retouch.MAX_MEMORY_BYTES',
    'retouch/maximum_region_pixels': 'sample_store.MAX_REGION_PIXELS',
    'retouch/residual_tolerance/0': 'retouch.MIN_RESIDUAL_TOLERANCE',
    'retouch/residual_tolerance/1': 'retouch.MAX_RESIDUAL_TOLERANCE',
    'retouch/screening/1': 'retouch.MAX_SCREENING',
    'retouch/work': 'retouch.MAX_WORK',
    'filters/median_radius/1': 'detail_filters.MAX_MEDIAN_RADIUS',
    'filters/sharpen_amount/1': 'detail_filters.MAX_SHARPEN_AMOUNT',
    'filters/spatial_offset/1': 'spatial_filters.MAX_OFFSET',
    'filters/mosaic_size/1': 'spatial_filters.MAX_MOSAIC_SIZE',
    'filters/displacement_map_dimension/1': 'spatial_filters.MAX_MAP_AXIS',
    'filters/box_radius/1': 'filters.MAX_BOX_RADIUS',
    'filters/gaussian_sigma/1': 'filters.MAX_GAUSSIAN_SIGMA',
    'filters/surface_radius/1': 'filters.MAX_SURFACE_RADIUS',
    'filters/directional_length/1': 'filters.MAX_DIRECTIONAL_LENGTH',
    'filters/directional_angle_degrees/1': 'filters.MAX_ANGLE_DEGREES',
    'filters/radial_angle_degrees/1': 'filters.MAX_RADIAL_ANGLE',
    'filters/trajectory_samples_odd/0': 'filters.MIN_TRAJECTORY_SAMPLES',
    'filters/trajectory_samples_odd/1': 'filters.MAX_TRAJECTORY_SAMPLES',
    'filters/trajectory_samples_default': 'filters.DEFAULT_TRAJECTORY_SAMPLES',
    'filters/creative_limits/angle_degrees/1': 'filters.MAX_ANGLE_DEGREES',
    'filters/creative_limits/twist_radius/0': 'creative_filters.MIN_TWIST_RADIUS',
    'filters/creative_limits/twist_radius/1': 'model.MAX_COORDINATE',
    'filters/creative_limits/relief_distance/1': 'creative_filters.MAX_RELIEF_DISTANCE',
    'filters/creative_limits/relief_strength/1': 'creative_filters.MAX_RELIEF_STRENGTH',
    'filters/creative_limits/high_pass_sigma/1': 'filters.MAX_GAUSSIAN_SIGMA',
    'filters/creative_limits/extrema_radius/1': 'creative_filters.MAX_EXTREMA_RADIUS',
    'filters/creative_limits/stroke_rank_radius/1': 'creative_filters.MAX_STROKE_RADIUS',
    'filters/creative_limits/edge_ink_strength/1': 'creative_filters.MAX_EDGE_STRENGTH',
    'filters/creative_limits/value_cell_size/1': 'creative_filters.MAX_CELL_SIZE',
    'filters/creative_limits/value_octaves/1': 'creative_filters.MAX_OCTAVES',
    'booleans/curve_tolerance/1': 'booleans.MAX_CURVE_TOLERANCE',
    'booleans/default_curve_tolerance': 'booleans.DEFAULT_CURVE_TOLERANCE',
    'warps/perspective_weights/1': 'warps.MAX_PERSPECTIVE_WEIGHT',
    'warps/tolerance/0': 'warps.MIN_TOLERANCE',
    'warps/tolerance/1': 'warps.MAX_TOLERANCE',
    'warps/default_tolerance': 'warps.DEFAULT_TOLERANCE',
    'repeats/copies/1': 'repeats.MAX_COPIES',
    'interpolation/spine_tolerance/0': 'path_text.MIN_TOLERANCE',
    'interpolation/spine_tolerance/1': 'path_text.MAX_TOLERANCE',
    'path_text/tolerance/0': 'path_text.MIN_TOLERANCE',
    'path_text/tolerance/1': 'path_text.MAX_TOLERANCE',
    'path_text/default_tolerance': 'path_text.DEFAULT_TOLERANCE',
    'path_text/max_commands': 'path_text.MAX_COMMANDS',
    'path_text/max_leaves': 'path_text.MAX_LEAVES',
    'path_text/max_document_leaves': 'path_text.MAX_DOCUMENT_LEAVES',
    'vector_strokes/miter_limit/0': 'strokes.MIN_MITER_LIMIT',
    'vector_strokes/miter_limit/1': 'strokes.MAX_MITER_LIMIT',
    'vector_strokes/width/0': 'strokes.MIN_WIDTH',
    'vector_strokes/width/1': 'strokes.MAX_WIDTH',
    'vector_strokes/dash_intervals': 'strokes.MAX_INTERVALS',
    'vector_strokes/dash_offset/1': 'model.MAX_COORDINATE',
    'vector_strokes/curve_tolerance/default': 'strokes.DEFAULT_CURVE_TOLERANCE',
    'vector_strokes/curve_tolerance/range/0': 'strokes.MIN_CURVE_TOLERANCE',
    'vector_strokes/curve_tolerance/range/1': 'strokes.MAX_CURVE_TOLERANCE',
    'vector_strokes/width_profile/knots/1': 'strokes.MAX_PROFILE_KNOTS',
    'vector_strokes/width_profile/factor/1': 'strokes.MAX_PROFILE_FACTOR',
    'vector_strokes/width_profile/maximum_resulting_width': 'strokes.MAX_WIDTH',
    'vector_strokes/arrow_length_width/0': 'strokes.MIN_ARROW_EXTENT',
    'vector_strokes/arrow_length_width/1': 'strokes.MAX_ARROW_EXTENT',
    'vector_brushes/motif_coordinates/1': 'strokes_brush.MAX_MOTIF_COORDINATE',
    'vector_brushes/spacing/0': 'strokes_brush.MIN_SPACING',
    'vector_brushes/spacing/1': 'strokes_brush.MAX_SPACING',
    'vector_brushes/phase/1': 'model.MAX_COORDINATE',
    'vector_brushes/corner_angle/0': 'strokes_brush.MIN_CORNER_ANGLE',
    'vector_brushes/corner_angle/1': 'strokes_brush.MAX_CORNER_ANGLE',
    'vector_brushes/clearance/1': 'strokes_brush.MAX_CLEARANCE',
    'booleans/curve_contact_root_search_depth': 'booleans_topology_algebraic_roots.MAX_ROOT_DEPTH',
    'booleans/curve_contact_polynomial_coefficient_bits': 'booleans_topology_algebraic_roots.MAX_COEFFICIENT_BITS',
    'warps/map_count/1': 'warps.MAX_MAPS',
    'warps/source_edges': 'warps.MAX_INPUT_EDGES',
    'warps/maximum_degree': 'warps.MAX_DEGREE',
    'warps/rational_bits': 'warps.MAX_BITS',
    'warps/subdivision_depth': 'warps.MAX_DEPTH',
    'warps/arithmetic_work': 'warps.MAX_WORK',
    'warps/generated_commands': 'model.MAX_SEGMENTS',
    'warps/samples': 'warps.MAX_SAMPLES',
    'warps/grid_intervals/1': 'warps.MAX_GRID_AXIS',
    'repeats/generated_commands': 'model.MAX_SEGMENTS',
    'vector_strokes/dash_document_work': 'strokes.MAX_DOCUMENT_WORK',
    'vector_strokes/dash_instance_work': 'strokes.MAX_INSTANCE_WORK',
    'vector_strokes/dash_range_work': 'strokes.MAX_RANGE_WORK',
    'vector_strokes/curve_tolerance/outline_resolution': 'strokes.OUTLINE_RESOLUTION',
    'vector_strokes/generated_document_commands': 'strokes_outline.MAX_OUTLINE_COMMANDS',
    'vector_strokes/generated_scan_work': 'render.MAX_RENDER_WORK',
    'vector_strokes/svg_outline_commands': 'strokes.MAX_SVG_COMMANDS',
    'vector_strokes/svg_range_outline_commands': 'strokes.MAX_SVG_RANGE_COMMANDS',
    'vector_brushes/maximum_conservative_placements': 'strokes_brush.MAX_PLACEMENTS',
    'hyphenation/minima_range/1': 'hyphenation.MAX_MINIMUM_GRAPHEMES',
    'hyphenation/exceptions': 'hyphenation.MAX_EXCEPTIONS',
    'hyphenation/pattern_count': 'hyphenation.MAX_PATTERNS',
    'hyphenation/pattern_scalars': 'hyphenation.MAX_PATTERN_CHARS',
    'hyphenation/total_exception_scalars': 'hyphenation.MAX_EXCEPTION_CHARS',
    'hyphenation/total_pattern_scalars': 'hyphenation.MAX_TOTAL_PATTERN_CHARS',
    'hyphenation/total_word_scalars': 'hyphenation.MAX_TOTAL_WORD_CHARS',
    'hyphenation/word_scalars': 'hyphenation.MAX_WORD_CHARS',
    'hyphenation/words': 'hyphenation.MAX_WORDS',
    'hyphenation/work': 'hyphenation.MAX_WORK',
    'limits/gradient_stops_per_paint': 'paint.MAX_STOPS',
    'limits/gradient_stops_and_anchors': 'paint.MAX_PAINT_SAMPLES',
    'limits/pattern_tile_pixels': 'paint.MAX_PATTERN_PIXELS',
    'limits/paint_work': 'paint.MAX_PAINT_WORK',
    'limits/svg_image_copy_pixels': 'assets.MAX_ASSET_PIXELS',
    'limits/fonts': 'fonts.MAX_FONTS',
    'limits/font_bytes': 'fonts.MAX_FONT_BYTES',
    'limits/font_license_bytes': 'fonts.MAX_LICENSE_BYTES',
    'limits/text_characters': 'text.MAX_TEXT_CHARS',
    'limits/text_ranges_per_frame': 'text.MAX_TEXT_RANGES',
    'limits/text_glyphs': 'text.MAX_GLYPHS',
    'limits/text_outline_commands': 'text.MAX_OUTLINE_COMMANDS',
    'limits/artboards': 'boards.MAX_ARTBOARDS',
    'limits/guides': 'boards.MAX_GUIDES',
    'limits/guides_per_frame': 'boards.MAX_FRAME_GUIDES',
    'limits/bleed_per_edge': 'boards.MAX_BLEED',
    'limits/artboard_batch_pixels': 'boards.MAX_BATCH_PIXELS',
    'limits/artboard_batch_encoded_bytes': 'boards.MAX_BATCH_BYTES',
    'limits/artboard_batch_work': 'boards.MAX_BATCH_WORK',
    'limits/mask_feather_radius': 'masks.MAX_FEATHER',
    'limits/mask_prepared_pixels': 'masks.MAX_PREPARED_PIXELS',
    'limits/mask_document_prepared_pixels': 'masks.MAX_DOCUMENT_PIXELS',
    'limits/mask_feather_work': 'masks.MAX_FEATHER_WORK',
    'limits/artwork_mask_references': 'artwork_masks.MAX_MASKS',
    'limits/artwork_mask_coverage_pixels': 'artwork_masks.MAX_COVERAGE_PIXELS',
    'limits/artwork_mask_svg_copies': 'artwork_masks.MAX_SVG_ITEMS',
    'limits/selection_pixels': 'selections.MAX_PIXELS',
    'limits/selection_work': 'selections.MAX_WORK',
    'limits/selection_radius': 'selections.MAX_RADIUS',
    'limits/selection_polygon_points': 'selections.MAX_POLYGON_POINTS',
    'limits/selection_coverage_subrows': 'selections.COVERAGE_SUBROWS',
    'limits/polygon_points': 'primitives.MAX_POLYGON_POINTS',
    'limits/regular_polygon_sides': 'primitives.MAX_SIDES',
    'limits/star_points': 'primitives.MAX_STAR_POINTS',
    'limits/adjustment_operators_per_layer': 'adjustments.MAX_OPERATORS',
    'limits/adjustment_operators': 'adjustments.MAX_DOCUMENT_OPERATORS',
    'limits/tone_curve_points': 'adjustments.MAX_CURVE_POINTS',
    'limits/measurement_samples': 'measurements.MAX_SAMPLES',
    'limits/color_lut_1d_entries': 'color_adjustments.MAX_LUT_1D',
    'limits/color_lut_3d_side': 'color_adjustments.MAX_LUT_3D_SIDE',
    'limits/color_lut_entries': 'color_adjustments.MAX_DOCUMENT_LUT_ENTRIES',
    'limits/color_map_stops': 'color_adjustments.MAX_MAP_STOPS',
    'limits/filters_per_item': 'filters.MAX_STACK',
    'limits/filters_per_document': 'filters.MAX_DOCUMENT_FILTERS',
    'limits/filter_work': 'filters.MAX_WORK',
    'limits/displacement_map_pixels': 'spatial_filters.MAX_MAP_PIXELS',
    'limits/saved_channels': 'channels.MAX_CHANNELS',
    'limits/channel_samples': 'channels.MAX_SAMPLES',
    'limits/selection_targets': 'selection_analysis.MAX_TARGETS',
    'limits/selection_edge_radius': 'selection_analysis.MAX_EDGE_RADIUS',
    'limits/simplification_span': 'simplify.MAX_SPAN',
    'limits/simplification_work': 'simplify.MAX_WORK',
    'limits/boolean_inputs': 'booleans.MAX_INPUTS',
    'limits/boolean_source_edges': 'booleans.MAX_EDGES',
    'limits/boolean_flattened_edges': 'booleans.MAX_EDGES',
    'limits/boolean_atomic_edges': 'booleans.MAX_ATOMS',
    'limits/boolean_work': 'booleans.MAX_WORK',
    'color_profiles/profile_bytes': 'profiles.MAX_PROFILE_BYTES',
    'color_profiles/profile_tags': 'profiles.MAX_PROFILE_TAGS',
    'color_profiles/transform_stack_bytes': 'profiles.TRANSFORM_STACK_BYTES',
    'focused_previews/vector_overview/axes/0': 'previews.MIN_OVERVIEW_AXIS',
    'focused_previews/vector_overview/axes/1': 'previews.MAX_OVERVIEW_AXIS',
    'handoff/limits/aggregate_pixels': 'sequences.MAX_PIXELS',
    'handoff/limits/axis': 'handoff.MAX_AXIS',
    'handoff/limits/bytes': 'handoff.MAX_BYTES',
    'handoff/limits/canvas_pixels': 'handoff.MAX_PIXELS',
    'handoff/limits/frames': 'sequences.MAX_FRAMES',
    'handoff/limits/seconds': 'handoff.MAX_SECONDS',
    'ink_recipes/curve_knots/1': 'ink_recipes.MAX_KNOTS',
    'ink_recipes/inks/1': 'ink_recipes.MAX_INKS',
    'ink_recipes/preview_work': 'ink_recipes.MAX_WORK',
    'ink_recipes/scale/1': 'render_quality.MAX_SCALE',
    'native_prepress/coverage_sources/max_mask_samples': 'artwork_masks.MAX_COVERAGE_PIXELS',
    'native_prepress/images/max_source_profiles': 'prepress_images.MAX_SOURCE_PROFILES',
    'native_prepress/ink_bindings/max_bindings': 'prepress_bindings.MAX_BINDINGS',
    'native_prepress/max_buffer_values': 'prepress.MAX_BUFFER_VALUES',
    'native_prepress/max_spots': 'prepress.MAX_SPOTS',
    'native_prepress/max_work': 'prepress.MAX_WORK',
    'native_prepress/object_sources/max_nesting': 'objects.MAX_NESTING',
    'native_prepress/object_sources/max_sources': 'objects.MAX_RENDERED_OBJECTS',
    'native_prepress/pdf_delivery/max_aggregate_pixels': 'pdf.MAX_IMAGE_PIXELS',
    'native_prepress/pdf_delivery/max_aggregate_work': 'prepress.MAX_WORK',
    'native_prepress/pixel_warps/work_limit': 'pixel_warps.MAX_WORK',
    'pixel_brushes/dabs': 'pixel_brush.MAX_DABS',
    'pixel_brushes/diameter/1': 'pixel_brush.MAX_DIAMETER',
    'pixel_brushes/points': 'pixel_brush.MAX_POINTS',
    'pixel_brushes/texture_pixels': 'pixel_brush.MAX_TEXTURE_PIXELS',
    'pixel_brushes/work': 'pixel_brush.MAX_WORK',
    'pixel_warps/axis_intervals/1': 'pixel_warps.MAX_AXIS',
    'pixel_warps/joints/1': 'pixel_warps.MAX_JOINTS',
    'pixel_warps/minimum_altitude': 'pixel_warps.MIN_ALTITUDE',
    'pixel_warps/minimum_relative_twice_area': 'pixel_warps.MIN_RELATIVE_AREA',
    'pixel_warps/render_work': 'pixel_warps.MAX_WORK',
    'pixel_warps/sample_limit': 'pixel_warps.MAX_SAMPLES',
    'pixel_warps/stored_controls': 'model.MAX_SEGMENTS',
    'raw_development/max_row_padding_bytes': 'raw.MAX_ROW_PADDING_BYTES',
    'raw_development/max_sensor_pixels': 'raw.MAX_PIXELS',
    'raw_development/retained/max_recipe_bytes': 'raw_retained.MAX_RECIPE_BYTES',
    'raw_development/retained/max_source_bytes': 'raw_retained.MAX_SOURCE_BYTES',
    'work_paths/compound/clip_pixel_limit': 'selections.MAX_PIXELS',
    'work_paths/compound/max_depth': 'work_paths.MAX_COMPONENT_DEPTH',
    'work_paths/compound/max_leaves': 'work_paths.MAX_COMPONENTS',
    'work_paths/compound/operands_per_operation/1': 'work_paths.MAX_OPERANDS',
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
    'sample_precision/import/jpeg/max_output_bytes': 'sample_import.MAX_JPEG_OUTPUT_BYTES',
    'sample_precision/import/jpeg/max_estimated_working_bytes': 'sample_import.MAX_JPEG_WORKING_BYTES',
    'sample_precision/import/jpeg/auxiliary_bytes': 'sample_import.JPEG_AUXILIARY_BYTES',
    'sample_precision/import/jpeg/max_scans': 'sample_import.MAX_JPEG_SCANS',
    'sample_precision/import/jpeg/max_scan_work': 'sample_import.MAX_JPEG_SCAN_WORK',
    'sample_precision/import/jpeg/max_exif_directories': 'sample_import.MAX_JPEG_EXIF_DIRECTORIES',
    'sample_precision/import/jpeg/max_exif_entries': 'sample_import.MAX_JPEG_EXIF_ENTRIES',
    'sample_precision/import/max_inline_pixels': 'model.MAX_STORED_PIXELS',
    'sample_precision/import/max_source_bytes': 'assets.MAX_IMPORT_BYTES',
    'sample_precision/import/max_tiff_padded_tile_bytes': 'sample_import.MAX_TIFF_PADDED_BYTES',
    'sample_precision/import/native_storage/max_source_pixels': 'sample_store.MAX_PIXELS',
    'sample_precision/import/native_storage/max_native_bytes': 'sample_import.MAX_NATIVE_DECODED_BYTES',
    'native_sample_store_library/tile_edge': 'sample_store.TILE_EDGE',
    'native_sample_store_library/max_pixels': 'sample_store.MAX_PIXELS',
    'native_sample_store_library/max_tiles': 'sample_store.MAX_TILES',
    'native_sample_store_library/max_region_pixels': 'sample_store.MAX_REGION_PIXELS',
    'native_sample_store_library/store_admission/maximum_native_bytes': 'sample_store.MAX_STORE_BYTES',
    'native_sample_store_library/store_admission/maximum_root_entries': 'sample_store.MAX_STORE_ENTRIES',
    'native_sample_store_library/store_admission/maximum_lock_wait_ms': 'sample_store.MAX_ADMISSION_WAIT_MS',
    'native_sample_store_library/store_admission/lock_poll_ms': 'sample_store.ADMISSION_POLL_MS',
    'native_sample_store_library/retained_edits/max_patches': 'stored_samples.MAX_PATCHES',
    'native_sample_store_library/retained_edits/max_aggregate_patch_pixels': 'stored_samples.MAX_PATCH_PIXELS',
    'native_sample_store_library/block_edits/maximum_pending_document_bytes': 'stored_samples.MAX_PENDING_BYTES',
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
    'publication/image_file_bytes': 'publish.MAX_FILE_IMAGE_BYTES',
    'durable_publication/maximum_other_output_bytes': 'publish.MAX_OUTPUT_BYTES',
    'render_quality/evaluation/image_file_output_bytes': 'publish.MAX_FILE_IMAGE_BYTES',
    'render_quality/evaluation/whole_work': 'render.MAX_RENDER_WORK',
    'render_quality/evaluation/tiled_work': 'render_tiled.MAX_WORK',
    'sample_precision/import/native_storage/max_source_bytes': 'sample_import.MAX_NATIVE_SOURCE_BYTES',
    'native_sample_store_library/import/max_source_bytes': 'sample_import.MAX_NATIVE_SOURCE_BYTES',
    'image_output/png/inline_encoded_bytes': 'publish.MAX_OUTPUT_BYTES',
    'image_output/jpeg/inline_encoded_bytes': 'publish.MAX_OUTPUT_BYTES',
    'image_output/tiff/inline_encoded_bytes': 'publish.MAX_OUTPUT_BYTES',
    'image_output/png/band_bytes': 'png_output.MAX_BAND_BYTES',
    'image_output/png/codec_chunk_bytes': 'png_output.STREAM_CHUNK_BYTES',
    'image_output/png/private_file_bytes': 'publish.MAX_FILE_IMAGE_BYTES',
    'image_output/tiff/encoded_bytes': 'publish.MAX_FILE_IMAGE_BYTES',
    'image_output/tiff/preflight_patch_bytes': 'publish.MAX_PREFLIGHT_PATCH_BYTES',
    'image_output/tiff/preflight_patch_entries': 'publish.MAX_PREFLIGHT_PATCHES',
    'image_output/jpeg/band_bytes': 'jpeg_output.MAX_BAND_BYTES',
    'image_output/jpeg/encoded_buffer_bytes': 'jpeg_output.STREAM_BUFFER_BYTES',
    'image_output/jpeg/encoded_bytes': 'publish.MAX_FILE_IMAGE_BYTES',
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
    'pixel_brushes/maximum_source_preparation_work': 'native_pixels.MAX_PREPARATION_WORK',
    'retouch/maximum_source_preparation_work': 'native_pixels.MAX_PREPARATION_WORK',
    'pixel_brushes/maximum_window_pixels': 'sample_store.MAX_REGION_PIXELS',
    'pixel_brushes/maximum_processing_memory_bytes': 'pixel_brush.MAX_MEMORY_BYTES',
    'pixel_assistance/maximum_pixels': 'assistance_segment.MAX_PIXELS',
    'pixel_assistance/maximum_work': 'assistance_segment.MAX_WORK',
    'pixel_assistance/native_region/maximum_pixels': 'assistance_segment.MAX_PIXELS',
    'pixel_assistance/native_region/memory_bytes': 'assistance_segment.MAX_MEMORY_BYTES',
    'pixel_assistance/native_region/source_preparation_work': 'native_pixels.MAX_PREPARATION_WORK',
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

    def test_descriptive_capability_limits_follow_catalog_values(self):
        values = {key: value for key, _, value, _ in update_limits.catalog((ROOT/'src/limits.rs').read_text(encoding='utf-8'))}
        bindings = (
            ('image_io/gif/timing','exact_centiseconds_0_to_','','image_io_gif.MAX_DELAY_TICKS'),
            ('layered_interchange/text_delivery/shape_owner','required_consumer_geometry_identifier;1_to_','_ASCII_letters_or_digits;unrecognized_labels_may_fail_geometry','layered_text.MAX_SHAPE_OWNER_BYTES'),
            ('pdf/user_unit','ceil_largest_physical_dimension_divided_by_','_minimum_1','pdf.MAX_PAGE_COORDINATE'),
            ('pixel_warps/weights','per_vertex_normalized_sum_one_within_','','pixel_warps.WEIGHT_SUM_TOLERANCE'),
            ('profile_gamut/inputs','D50_XYZ;finite;','_samples','profiles_gamut.MAX_SAMPLES'),
            ('session_backups/capture','expected_head_read_transaction;bounded_','_page_steps;writers_may_receive_SESSION_BUSY','sessions.BACKUP_STEP_PAGES'),
            ('vector_brushes/distance_precision','','_epsilon_times_point_count_times_length_plus_sum_max_abs_evaluated_coordinates','strokes_brush.ROUNDING_EPSILONS'),
        )
        for path,prefix,suffix,key in bindings:
            with self.subTest(path=path):
                value = capabilities()
                for part in path.split('/'):value = value[part]
                self.assertTrue(value.startswith(prefix) and value.endswith(suffix))
                self.assertEqual(float(value.removeprefix(prefix).removesuffix(suffix)),values[key])

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

        # A scale of one is the identity lower bound; every advertised root
        # resource ceiling (including maximum scale) must have a catalog binding.
        self.assertEqual(capabilities()['limits']['render_scale'][0], 1)
        self.assertEqual(numeric_fields(capabilities()['limits'], 'limits')
                         - {'limits/render_scale/0'},
                         {p for p in BINDINGS if p.startswith('limits/')})

        # Versions, connectivity, a single page, identity scale and zero/infinite
        # endpoints are format or structural semantics, not adjustable budgets.
        fixed = {'durable_publication/payload_versions/output':1,
                 'durable_publication/payload_versions/history':2,
                 'image_io/tiff/pages':1, 'image_io/gif/plays/0':0,
                 'image_tracing/foreground_connectivity':4,
                 'image_tracing/background_connectivity':8,
                 'meshes/axis_range/0':2, 'meshes/svg_samples_per_cell/0':1,
                 'native_sample_store_library/manifest_version':1,
                 'native_sample_store_library/candidate_transfer/version':1,
                 'native_sample_store_library/block_edits/storage_version':2,
                 'native_sample_store_library/block_edits/default_import_storage_version':2,
                 'objects/surface_scale/0':1, 'pdf/scale':1,
                 'render_quality/padding_document_units/0':0,
                 'render_quality/supersample_factors/0':2,
                 'svg_import/validation_limits/stroke_width/0':0,
                 'print_proof/delta_e76_threshold/0':0}
        for path, expected in fixed.items():
            value = capabilities()
            for part in path.split('/'):
                value = value[int(part)] if isinstance(value, list) else value[part]
            self.assertEqual(value, expected)
        scales = capabilities()['print_cmyk']['raster_scale']
        self.assertEqual(scales, list(range(1, values['render_quality.MAX_SCALE']+1)))
        derived = {f'print_cmyk/raster_scale/{i}' for i in range(len(scales))}
        for prefix in ('agent_inputs','agent_outputs','components','durable_publication',
                       'image_io','image_tracing','meshes','native_sample_store_library',
                       'objects','pdf','print_cmyk','print_proof','publication',
                       'render_quality','resource_profiles','sample_profiles','sequences',
                       'supported/text','svg_import','variants','visual_comparison','paint_limits','numerical_limits'):
            value = capabilities()
            for part in prefix.split('/'): value = value[part]
            self.assertEqual(numeric_fields(value, prefix) - fixed.keys() - derived,
                             {p for p in BINDINGS if p.startswith(prefix+'/')}, prefix)
        self.assertEqual(values['fonts.MAX_FALLBACK_FONTS'], values['fonts.MAX_FONTS']-1)

        # Format depth, normalized endpoints and symmetric angle/offset bounds
        # have fixed semantics; every other numeric filter budget is bound.
        filters = capabilities()['filters']
        fixed = {'filters/input_depth': 8, 'filters/mosaic_size/0': 1,
                 'filters/displacement_map_dimension/0': 1,
                 'filters/creative_limits/value_cell_size/0': 1,
                 'filters/creative_limits/value_octaves/0': 1}
        zero = ('median_radius', 'sharpen_amount', 'box_radius', 'gaussian_sigma',
                'surface_radius', 'directional_length',
                'creative_limits/relief_distance', 'creative_limits/relief_strength',
                'creative_limits/high_pass_sigma', 'creative_limits/extrema_radius',
                'creative_limits/stroke_rank_radius', 'creative_limits/edge_ink_strength')
        fixed.update({'filters/'+key+'/0': 0 for key in zero})
        symmetric = ('spatial_offset', 'directional_angle_degrees', 'radial_angle_degrees',
                     'creative_limits/angle_degrees')
        for path, expected in fixed.items():
            value = capabilities()
            for part in path.split('/'):
                value = value[int(part)] if isinstance(value, list) else value[part]
            self.assertEqual(value, expected)
        for key in symmetric:
            bounds = filters
            for part in key.split('/'):
                bounds = bounds[part]
            self.assertEqual(bounds[0], -bounds[1])
        self.assertEqual(numeric_fields(filters, 'filters') - fixed.keys()
                         - {'filters/'+key+'/0' for key in symmetric},
                         {p for p in BINDINGS if p.startswith('filters/')})

        # Nonempty windows and normalized weights have semantic endpoints.
        # Every other numeric brush, repair and healing bound is catalog-backed.
        fixed = {'pixel_brushes/scatter_range/0': 0, 'retouch/screening/0': 0,
                 'repair/fill_patch_radius/0': 1, 'repair/guide_radius/0': 1,
                 'repair/patch_search_radius/0': 0, 'repair/patch_context_radius/0': 1,
                 'repair/patch_source_origin/0': 0, 'repair/synthesized_weight/1': 1,
                 'repair/guide_range_sigma/1': 1, 'repair/guide_minimum_effective_samples/0': 1}
        for path, expected in fixed.items():
            value = capabilities()
            for part in path.split('/'):
                value = value[int(part)] if isinstance(value, list) else value[part]
            self.assertEqual(value, expected)
        for prefix in ('pixel_brushes', 'retouch', 'repair'):
            self.assertEqual(numeric_fields(capabilities()[prefix], prefix) - fixed.keys(),
                             {p for p in BINDINGS if p.startswith(prefix+'/')})
        brush = capabilities()['pixel_brushes']
        self.assertEqual(brush['spacing'], f"{brush['spacing_range'][0]:g}_to_{brush['spacing_range'][1]:g}_times_base_diameter")
        self.assertEqual(brush['scatter'], f"seeded_uniform_square;0_to_{brush['scatter_range'][1]:g}_radii")
        repair = capabilities()['repair']
        self.assertEqual(repair['guide_minimum_effective_samples'][1], (2*repair['guide_radius'][1]+1)**2)

        fixed = {'layer_effects/shadow_sigma/0': 0, 'layer_effects/shadow_distance/0': 0,
                 'layer_effects/stroke_radius/0': 0, 'layer_effects/contour_knots/0': 2,
                 'appearance/passes/0': 1, 'appearance/bake/scale/0': 1,
                 'document_transfer/prefix_characters/0': 1}
        symmetric = ('dimensions/angle_degrees', 'layer_effects/shadow_offset', 'layer_effects/light_azimuth')
        for path, expected in fixed.items():
            value = capabilities()
            for part in path.split('/'):
                value = value[int(part)] if isinstance(value, list) else value[part]
            self.assertEqual(value, expected)
        for path in symmetric:
            value = capabilities()
            for part in path.split('/'):
                value = value[part]
            self.assertEqual(value[0], -value[1])
        for prefix in ('dimensions', 'layer_effects', 'appearance', 'document_transfer'):
            self.assertEqual(numeric_fields(capabilities()[prefix], prefix) - fixed.keys()
                             - {p+'/0' for p in symmetric},
                             {p for p in BINDINGS if p.startswith(prefix+'/')})
        self.assertEqual(capabilities()['dimensions']['requested_logical_dimensions'][1],
                         2*values['model.MAX_COORDINATE'])
        self.assertEqual(capabilities()['layer_effects']['contour'],
                         f"piecewise_linear_2_to_{values['effects.MAX_CONTOUR_KNOTS']}_knots_origin_zero")

        # Selection zero/required-positive and normalized volume endpoints are
        # structural semantics; all other numeric controls have catalog bindings.
        fixed = {'pixel_assistance/smoothness/0':0, 'pixel_assistance/edge_scale/0':1,
                 'pixel_assistance/native_region/feature_bits/u8':8,
                 'pixel_assistance/native_region/feature_bits/u16':16,
                 'pixel_assistance/native_region/feature_bits/f32':16,
                 'volumes/depth/0':0, 'volumes/light_intensity/0':0}
        for path, expected in fixed.items():
            value = capabilities()
            for part in path.split('/'):
                value = value[int(part)] if isinstance(value, list) else value[part]
            self.assertEqual(value, expected)
        rotation = capabilities()['geometry_limits']['primitives']['rotation_degrees']
        self.assertEqual(rotation[0], -rotation[1])
        self.assertEqual(capabilities()['color_profiles']['lut_curve_entries'][0], 2)
        angles = capabilities()['volumes']['rotation_degrees']
        self.assertEqual(angles[0], -angles[1])
        self.assertEqual(capabilities()['pixel_assistance']['edge_scale'][1], 4*255**2)
        for prefix in ('geometry_limits','assistance','snapping','vector_canvas','pixel_assistance','volumes'):
            self.assertEqual(numeric_fields(capabilities()[prefix], prefix) - fixed.keys()
                             - {'volumes/rotation_degrees/0', 'geometry_limits/primitives/rotation_degrees/0'},
                             {p for p in BINDINGS if p.startswith(prefix+'/')})

        # Fixed kernel definitions, normalized ranges and symmetric/reciprocal
        # bounds are explicit; all other numeric color/raw/reconstruction limits bind.
        fixed = {'hdr/channel_gain/0': 0, 'swatches/reference/tint/0': 0,
                 'swatches/reference/tint/1': 1, 'swatches/reference/opacity/0': 0,
                 'swatches/reference/opacity/1': 1, 'reconstruction/bicubic_parameter': -.5,
                 'reconstruction/lanczos_radius': 3,
                 'raw_development/calibration_limits/white_balance_component/0': 0,
                 'raw_development/retained/neighborhood_radius/0': 1,
                 'raw_development/retained/correction_limits/threshold/0': 0,
                 'raw_development/retained/correction_limits/denoise_amount/0': 0,
                 'raw_development/retained/correction_limits/denoise_amount/1': 1,
                 'raw_development/retained/correction_limits/detail_amount/0': 0}
        symmetric = ('hdr/exposure_stops', 'raw_development/exposure_stops',
                     'raw_development/calibration_limits/camera_coefficient',
                     'raw_development/retained/correction_limits/radial_coefficient',
                     'raw_development/retained/correction_limits/tangential_coefficient')
        for path, expected in fixed.items():
            value = capabilities()
            for part in path.split('/'):
                value = value[int(part)] if isinstance(value, list) else value[part]
            self.assertEqual(value, expected)
        for path in symmetric:
            value = capabilities()
            for part in path.split('/'): value = value[part]
            self.assertEqual(value[0], -value[1])
        reciprocal = 'raw_development/calibration_limits/effective_white_balance_gain/0'
        raw = capabilities()['raw_development']
        self.assertEqual(raw['calibration_limits']['effective_white_balance_gain'][0],
                         1/raw['calibration_limits']['effective_white_balance_gain'][1])
        self.assertTrue(raw['calibration_limits']['component_minimum_exclusive'])
        self.assertEqual(raw['source_bytes'],
                         f"exact_row_stride_times_height_max_{values['assets.MAX_IMPORT_BYTES']/(1024*1024):g}_MiB")
        self.assertEqual(raw['retained']['lens_no_fold'],
                         f"global_normalized_Jacobian_perturbation_bound_less_than_{values['raw_corrections.MAX_JACOBIAN_PERTURBATION']:g}")
        for prefix in ('hdr', 'swatches', 'reconstruction', 'raw_development'):
            self.assertEqual(numeric_fields(capabilities()[prefix], prefix) - fixed.keys()
                             - {p+'/0' for p in symmetric} - {reciprocal},
                             {p for p in BINDINGS if p.startswith(prefix+'/')})

        # Identity/default endpoints and symmetric signed ranges are semantics;
        # every text/flow and coordinate precision budget has a compiled binding.
        fixed = {'coordinate_precision/direct_transport_absolute_error': 0,
                 'text_character_geometry/scale_default': 1,
                 'text_character_geometry/baseline_shift_default': 0,
                 'paragraph_flow/layout_limits/gutter/0': 0,
                 'paragraph_flow/layout_limits/spacing_and_indents/0': 0,
                 'paragraph_flow/layout_limits/list_gap/0': 0}
        symmetric = ('text_limits/tracking', 'text_character_geometry/baseline_shift_range',
                     'paragraph_flow/layout_limits/first_indent')
        for path, expected in fixed.items():
            value = capabilities()
            for part in path.split('/'):
                value = value[int(part)] if isinstance(value, list) else value[part]
            self.assertEqual(value, expected)
        for path in symmetric:
            value = capabilities()
            for part in path.split('/'):
                value = value[part]
            self.assertEqual(value[0], -value[1])
        for prefix in ('text_limits', 'text_character_geometry', 'paragraph_flow', 'coordinate_precision'):
            self.assertEqual(numeric_fields(capabilities()[prefix], prefix) - fixed.keys()
                             - {p+'/0' for p in symmetric},
                             {p for p in BINDINGS if p.startswith(prefix+'/')})
        self.assertEqual(values['geometry_affine.MAX_POINT_COORDINATE'],
                         2*values['model.MAX_COORDINATE'])
        self.assertEqual(capabilities()['coordinate_precision']['hierarchy']['error_scope'],
                         f"composition_only;exact_application_to_controls_bounded_by_{values['model.MAX_COORDINATE']:g};final_point_arithmetic_and_coverage_are_separate")
        self.assertEqual(capabilities()['text_first_baseline']['minimum'],
                         f"finite_0_to_{values['model.MAX_COORDINATE']:g}_local_pixels")

        # Symmetric coordinates and normalized zero/endpoint semantics are
        # checked separately; every other advertised stroke/brush bound is bound.
        semantics = {'vector_strokes/dash_offset/0', 'vector_strokes/width_profile/knots/0',
                     'vector_strokes/width_profile/factor/0', 'vector_brushes/motif_coordinates/0',
                     'vector_brushes/phase/0', 'vector_brushes/clearance/0'}
        for prefix in ('vector_strokes', 'vector_brushes'):
            self.assertEqual(numeric_fields(capabilities()[prefix], prefix) - semantics,
                             {p for p in BINDINGS if p.startswith(prefix+'/')})
        stroke = capabilities()['vector_strokes']
        brush = capabilities()['vector_brushes']
        for bounds in (stroke['dash_offset'], brush['phase'], brush['motif_coordinates']):
            self.assertEqual(bounds[0], -bounds[1])
        self.assertEqual(stroke['width_profile']['knots'][0], 2)
        self.assertEqual(stroke['width_profile']['factor'][0], 0)
        self.assertEqual(brush['clearance'][0], 0)
        self.assertEqual(stroke['dash_interval'],
                         f"zero_or_{values['strokes.MIN_DASH_LENGTH']:g}_to_{values['model.MAX_COORDINATE']:g}")
        self.assertEqual(stroke['curve_tolerance']['automatic_refinement'],
                         f"min_saved_and_1_over_{1 / values['strokes.DEFAULT_CURVE_TOLERANCE']:g}_divided_by_max_1_and_{values['strokes.OUTLINE_RESOLUTION']}_times_world_stretch_bound")

        # Required counts and normalized endpoints are structural semantics;
        # projective weight bounds are coupled by an exact reciprocal policy.
        fixed = {'booleans/curve_tolerance/0': 0, 'warps/map_count/0': 1,
                 'warps/grid_intervals/0': 1, 'repeats/copies/0': 1,
                 'repeats/brick_offset/0': 0, 'repeats/brick_offset/1': 1,
                 'interpolation/count/0': 2}
        for path, expected in fixed.items():
            value = capabilities()
            for part in path.split('/'):
                value = value[int(part)] if isinstance(value, list) else value[part]
            self.assertEqual(value, expected)
        weights = capabilities()['warps']['perspective_weights']
        self.assertEqual(weights[0], 1 / weights[1])
        for prefix in ('booleans', 'warps', 'repeats', 'interpolation', 'path_text'):
            self.assertEqual(numeric_fields(capabilities()[prefix], prefix)
                             - fixed.keys() - {'warps/perspective_weights/0'},
                             {p for p in BINDINGS if p.startswith(prefix+'/')})

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
        pattern = re.compile(r'\bconst\s+(?:MAX|MIN)_[A-Z_]+\s*:\s*(?:usize|u64|u32|u8|i64|f64)\s*=')
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

    def test_generator_retains_multiline_derived_budgets_after_formatting(self):
        source = ('pub mod sample {\n'
                  '    pub const SOURCE: u64 = 544 * 1024 * 1024;\n'
                  '    pub const PIXELS: usize = 512 * 1024 * 1024;\n'
                  '    pub const TOTAL: u64 =\n'
                  '        SOURCE + PIXELS as u64;\n}\n')
        values = {key: value for key, _, value, _ in update_limits.catalog(source)}
        self.assertEqual(values['sample.TOTAL'], 1056 * 1024 * 1024)

    def test_generator_preserves_byte_codec_constants_and_casts(self):
        source = 'pub mod codec {\n    pub const MAX_QUALITY: u8 = 100;\n    pub const MAX_COPY: usize = MAX_QUALITY as usize;\n}\n'
        self.assertEqual(update_limits.catalog(source), [
            ('codec.MAX_COPY', 'usize', 100, 'MAX_QUALITY as usize'),
            ('codec.MAX_QUALITY', 'u8', 100, '100')])

    def test_generator_rejects_cycles_duplicates_and_executable_expressions(self):
        def source(body):
            return 'pub mod example {\n'+body+'\n}\n'
        for content in [source('')+source(''),
                        source('pub const MAX_A: usize = 1;')+source('pub const MAX_B: usize = 2;')]:
            with self.assertRaisesRegex(ValueError, 'Duplicate limit group'):
                update_limits.catalog(content)
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

    def test_capability_binding_paths_are_unique(self):
        tree = ast.parse((ROOT/'tests/test_resource_limits.py').read_text(encoding='utf-8'))
        bindings = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                        and any(getattr(target, 'id', '') == 'BINDINGS' for target in node.targets))
        keys = [ast.literal_eval(key) for key in bindings.keys]
        self.assertEqual(len(keys), len(set(keys)), 'Duplicate keys would silently hide a binding')


if __name__ == '__main__':
    unittest.main()
