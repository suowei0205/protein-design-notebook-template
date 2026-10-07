"""Execute delivered main/refine cells with synthetic CPU engine doubles.

No inference engines, GPU, weights, installation, network or reference datasets.
Run with existing numpy/scipy/biotite dependencies; writes only temporary fixtures.
"""
from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager, nullcontext, redirect_stdout
import ast, csv, gc, hashlib, importlib.util, io, json, math, numbers, os, re, sys, tempfile, time
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'runtime'))
import sr56_feedback as feedback
import numpy as np
from scipy.spatial import cKDTree
from biotite.sequence import ProteinSequence
from biotite.structure import AtomArray, annotate_sse, concatenate, get_residue_starts
from biotite.structure.io.pdbx import CIFFile, get_structure
from fake_engines import FakeRuntime, execute_cells, make_complex, release_engines, source, synthetic_target, write_cif

NOTEBOOK = ROOT/'template/DesignProject/DesignProject.ipynb'


def load_helpers(nb, cell, env):
    nodes = [n for n in ast.parse(source(nb,cell)).body if isinstance(n,ast.FunctionDef)]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),f'cell{cell}-delivered-helpers','exec'),env)


def base_environment(nb, root, input_file, resume=False, refine_top_n=2):
    frozen=root/'checkpoints/input/notebook.ipynb'
    if not frozen.exists():
        frozen.parent.mkdir(parents=True,exist_ok=True);frozen.write_text(json.dumps(nb))
    assert json.loads(frozen.read_text())==nb
    session = feedback.Session(root,'template_project',notebook_path=frozen,
                               namespace='design_template_pipeline_v2',background=False,run_label='CPU synthetic')
    session.close = lambda:None
    env = dict(np=np, Path=Path, get_residue_starts=get_residue_starts,
               ProteinSequence=ProteinSequence, SimpleNamespace=SimpleNamespace,
               _re=re, _hashlib=hashlib, hashlib=hashlib, _csv=csv, csv=csv, json=json, time=time,
               os=os, sys=sys, math=math, numbers=numbers, gc=gc, AtomArray=AtomArray,
               contextmanager=contextmanager, tempfile=tempfile, _CIFFile=CIFFile,
               _get_structure=get_structure,cKDTree=cKDTree,annotate_sse=annotate_sse,
               concatenate=concatenate,to_cif_file=write_cif,display=lambda *a:None,
               _HTML=lambda x:x,seed_everything=lambda seed:None,
               _feedback=session,_feedback_Path=Path,_feedback_sys=sys,_feedback_importlib=importlib.util,
               _feedback_paths={},_feedback_assessed={},
               _standalone_runtime=SimpleNamespace(__file__=str(ROOT/'runtime/standalone_runtime.py')))
    load_helpers(nb,4,env)
    # Cell 6/8/9 are real setup and parameter code, then only test budget/input values change.
    execute_cells(nb,env,(6,8,9))
    env.update(TARGET_STRUCTURE_FILE=str(input_file),SOURCE_CHAIN='Q',SOURCE_RESIDUE_RANGE=None,
               SOURCE_MODEL=1,SOURCE_ALTLOC='occupancy',EXPECTED_TARGET_SEQUENCE='',
               _SOURCE_INPUT=input_file, diffusion_batch_size=1,n_batches=3,total_designs=3,n_proc=3,
               num_timesteps=2,low_memory_mode=True,random_seed=20261007,
               mpnn_seqs_per_backbone=2,rf3_models_per_sequence=4,refine_top_n=refine_top_n,refine_rounds=3,
               refine_backbone_batch=1,refine_batch=3,refine_mpnn_seqs=2,refine_beam_k=3,
               refine_timesteps=2,refine_early_stop=0.,max_designs=0)
    load_helpers(nb,10,env)
    # Shared checkpoint adapter assignments use real delivered scientific helper functions.
    allowed = {'_fix','_resume','_WEIGHT_SHA_MEMO','_HOTSPOT_RE','_cfg_fp'}
    for node in ast.parse(source(nb,10)).body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in allowed for t in node.targets):
            exec(compile(ast.Module(body=[node],type_ignores=[]),'delivered-adapters','exec'),env)
    # These are presentation functions only; metric/validation/selection code remains real.
    for name in ('_collapsible','_ref_panel','_sr56_table','_sr56_tick','_sr56_emit','_sr56_three_panel'):
        env[name]=lambda *a,**k:None
    env.update(_quiet_logging=lambda:None,_fold_out=lambda *a:nullcontext(),view=lambda *a,**k:None)
    for key in ('RFD3_CKPT','MPNN_CKPT','RF3_CKPT'):
        path=root/(key+'.fake')
        if not path.exists():path.write_bytes(b'SYNTHETIC CPU fake weight identity marker')
        env[key]=str(path)
    # Actual target preparation/validation executes in full; test target has eleven residues.
    reference=make_complex(synthetic_target(11,'A',1))
    fake=FakeRuntime(env,reference);fake.install()
    try:
        execute_cells(nb,env,(12,13))
        assert len(env['TARGET_FRAGMENT_SEQ'])==11
        assert env['TARGET_FRAGMENT_RANGE']==(1,11)
        reference=make_complex(env['TARGET_FRAGMENT_AA']);fake.reference=reference
    except BaseException:
        fake.uninstall();raise
    return env,fake,reference


