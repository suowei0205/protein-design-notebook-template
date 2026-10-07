"""Stdlib acceptance: exact build, blank lifecycle, source and Git boundaries."""
from pathlib import Path
import ast,copy,hashlib,importlib.util,json,shutil,subprocess,sys,tempfile,zipfile
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from build import build
from new_project import create

def rejected(call):
 try:call()
 except (ValueError,RuntimeError,FileNotFoundError,FileExistsError):return
 raise AssertionError('Unsafe operation accepted')

def fingerprint(document):
 n=copy.deepcopy(document);s=''.join(n['cells'][3]['source']);lines=s.splitlines(True)
 node=next(t for t in ast.parse(s).body if isinstance(t,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='RESOURCE_BUNDLE_SHA256' for x in t.targets))
 lines[node.lineno-1:node.end_lineno]=["RESOURCE_BUNDLE_SHA256 = 'RESOURCE_PIN'\n"];n['cells'][3]['source']=''.join(lines).splitlines(True)
 return hashlib.sha256(json.dumps(n,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def bootstrap(package,filename):
 n=json.loads((package/filename).read_text());s=''.join(n['cells'][3]['source'])
 if '# SR56_FEEDBACK_END' in s:s=s.split('# SR56_FEEDBACK_END')[0]
 nodes=[t for t in ast.parse(s).body if not(isinstance(t,ast.Expr) and isinstance(t.value,ast.Call) and isinstance(t.value.func,ast.Name) and t.value.func.id=='_feedback_boot')]
 env={};exec(compile(ast.Module(body=nodes,type_ignores=[]),'actual-bootstrap','exec'),env)
 return n,env

def run():
 build(check=True);compiled=0
 for p in sorted((ROOT/'template').rglob('*.ipynb'))+sorted((ROOT/'examples').rglob('*.ipynb')):
  if '.resources' in p.parts or any(x.startswith('run_') for x in p.parts):continue
  n=json.loads(p.read_text());assert len({c['id'] for c in n['cells']})==len(n['cells'])
  for c in n['cells']:
   if c['cell_type']=='code':assert not c['outputs'] and c['execution_count'] is None;compile(''.join(c['source']),str(p),'exec');compiled+=1
 for directory in ('runtime','scripts','tests'):
  for p in (ROOT/directory).rglob('*.py'):compile(p.read_bytes(),str(p),'exec')
 provenance=json.loads((ROOT/'examples/SR56/PROVENANCE.json').read_text())
 for item in provenance['notebook_fingerprints']:assert fingerprint(json.loads((ROOT/'examples/SR56'/item['path']).read_text()))==item['source_with_pin_normalized_sha256']
 expected={item['path'] for item in provenance['inputs']}
 assert expected=={'inputs/Q6ZWQ0.fasta','inputs/fold_nesprin_sr54_sr56.zip'}
 assert {p.relative_to(ROOT/'examples/SR56').as_posix() for p in (ROOT/'examples/SR56/inputs').rglob('*') if p.is_file()}==expected
 for item in provenance['inputs']:assert hashlib.sha256((ROOT/'examples/SR56'/item['path']).read_bytes()).hexdigest()==item['sha256']
 template=json.loads((ROOT/'template/DesignProject/DesignProject.ipynb').read_text())
 example=json.loads((ROOT/'examples/SR56/SR56_A_minibinder/SR56_A_minibinder.ipynb').read_text())
 assert len(template['cells'])==36 and [c['id'] for c in template['cells']]==[c['id'] for c in example['cells']]
 for i in (15,18,21,24,25,28,30,31,32,33,34):
  actual=ast.parse(''.join(template['cells'][i-1]['source']))
  if i==15:
   assert ast.dump(actual.body[0])==ast.dump(ast.parse('_verify_target_input()').body[0])
   actual.body=actual.body[1:]
  assert ast.dump(actual)==ast.dump(ast.parse(''.join(example['cells'][i-1]['source']))),i
 for i in (4,8,9):assert template['cells'][i-1]['metadata']['jupyter']['source_hidden'] is False
 for package in (ROOT/'template',ROOT/'examples/SR56'):
  with zipfile.ZipFile(package/'resources.zip') as z:
   assert z.testzip() is None and all(not n.startswith(('feedback/','weights/','cache/')) for n in z.namelist())
   for member in json.loads(z.read('RESOURCE_MANIFEST.json'))['files']:assert hashlib.sha256(z.read(member['path'])).hexdigest()==member['sha256']
   for name in ('standalone_runtime.py','sr56_feedback.py'):assert z.read(name)==(ROOT/'runtime'/name).read_bytes()
 with tempfile.TemporaryDirectory(prefix='template-verify-') as tmp:
  temp=Path(tmp).resolve();package=temp/'moved';create(package);rejected(lambda:create(package));rejected(lambda:create(ROOT/'runtime/unsafe'))
  filename='DesignProject/DesignProject.ipynb';n,env=bootstrap(package,filename);res=env['_prepare_resources'](package)
  spec=importlib.util.spec_from_file_location('tested_runtime',res/'standalone_runtime.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  nb=package/filename;s=m.start(package,nb,'template_project','design_template_pipeline_v2',background=False,resource_root=res,run_label=' 模板验证 ')
  lifecycle=dict(env, _feedback=s, _standalone_package=package)
  for i in (6,8,9):exec(compile(''.join(n['cells'][i-1]['source']),'delivered-template','exec'),lifecycle)
  gate=''.join(n['cells'][9]['source']).split('# TEMPLATE_INPUT_GATE_END')[0]
  rejected(lambda:exec(compile(gate,'delivered-input-gate','exec'),lifecycle))
  root=s.root;assert root.parent==nb.parent and root.name.startswith('run_模板验证_')
  state=json.loads((root/'monitor/session.json').read_text());assert state['status']=='NOT_RUN' and state['config']['pipeline_status']=='NOT_RUN' and state['config']['reason']=='TARGET_NOT_CONFIGURED'
  assert state['helix'] is None and state['binder_class'] is None
  for path in ('rankings/main','reports/index.html','monitor/index.html','checkpoints/input/notebook.ipynb'):assert (root/path).exists()
  assert 'NESPRIN · SPECTRIN REPEAT 56' not in (root/'reports/index.html').read_text()
  zipped=list((root/'feedback').glob('*.zip'));assert len(zipped)==1
  sys.path.insert(0,str(ROOT/'runtime'));import sr56_feedback as f
  one=zipped[0];assert f.verify_bundle(one)['computation_status']=='NOT_RUN'
  two=f.export_feedback(root);assert two!=one and one.is_file();f.verify_bundle(two)
  for z in (one,two):assert z.with_suffix('.zip.sha256').read_text()==f.digest(z)+'  '+z.name+'\n'
  # Filled science parameters are type-checked before dependency imports/RNG setup.
  candidate=dict(lifecycle);valid_input=temp/'fake.cif';valid_input.write_text('input exists; parser not reached')
  candidate['TARGET_STRUCTURE_FILE']=str(valid_input)
  exec(compile(gate,'delivered-parameter-guard','exec'),candidate)
  for name,value in (('random_seed',None),('random_seed',True),('random_seed',-1),('random_seed',2**32),('n_batches',True),('low_memory_mode','False'),('step_scale',float('nan'))):
   invalid=dict(candidate);invalid[name]=value
   rejected(lambda e=invalid:exec(compile(gate,'delivered-parameter-guard','exec'),e))
  rejected(lambda:m.start(package,nb,'template_project','design_template_v1',str(root),True,False,res))
  rid=state['run_id'];session=m.start(package,nb,'template_project','design_template_pipeline_v2',str(root),True,False,res,run_label='显示信息')
  assert session.run['run_id']==rid;session.configure(state['config'],state['target'],'design_template_pipeline_v2',root)
  rejected(lambda:session.configure({'seed':123},state['target'],'design_template_pipeline_v2',root))
  rejected(lambda:m.start(package,nb,'template_project','design_template_pipeline_v2',str(root),True,False,res));session.close()
  frozen=root/'checkpoints/input/notebook.ipynb';raw=frozen.read_bytes();bad=json.loads(raw);bad['cells'][8]['source'].append('\nrandom_seed = 2\n');frozen.write_text(json.dumps(bad));rejected(lambda:m.start(package,nb,'template_project','design_template_pipeline_v2',str(root),True,False,res));frozen.write_bytes(raw)
  rejected(lambda:m.start(package,nb,'template_project','design_template_pipeline_v2',str(package),False,False,res))
  for label in ('../escape','a b','x'*41):rejected(lambda:m.normalize_run_label(label))
  assert m.normalize_run_label(' ' )=='未命名实验'
  merged=temp/'merged';f.merge_bundles([one,two],merged);assert len(f.read_json(merged/'merge_index.json')['imports'])==2
 import feedback_protocol;feedback_protocol.run()
 with tempfile.TemporaryDirectory(prefix='template-ignore-') as tmp:
  d=Path(tmp);shutil.copy2(ROOT/'.gitignore',d/'.gitignore');subprocess.run(['git','init','-q'],cwd=d,check=True)
  for path in ('projects/MyTarget/DesignProject.ipynb','template/DesignProject/run_测试/feedback/a.zip','template/.resources/x','weights/x.pt','.env'):
   assert subprocess.run(['git','check-ignore','-q','--no-index',path],cwd=d).returncode==0,path
  for path in ('runtime/sr56_feedback.py','template/resources.zip','examples/SR56/manifest.json','template/DesignProject/DesignProject.ipynb','tests/feedback_protocol.py'):
   assert subprocess.run(['git','check-ignore','-q','--no-index',path],cwd=d).returncode==1,path
 print('PASS: exact resources/pins; 7 notebooks;',compiled,'compiled code cells; source fingerprints; unconfigured complete-pipeline NOT_RUN refusal; strict resume and refusal; feedback trust boundaries; Git include/exclude. No GPU validation.')
if __name__=='__main__':run()
