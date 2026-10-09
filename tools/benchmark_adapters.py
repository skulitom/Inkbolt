"""Explicit reference-adapter inventory, separate from accepted task requirements."""
from benchmark_graphics import (diagram, icons, large_layout, svg_artwork, palette,
    foreground_mask, local_retouch, transparent_delivery, resource_repair,
    seeded_repair, lost_response, conflicting_writers)
from benchmark_typography import linked_overflow, multilingual
from benchmark_layout_delivery import mixed_composition, layout_variants, physical_print

ADAPTERS = {'B01':diagram,'B02':icons,'B03':large_layout,'B04':svg_artwork,
    'B05':palette,'B06':linked_overflow,'B07':multilingual,'B08':foreground_mask,
    'B09':local_retouch,'B11':mixed_composition,'B12':layout_variants,
    'B13':transparent_delivery,'B14':physical_print,'B15':resource_repair,
    'B16':seeded_repair,'B17':lost_response,'B18':conflicting_writers}
