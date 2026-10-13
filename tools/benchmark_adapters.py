"""Explicit reference-adapter inventory, separate from accepted task requirements."""
from benchmark_conflict import conflicting_writers
from benchmark_retry import lost_response
from benchmark_repair import seeded_repair
from benchmark_resources import resource_repair
from benchmark_typography import multilingual
from benchmark_print import physical_print
from benchmark_variants import layout_variants
from benchmark_screen import transparent_delivery
from benchmark_mixed import mixed_composition
from benchmark_recovery import recovery
from benchmark_photo import photograph
from benchmark_handoff import linked_graphic
from benchmark_diagram import diagram
from benchmark_icons import icons
from benchmark_large_layout import large_layout
from benchmark_svg import svg_artwork
from benchmark_palette import palette
from benchmark_flow import linked_overflow
from benchmark_mask import foreground_mask
from benchmark_retouch import local_retouch

ADAPTERS = {'B01':diagram,'B02':icons,'B03':large_layout,'B04':svg_artwork,
    'B05':palette,'B06':linked_overflow,'B07':multilingual,'B08':foreground_mask,
    'B09':local_retouch,'B10':photograph,'B11':mixed_composition,'B12':layout_variants,
    'B13':transparent_delivery,'B14':physical_print,'B15':resource_repair,
    'B16':seeded_repair,'B17':lost_response,'B18':conflicting_writers,'B19':recovery,'B20':linked_graphic}