def rows(path):
    with Path(path).open() as stream:return list(csv.DictReader(stream))


def selected_signature(env):
    return {'main':[(int(r[0]),int(r[5]),r[2].get('ranking_score')) for r in env['rmsd_report']],
            'refine':{str(di):[int(v[0]),int(v[1]),int(v[2]),v[4].get('ranking_score'),v[6]] for di,v in env['refine_best_round'].items()}}


def audit_signature(env):
    # Exclude runtime roots/times; retain every numeric assessment and scientific identity.
    signature=[]
    for phase,path in [('main',env['MAIN_REPORT_DIR']/'rf3_model_audit.csv'),('refine',env['REFINE_DIR']/'refine_model_audit.csv')]:
        for row in rows(path):
            signature.append((phase,tuple(sorted((k,v) for k,v in row.items() if k not in ('cif','conf')))))
    assert len(signature)==len(set(signature)), 'Duplicate model-level audit rows'
    return sorted(signature)


def run_case(nb,input_file,root,profile='normal',invalid=(),crash_at=None,refine_top_n=2):
    root.mkdir();env,initial,reference=base_environment(nb,root,input_file,refine_top_n=refine_top_n)
    initial.uninstall();fake=FakeRuntime(env,reference,profile,invalid,crash_at);fake.install()
    env['refine_top_n']=refine_top_n
    # Reconfigure before any computation, preserving the test's explicit budget identity.
    execute_cells(nb,env,(13,))
    before=[];interrupted=False
    try:
        try:execute_cells(nb,env)
        except RuntimeError as exc:
            if str(exc)!='CPU_TEST_PLANNED_RF3_INTERRUPT':raise
            interrupted=True;before=list(fake.rf3_ids)
            env['_feedback'].finish('INTERRUPTED')
            release_engines(env);fake.uninstall()
            env,initial,reference=base_environment(nb,root,input_file,True,refine_top_n)
            initial.uninstall();fake=FakeRuntime(env,reference,profile,invalid);fake.install()
            execute_cells(nb,env)
            assert not set(before).intersection(fake.rf3_ids), 'Completed RF3 pairs were recomputed'
        valid_designs=[i for i in range(3) if i not in invalid]
        assert len(env['all_mpnn_results'])==3 and len(env['all_rf3_results'])==len(valid_designs)*2
        assert all(r[4]['cpu_model_index']==1 for r in env['all_rf3_results']), 'Stable model tie-break changed'
        for di,best in env['refine_best_round'].items():
            if profile=='normal':assert best[0]==1 and best[4]['ranking_score']==.96
            elif profile in ('baseline_best','no_valid_refine'):assert best[0]==0
            if profile!='no_valid_refine':
                assert len(env['refine_history'][di])==4 and env['beam_kept'][di]=={1:3,2:3,3:3}
            assert env['_binder_seq_of'](env['refine_best_mpnn'][di])==env['_binder_seq_of'](best[3])
        sig=selected_signature(env);audit=audit_signature(env)
        main_pairs=len(valid_designs)*2
        refine_pairs=min(refine_top_n,len(valid_designs))*(6 if profile=='no_valid_refine' else 42)
        total=main_pairs+refine_pairs
        assert len(before)+len(fake.rf3_ids)==total
        assert len(audit)==total*4
        valid=main_pairs*4+(0 if profile=='no_valid_refine' else refine_pairs*4)
        report=feedback.collect(root)
        assert report['counts']['rf3_pairs']==total and report['counts']['rf3_models']==total*4
        assert report['counts']['valid_models']==valid
        assert report['counts']['rfd3_generated']==3 and report['counts']['mpnn_sequences']==main_pairs
        assert report['counts']['rounds_completed']==min(refine_top_n,len(valid_designs))*(1 if profile=='no_valid_refine' else 3)
        assert not any(i['code'].startswith('CHECKPOINT_') or i['code']=='ASSESSMENT_IDENTITY_MISMATCH' for i in report['issues'])
        assert all(c['assessment_binding']=='VERIFIED_RECEIPT' for c in report['candidates'])
        archives=list((root/'feedback').glob('*.zip'));assert archives
        assert feedback.verify_bundle(max(archives,key=lambda p:p.stat().st_mtime_ns))['computation_status']=='COMPLETED'
        assert fake.max_alive<=1, 'Simultaneous inference engine ownership changed'
        # Fresh globals + fake modules must restore completed caches without constructing engines.
        release_engines(env);fake.uninstall()
        restored,cache,reference=base_environment(nb,root,input_file,True,refine_top_n)
        try:
            execute_cells(nb,restored)
            assert cache.calls==[] and cache.constructors==[]
            assert selected_signature(restored)==sig and audit_signature(restored)==audit
        finally:release_engines(restored);cache.uninstall()
        return {'profile':profile,'pairs':total,'models':total*4,'valid_models':valid,'interrupted':interrupted,
                'cache_restore_no_engines':True,'selected':sig},sig,audit
    finally:
        release_engines(env);fake.uninstall();env['_feedback'].close()


