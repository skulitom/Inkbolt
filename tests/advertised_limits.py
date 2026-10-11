"""Read current build limits for resource-boundary fixtures, without copying policy."""
from functools import lru_cache
import json
from math import isqrt
import subprocess
from test_cli import EXE


@lru_cache(maxsize=1)
def capabilities():
    process = subprocess.run([str(EXE), 'capabilities'], capture_output=True, timeout=10)
    if process.returncode or process.stderr:
        raise AssertionError((process.returncode, process.stderr.decode(errors='replace')))
    response = json.loads(process.stdout)
    if not response['ok']:
        raise AssertionError(response)
    return response['result']


def over_pixel_budget(pixels, dimension=None):
    """Small rectangular grid beyond a pixel ceiling, inside the axis ceiling."""
    dimension = dimension or capabilities()['limits']['dimension_pixels']
    width = min(isqrt(pixels) + 1, dimension)
    height = pixels // width + 1
    if height > dimension or width * height <= pixels:
        raise AssertionError('Pixel boundary is not representable inside dimension limits')
    return width, height
