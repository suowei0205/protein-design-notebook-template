"""Pure synthetic CPU engine doubles; extracted from the prior bounded CPU verifier.
No legacy reference paths, source fixtures, weights or scientific engine imports.
"""
from pathlib import Path
from types import SimpleNamespace, ModuleType
from contextlib import redirect_stdout
import gc, inspect, io, json, sys
import numpy as np
from biotite.structure import AtomArray, concatenate
from biotite.structure.io.pdbx import CIFFile, set_structure

FLOW_CELLS = (15, 16, 18, 22, 24, 27, 28, 30, 31, 32, 33, 34)

def source(nb, cell):
    return ''.join(nb['cells'][cell - 1]['source'])

def synthetic_target(length=11, chain='Q', start=101):
    aa = AtomArray(length * 4)
    aa.chain_id[:] = chain
    aa.res_id = np.repeat(np.arange(start, start + length), 4)
    names = ['ALA', 'GLY', 'SER', 'VAL', 'LEU', 'THR', 'ASN', 'ASP', 'LYS', 'GLU', 'PHE']
    aa.res_name = np.repeat([names[i % len(names)] for i in range(length)], 4)
    aa.atom_name = np.tile(['N', 'CA', 'C', 'O'], length)
    aa.element = np.tile(['N', 'C', 'C', 'O'], length)
    theta = np.arange(length) * 1.745
    ca = np.column_stack((1.5 * np.arange(length), 2.3 * np.cos(theta), 2.3 * np.sin(theta)))
    offsets = np.array([[-.7, .3, 0], [0, 0, 0], [.7, .2, 0], [1., .8, .1]])
    aa.coord = (ca[:, None, :] + offsets).reshape(-1, 3)
    return aa

def write_cif(aa, path):
    f = CIFFile(); set_structure(f, aa); f.write(str(path))

def make_complex(target, length=40):
    """Finite, ordered synthetic binder, deliberately far from the target."""
    binder = AtomArray(length * 4)
    binder.chain_id[:] = 'B'; binder.res_id = np.repeat(np.arange(1, length + 1), 4)
    binder.res_name[:] = 'ALA'; binder.atom_name = np.tile(['N', 'CA', 'C', 'O'], length)
    binder.element = np.tile(['N', 'C', 'C', 'O'], length)
    theta = np.arange(length) * 1.745
    ca = np.column_stack((1.5 * np.arange(length), 2.3 * np.cos(theta), 2.3 * np.sin(theta)))
    offsets = np.array([[-.7, .3, 0], [0, 0, 0], [.7, .2, 0], [1., .8, .1]])
    binder.coord = (ca[:, None, :] + offsets + target.coord.mean(0) + [60., 60., 60.]).reshape(-1, 3)
    return concatenate((target.copy(), binder))

class FakeCUDA:
    @staticmethod
    def is_available(): return True  # Fake runtime gate only; no real torch is imported.
    @staticmethod
    def empty_cache(): pass
    @staticmethod
    def memory_allocated(): return 0
    @staticmethod
    def memory_reserved(): return 0

class FakeSampler:
    """Deterministic schedule stub; does not validate a real RFD3 scheduler."""
    def __init__(self, **kwargs):pass
    def _construct_inference_noise_schedule(self, device=None, partial_t=None):
        full = np.asarray([15., 1.8, .5, .1])
        return full if partial_t is None else full[full <= float(partial_t)]