def check_missing_target_gate(nb,root):
    session=feedback.Session(root,'template_project',notebook_sha256='synthetic-gate',namespace='design_template_pipeline_v2',background=False)
    session.close=lambda:None
    env={'TARGET_STRUCTURE_FILE':'','_feedback':session}
    before=set(sys.modules)
    try:exec(compile(source(nb,10).split('# TEMPLATE_INPUT_GATE_END',1)[0],'delivered-missing-input-gate','exec'),env)
    except ValueError as exc:assert 'TARGET_STRUCTURE_FILE' in str(exc)
    else:raise AssertionError('Missing target did not stop the delivered input gate')
    assert not any(x=='torch' or x.startswith(('rfd3','rf3','mpnn')) for x in set(sys.modules)-before)
    assert feedback.read_json(root/'monitor/session.json')['status']=='NOT_RUN'
    assert feedback.verify_bundle(next((root/'feedback').glob('*.zip')))['computation_status']=='NOT_RUN'


def run():
    raw=NOTEBOOK.read_bytes();nb=json.loads(raw)
    assert len(nb['cells'])==36
    for cell in nb['cells']:
        if cell['cell_type']=='code':compile(''.join(cell['source']),'delivered-notebook','exec')
    results=[]
    with tempfile.TemporaryDirectory(prefix='template-pipeline-cpu-') as td,redirect_stdout(io.StringIO()):
        temp=Path(td).resolve();target=temp/'synthetic-target.cif';write_cif(synthetic_target(),target)
        check_missing_target_gate(nb,temp/'missing-target')
        env,fake,_=base_environment(nb,temp/'frozen-input',target)
        try:
            for path in (target,env['PREP_DIR']/'target.cif',env['PREP_DIR']/'target.provenance.json'):
                original=path.read_bytes()
                changed=(original+b'# changed after preflight\n') if path.suffix!='.json' else b'{}'
                path.write_bytes(changed)
                try:
                    for call in (env['_current_cfg'],lambda:execute_cells(nb,env,(15,))):
                        try:call()
                        except ValueError as exc:assert 'changed' in str(exc)
                        else:raise AssertionError('Changed frozen input reached scientific stage')
                    assert fake.calls==[] and fake.constructors==[] and path.read_bytes()==changed
                finally:path.write_bytes(original)
        finally:release_engines(env);fake.uninstall();env['_feedback'].close()

        for name,kwargs in [('three_rounds',{}),('baseline_best',{'profile':'baseline_best'}),
                            ('no_valid_refine',{'profile':'no_valid_refine'}),
                            ('no_valid_inputs',{'invalid':(0,1,2),'refine_top_n':0}),
                            ('interrupted_resume',{'crash_at':9})]:
            print('CPU CASE START',name,flush=True,file=sys.__stdout__)
            result,sig,audit=run_case(nb,target,temp/name,**kwargs);results.append({'case':name,**result})
            print('CPU CASE PASS',name,'pairs',result['pairs'],'models',result['models'],flush=True,file=sys.__stdout__)
            if name=='three_rounds':uninterrupted=(sig,audit)
            if name=='interrupted_resume':assert (sig,audit)==uninterrupted,'Interrupted resume differs from uninterrupted execution'
        original_target=target.read_bytes();prepared=temp/'three_rounds/prep'
        frozen_prepared={p.name:p.read_bytes() for p in prepared.iterdir() if p.name in ('target.cif','target.provenance.json')}
        target.write_bytes(original_target+b'# source changed after completed run\n')
        try:
            try:base_environment(nb,temp/'three_rounds',target,True)
            except ValueError as exc:assert 'changed' in str(exc)
            else:raise AssertionError('Changed source content accepted on actual pipeline preflight resume')
            assert {p.name:p.read_bytes() for p in prepared.iterdir() if p.name in frozen_prepared}==frozen_prepared
        finally:target.write_bytes(original_target)

    assert NOTEBOOK.read_bytes()==raw, 'Test changed delivered notebook'
    assert 'torch' not in sys.modules, 'Real torch imported'
    print(json.dumps({'status':'PASS','scope':'actual delivered pipeline cells + CPU fake engines; no GPU inference',
                      'target_residues':11,'missing_target_NOT_RUN':True,'source_change_resume_refused':True,'pre_stage_frozen_input_refused':True,'cases':results},ensure_ascii=False,indent=2))
    return results

if __name__=='__main__':run()
