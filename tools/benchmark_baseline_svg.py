"""Engine-free B04 SVG delivery and truthful loss-report judging."""
import subprocess

from benchmark_diagram import delivered
from benchmark_graphics import png_check
from benchmark_runtime import require, strict_json
from benchmark_svg import svg_artifact, declared_losses, expected_picture


def render_artwork(case, tools):
    target=getattr(case,'judge_root',case.root)/'judge-baseline.png'
    require(not target.exists(), 'Judge output already exists')
    result=subprocess.run([tools['resvg']['path'],'--skip-system-fonts',str(case.root/'revised.svg'),str(target)],
        cwd=case.root,timeout=30,capture_output=True)
    require(result.returncode==0, 'Pinned SVG artwork rasterizer failed')
    return target.read_bytes()


def judge_svg_artwork(case, tools):
    report=strict_json(delivered(case,'import-report.json'))
    raw=delivered(case,'revised.svg')
    artifact=svg_artifact(raw,report['mapping'])
    case.check('imported-structure',lambda:svg_artifact(raw,report['mapping']))
    case.check('declared-losses',lambda:declared_losses(case,report,artifact))
    rendered=render_artwork(case,tools)
    def picture():
        png_check(delivered(case,'preview.png'),32,24,expected_picture())
        png_check(rendered,32,24,expected_picture())
    case.check('revised-pixels',picture)
    case.not_applicable('editable-source','This check reopens an Inkbolt snapshot; the baseline retains an editable SVG group and path.')
