"""Precision contracts, independent cubic areas, coincidence and durable retries."""
import copy
from contextlib import closing
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import test_booleans_cli as booleans
from test_boolean_curves_cli import curve, blossom
from test_boolean_topology_cli import closed_loop, integrated_area
from test_boolean_ellipses_cli import ellipse, inside_output
from test_mcp import Client
from external_workspace import files


TANGENT_CONTROLS = [[[10,11],[14,7],[18,7],[22,11]], [[11.5,9.5],[11.5,10.5],[15.5,3.5],[23.5,12.5]]]


class BooleanPrecisionTests(unittest.TestCase):
    invoke=booleans.BooleanTests.invoke
    document=booleans.BooleanTests.document
    combine=booleans.BooleanTests.combine

    def bounds(self,result,tolerance):
        self.assertEqual(result['certificate'],'tolerance_snap')
        self.assertFalse(result['curves']['topology']['source_topology_preserved'])
        grid=F(result['curves']['topology']['grid_spacing'])
        self.assertLessEqual(grid,F(tolerance)/8)
        self.assertGreater(grid,F(tolerance)/16)
        for value in result['inputs']:
            self.assertLessEqual(F(value['flattening_deviation_squared']),(F(tolerance)/2)**2)
            self.assertLessEqual(F(value['snapping_deviation_squared']),grid*grid/2)
        for value in result['output_snap_deviation_squared']:
            self.assertLessEqual(F(value),grid*grid/2)
        self.assertLessEqual(len(result['output_snap_deviation_squared']),3)
        self.assertLessEqual(F(result['rounding_deviation_squared']),(F(tolerance)/8)**2)
        self.assertLessEqual(result['work_units'],2_000_000)

    def test_default_auto_strict_lines_and_explicit_invalid_precision(self):
        doc=self.document([booleans.rect(.1,.2,8,6),booleans.rect(4,3,8,6)])
        exact=self.combine(doc,precision='exact')
        args=dict(command='document.boolean',document=doc,ids=['s0','s1'],mode='union')
        default=self.invoke(args)
        self.assertEqual(default['precision'],'auto');self.assertEqual(default['certificate'],'exact')
        self.assertEqual(default['geometry'],exact['geometry']);self.assertNotIn('fallback',default)
        for extra in [dict(precision='unknown'),dict(precision='tolerance',curve_tolerance=0)]:
            self.invoke(dict(args,**extra),1)
        ellipse_doc=self.document([ellipse(12,12,8),booleans.rect(0,0,32,24)])
        refused=self.combine(ellipse_doc,precision='exact',expected=1)
        self.assertEqual(refused['code'],'UNSUPPORTED')
        auto=self.combine(ellipse_doc,precision='auto')
        self.assertEqual(auto['fallback']['stage'],'curves')
        self.assertEqual(auto['fallback']['code'],'RESOURCE_LIMIT')
        self.bounds(auto,.125)
        direct=self.combine(ellipse_doc,precision='tolerance')
        self.assertEqual(auto['geometry'],direct['geometry'])
        self.assertGreater(auto['work_units'],direct['work_units'])

    def test_cubic_green_area_converges_and_source_subdivision_is_invariant(self):
        control=[[0,0],[4,8],[8,8],[12,0]]
        whole=curve(control)
        divided=curve(control,(F(0),F(1,8),F(3,8),F(3,4),F(1)),True)
        source=self.document([whole,booleans.rect(-10,-10,40,40)])
        expected=abs(integrated_area(control));errors=[]
        for t in [.5,.125,.03125]:
            result=self.combine(source,'intersection',precision='tolerance',curve_tolerance=t)
            self.bounds(result,t)
            errors.append(abs(F(result['area_exact'])-expected))
            split=self.document([divided,booleans.rect(-10,-10,40,40)])
            other=self.combine(split,'intersection',precision='tolerance',curve_tolerance=t)
            self.assertEqual(result['geometry'],other['geometry'])
            self.assertEqual(result['area_exact'],other['area_exact'])
        self.assertLess(errors[-1],errors[0]);self.assertLess(errors[-1],F(1,2))
        same=self.document([whole,divided])
        for mode in ['difference','xor']:
            result=self.combine(same,mode,precision='tolerance')
            self.assertTrue(result['empty']);self.assertEqual(result['area_exact'],'0')
        repeated=dict(shape='path',commands=whole['commands']*2)
        for rule,empty in [('nonzero',False),('even_odd',True)]:
            doc=self.document([repeated,booleans.rect(-10,-10,40,40)],[rule,'nonzero'])
            result=self.combine(doc,'intersection',precision='tolerance')
            self.assertEqual(result['empty'],empty)

    def test_irrational_tangencies_fallback_and_independent_cubic_winding(self):
        controls=TANGENT_CONTROLS
        doc=self.document([curve(c) for c in controls]);saved=copy.deepcopy(doc)
        # Independent fine Bernstein sampling for the two source regions. Samples
        # less than .3 units from these segments are excluded from the oracle.
        reference=[]
        for c in controls:
            reference.append([tuple(map(float,blossom(c,[F(i,128)]*3))) for i in range(129)])
        def distance(p,a,b):
            dx,dy=b[0]-a[0],b[1]-a[1];square=dx*dx+dy*dy
            t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/square)) if square else 0
            return ((p[0]-a[0]-t*dx)**2+(p[1]-a[1]-t*dy)**2)**.5
        samples=[]
        for yi in range(35):
            for xi in range(60):
                p=(9+xi/4+.013,4+yi/4+.017)
                if min(distance(p,a,b) for poly in reference for a,b in zip(poly,poly[1:]+poly[:1]))>.3:
                    samples.append((p,[inside_output([poly],*p) for poly in reference]))
        self.assertGreater(len(samples),700)
        for mode in ['union','intersection','difference','xor']:
            result=self.combine(doc,mode,precision='auto');self.bounds(result,.125)
            self.assertIn(result['fallback']['code'],['CURVE_TOPOLOGY_UNRESOLVED','RESOURCE_LIMIT'])
            output=[[tuple(map(float,p)) for p in poly] for poly in booleans.polygons(result['geometry'])]
            for p,states in samples:
                self.assertEqual(inside_output(output,*p),booleans.truth(states,mode),(mode,p))
            curved = self.invoke(dict(command='document.boolean',document=doc,ids=['s0','s1'],mode=mode))
            self.bounds(curved,.125)
            report = curved['curve_output']
            if mode in ('difference','xor'):
                self.assertEqual(report['handle_adjustment'],'linear_interpolation_of_snapped_endpoint_offsets')
            self.assertGreater(report['cubic_segments'],0)
            for key in ('source_curve_deviation_squared','polygon_deviation_squared'):
                self.assertLessEqual(F(report[key]),F(1,8)**2)
            contours = []
            signed_area = F(0)
            for cmd in curved['geometry']['commands']:
                if cmd['verb']=='move':
                    start = last = cmd['to']
                    contours.append([start])
                    continue
                end = start if cmd['verb']=='close' else cmd['to']
                if cmd['verb']=='cubic':
                    controls = [last,cmd['control1'],cmd['control2'],end]
                    signed_area += integrated_area(controls,close=False)
                    for i in range(1,33):
                        t = i/32
                        contours[-1].append([(1-t)**3*a+3*t*(1-t)**2*b+3*t*t*(1-t)*c+t**3*d
                                             for a,b,c,d in zip(*controls)])
                else:
                    signed_area += (F(last[0])*F(end[1])-F(last[1])*F(end[0]))/2
                    contours[-1].append(end)
                last = end
            self.assertEqual(signed_area,F(report['signed_area_exact']))
            for p,states in samples:
                self.assertEqual(inside_output(contours,*p),booleans.truth(states,mode),(mode,p))
        self.assertEqual(doc,saved)

    def test_tight_xor_subdivides_local_chords_and_scales_to_default_tolerance(self):
        for scale in (32, 64):
            tolerance = .125 / scale
            doc = self.document([curve(c) for c in TANGENT_CONTROLS])
            query = dict(command='document.boolean', document=doc, ids=['s0','s1'], mode='xor')
            result = self.invoke(dict(query, curve_tolerance=tolerance))
            polygon = self.invoke(dict(query, curve_tolerance=tolerance, output='polygon'))
            self.bounds(result,tolerance)
            for key in ('area_exact','boundary_edges','positive_contours','negative_contours'):
                self.assertEqual(result[key], polygon[key])
            report = result['curve_output']
            knots = report['chord_subdivision']['inserted_knots']
            self.assertGreater(knots, 0)
            self.assertLess(knots, result['boundary_edges']//10)
            for key in ('polygon_deviation_squared','source_curve_deviation_squared'):
                self.assertLessEqual(F(report[key]), F(tolerance)**2)
            scaled = self.document([curve([[scale*x,scale*y] for x,y in c]) for c in TANGENT_CONTROLS])
            larger = self.invoke(dict(query, document=scaled))
            expected = copy.deepcopy(result['geometry'])
            area = F(0)
            for c in expected['commands']:
                if c['verb']=='move':
                    start = last = tuple(map(F,c['to']))
                else:
                    end = start if c['verb']=='close' else tuple(map(F,c['to']))
                    if c['verb']=='cubic':
                        area += integrated_area([last,c['control1'],c['control2'],end],close=False)
                    else:
                        area += (last[0]*end[1]-last[1]*end[0])/2
                    last = end
                for key in ('to','control1','control2'):
                    if key in c:
                        c[key] = [v*scale for v in c[key]]
            self.assertEqual(area, F(report['signed_area_exact']))
            self.assertEqual(larger['geometry'], expected)
            self.assertEqual(F(larger['curve_output']['signed_area_exact']), area*scale**2)
            self.assertEqual(larger['curve_output']['chord_subdivision'], report['chord_subdivision'])

    def test_loose_tolerance_declares_collapsed_small_regions_and_limits(self):
        doc=self.document([closed_loop(10,10,F(1,4096)),booleans.rect(0,0,32,24)])
        strict=self.combine(doc,'intersection',precision='exact',curve_tolerance=64)
        self.assertFalse(strict['empty'])
        approximate=self.combine(doc,'intersection',precision='tolerance',curve_tolerance=64)
        self.assertTrue(approximate['empty']);self.bounds(approximate,64)
        self.assertIn('Source topology is not preserved',' '.join(approximate['losses']))
        excessive=self.document([dict(shape='regular_polygon',cx=10,cy=10,radius=8,sides=256)]*(booleans.capabilities()['limits']['boolean_source_edges']//256+1))
        for precision in ['auto','exact','tolerance']:
            error=self.combine(excessive,precision=precision,expected=1)
            self.assertEqual(error['code'],'RESOURCE_LIMIT');self.assertNotIn('geometry',error)
        tiny=self.document([curve([[0,0],[4,8],[8,8],[12,0]]),booleans.rect(0,0,32,24)])
        error=self.combine(tiny,precision='tolerance',curve_tolerance=1e-12,expected=1)
        self.assertEqual(error['code'],'RESOURCE_LIMIT')

    def test_mcp_atomic_proposal_retry_and_undo(self):
        doc=self.document([ellipse(12,12,8,5),booleans.rect(8,0,16,24)])
        operation=dict(op='boolean',ids=['s0','s1'],new_id='cut',mode='difference',fill=[30,90,180,255],sources='hide',curve_tolerance=.125)
        action=dict(type='edit',operations=[operation])
        # Historical action normalization adds request_snapshot:null but no precision.
        with tempfile.TemporaryDirectory() as directory, closing(Client()) as client:
            client.initialize();args=dict(session_root=directory,session_id='ellipse')
            client.success('session.create',**args,request_id='create',document=doc)
            inventory={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files(Path(directory))}
            before=client.success('session.read',**args)['document']
            review=client.success('session.dry_run',**args,request_id='cut',expected_revision=0,action=action,
                options=dict(include_document=True))
            self.assertEqual(inventory,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files(Path(directory))})
            result=client.success('session.apply_proposal',session_root=directory,proposal=review['proposal'],action=action)
            self.assertEqual(result['document'],review['proposed_document'])
            retry=client.success('session.apply',**args,request_id='cut',expected_revision=0,action=action)
            self.assertTrue(retry['replayed']);self.assertEqual(retry['receipt'],result['receipt'])
            restored=client.success('session.apply',**args,request_id='undo',expected_revision=1,action=dict(type='undo'))
            self.assertEqual(restored['document']['items'],before['items'])
            redo=client.success('session.apply',**args,request_id='redo',expected_revision=2,action=dict(type='redo'))
            self.assertEqual(redo['document']['items'],result['document']['items'])
            client.success('session.verify',**args)


if __name__=='__main__':unittest.main()