class FakeRuntime:
    """Tracks constructor/run calls and engine residency without importing torch."""
    def __init__(self, env, reference, profile='normal', invalid=(), crash_at=None):
        self.env = env; self.reference = reference; self.profile = profile
        self.invalid = set(invalid); self.crash_at = crash_at; self.crashed = False
        self.calls = []; self.constructors = []; self.alive = {}; self.max_alive = 0
        self.phase = 'main'; self.max_alive_by_phase = {'main': 0, 'refine': 0}
        self.rf3_ids = []
        self.main_rfd_calls = 0
        runtime = self

        class Engine:
            kind = ''
            def __init__(self, **kwargs):
                runtime.constructors.append((self.kind, dict(kwargs)))
                runtime.alive[id(self)] = self.kind
                runtime.max_alive = max(runtime.max_alive, len(runtime.alive))
                runtime.max_alive_by_phase[runtime.phase] = max(runtime.max_alive_by_phase[runtime.phase], len(runtime.alive))
            def __del__(self): runtime.alive.pop(id(self), None)
            def initialize(self): self.initialized = True; self.seed = None
            def check_seed(self):
                assert getattr(self, 'initialized', False) and isinstance(getattr(self, 'seed', None), int), 'engine must initialize before the stage seed is set'

        class RFD3(Engine):
            kind = 'rfd3'
            def __init__(self, **kwargs):
                super().__init__(**kwargs); self.batch_size = kwargs.get('diffusion_batch_size', 1)
            def run(self, inputs, out_dir=None, n_batches=1):
                self.check_seed()
                runtime.calls.append(('rfd3', str(inputs)))
                payload = json.loads(Path(inputs).read_text()) if isinstance(inputs, (str, Path)) else (inputs.model_dump() if hasattr(inputs, 'model_dump') else inputs)
                spec = payload.get('design_spec', payload)
                partial = spec.get('partial_t') is not None
                ref = runtime.env['_read_cif'](spec['input']) if partial else runtime.reference
                main_offset = runtime.main_rfd_calls
                if not partial: runtime.main_rfd_calls += n_batches
                result = {}
                for batch in range(n_batches):
                    group = []
                    for j in range(self.batch_size):
                        aa = ref.copy(); aa.coord[aa.chain_id != 'A'] += [0., .03 * (batch * self.batch_size + j), 0.]
                        if not partial and (main_offset + batch) * self.batch_size + j in runtime.invalid:
                            aa.coord[np.flatnonzero(aa.chain_id != 'A')[0]] = np.nan
                        group.append(SimpleNamespace(atom_array=aa))
                    result[f'batch{batch}'] = group
                return result

        class MPNN(Engine):
            kind = 'mpnn'
            def run(self, input_dicts, atom_arrays):
                self.check_seed()
                runtime.calls.append(('mpnn', len(atom_arrays)))
                result = []
                for j in range(input_dicts[0]['batch_size']):
                    aa = atom_arrays[0].copy(); aa.res_name[aa.chain_id != 'A'] = 'ALA' if j % 2 == 0 else 'GLY'
                    result.append(SimpleNamespace(atom_array=aa, output_dict={}))
                return result

        class RF3(Engine):
            kind = 'rf3'
            def run(self, inputs, **kwargs):
                self.check_seed()
                eid = inputs['name']
                runtime.calls.append(('rf3', eid))
                if runtime.crash_at is not None and len(runtime.rf3_ids) == runtime.crash_at and not runtime.crashed:
                    runtime.crashed = True
                    raise RuntimeError('CPU_TEST_PLANNED_RF3_INTERRUPT')
                runtime.rf3_ids.append(eid)
                ref = inputs['_cpu_reference']; refined = str(eid).startswith('r')
                ranks = [.6, .9, None, .9]
                if runtime.profile == 'normal' and refined: ranks = [.6, .96, None, .96]
                if runtime.profile == 'baseline_best': ranks = [.4, .5, None, .5] if refined else [.8, .99, None, .99]
                outputs = []
                for mi, rank in enumerate(ranks):
                    aa = ref.copy(); aa.coord[aa.chain_id != 'A'] += [mi * .1, 0., 0.]
                    if runtime.profile == 'no_valid_refine' and refined:
                        aa.coord[np.flatnonzero(aa.chain_id != 'A')[0]] = np.nan
                    if runtime.profile == 'mixed_models' and mi in (0, 3):
                        aa.coord[np.flatnonzero(aa.chain_id != 'A')[0]] = np.nan
                    sm = dict(iptm=.8, ptm=.7, overall_plddt=.9, overall_pae=2., has_clash=False, cpu_model_index=mi)
                    if rank is not None: sm['ranking_score'] = rank
                    outputs.append(SimpleNamespace(atom_array=aa, summary_confidences=sm, confidences={}))
                return {eid: outputs}

        class Spec:
            def __init__(self, **kwargs): self.kwargs = kwargs
            def model_dump(self, exclude_none=False):
                return {k: v for k, v in self.kwargs.items() if not exclude_none or v is not None}

        class Config(dict):
            def __init__(self, **kwargs): super().__init__(kwargs)

        def from_json_dict(value, **kwargs):
            assert kwargs.get('template_selection', []) == []
            assert kwargs.get('ground_truth_conformer_selection', []) == []
            ref = inspect.currentframe().f_back.f_locals['aa']
            assert value['components'][0]['seq'] == runtime.env['TARGET_FRAGMENT_SEQ']
            return {**value, '_cpu_reference': ref.copy()}

        self.modules = {
            'torch': dict(cuda=FakeCUDA(), bfloat16='CPU_TEST_BFLOAT16',device=lambda x:x,tensor=lambda x,**k:x),
            'rfd3.model.inference_sampler': dict(SampleDiffusionWithMotif=FakeSampler),
            'rfd3.utils.inference': dict(inference_load_=lambda path: {'atom_array':self.env['_read_cif'](path)}),
            'rfd3.engine': dict(RFD3InferenceConfig=Config, RFD3InferenceEngine=RFD3),
            'rfd3.inference.input_parsing': dict(DesignInputSpecification=Spec),
            'mpnn.inference_engines.mpnn': dict(MPNNInferenceEngine=MPNN),
            'rf3.inference_engines.rf3': dict(RF3InferenceEngine=RF3),
            'rf3.utils.inference': dict(InferenceInput=SimpleNamespace(from_json_dict=from_json_dict)),
        }

    def install(self):
        self.previous = {}
        for name, attrs in self.modules.items():
            self.previous[name] = sys.modules.get(name)
            mod = ModuleType(name)
            for key, value in attrs.items(): setattr(mod, key, value)
            sys.modules[name] = mod
        self.previous['py3Dmol'] = sys.modules.get('py3Dmol'); sys.modules['py3Dmol'] = None
        self.env['torch'] = SimpleNamespace(cuda=FakeCUDA(), device=lambda x:x, tensor=lambda x,**k:x)
        self.env['_cpu_before_cell'] = lambda cell: setattr(self, 'phase', 'refine' if cell >= 30 else 'main')

    def uninstall(self):
        for name, mod in self.previous.items():
            if mod is None: sys.modules.pop(name, None)
            else: sys.modules[name] = mod

    def summary(self):
        return dict(constructor_counts={k: sum(x[0] == k for x in self.constructors) for k in ('rfd3', 'mpnn', 'rf3')},
                    run_counts={k: sum(x[0] == k for x in self.calls) for k in ('rfd3', 'mpnn', 'rf3')},
                    max_simultaneously_resident_engines=self.max_alive,
                    max_resident_engines_by_phase=dict(self.max_alive_by_phase), rf3_candidate_ids=self.rf3_ids,
                    completed_RF3_runs=len(self.rf3_ids),
                    failed_RF3_attempts=sum(kind == 'rf3' for kind, _ in self.calls) - len(self.rf3_ids))

def execute_cells(nb, env, cells=FLOW_CELLS):
    log = io.StringIO()
    with redirect_stdout(log):
        for cell in cells:
            if '_cpu_before_cell' in env: env['_cpu_before_cell'](cell)
            exec(compile(source(nb, cell), f'cell{cell}_cpu_flow', 'exec'), env)
    return log.getvalue()

def release_engines(env):
    for key in ('model', 'mpnn', 'rf3_engine', 'rfd3_model', 'mpnn_eng', 'rf3_eng'):
        env.pop(key, None)
    gc.collect()
