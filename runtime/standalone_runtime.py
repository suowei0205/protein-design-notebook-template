"""Explicit standalone identity and observation; standard library, no engines.

This adapter neither impersonates a workbench worker nor writes its database.
"""
from pathlib import Path
import ast,copy,hashlib,html,importlib.metadata,importlib.util,json,os,sys,uuid,unicodedata
from datetime import datetime,timezone,timedelta

LAUNCH_VALUES={'STANDALONE_PACKAGE_ROOT':'','STANDALONE_OUTPUT_ROOT':'','STANDALONE_RESUME':False,'RUN_LABEL':''}

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def atomic(path,value):
 path=Path(path);tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
 with tmp.open('w',encoding='utf8') as f:
  json.dump(value,f,ensure_ascii=False,allow_nan=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)

def normal_document(document):
 """Only deployment settings and saved execution state are identity-neutral."""
 nb=copy.deepcopy(document)
 for c in nb['cells']:
  if c['cell_type']=='code':c['outputs']=[];c['execution_count']=None
 c=nb['cells'][3];source=''.join(c['source']);lines=source.splitlines(keepends=True)
 edits=[]
 for n in ast.parse(source).body:
  if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in LAUNCH_VALUES:
   edits.append((n.lineno-1,n.end_lineno,n.targets[0].id+' = '+repr(LAUNCH_VALUES[n.targets[0].id])+'\n'))
 if len(edits)!=len(LAUNCH_VALUES):raise ValueError('Expected four explicit standalone launch settings')
 for a,b,s in sorted(edits,reverse=True):lines[a:b]=[s]
 c['source']=''.join(lines).splitlines(keepends=True)
 return nb

def sampler_identity():
 """Locate sampler code without importing the inference package or initializing a device."""
 try:
  spec=importlib.util.find_spec('rfd3')
 except (ValueError,ImportError,AttributeError):spec=None
 roots=list(spec.submodule_search_locations or []) if spec else []
 paths=[Path(root)/'model/inference_sampler.py' for root in roots]
 files=[path.resolve() for path in paths if path.is_file()]
 if len(files)!=1:return {'status':'UNAVAILABLE','reason':'Unique rfd3/model/inference_sampler.py not locatable without importing models'}
 return {'status':'AVAILABLE','path':str(files[0]),'sha256':digest(files[0])}

SHANGHAI = timezone(timedelta(hours=8), 'Asia/Shanghai')

def normalize_run_label(value):
 if not isinstance(value,str):raise ValueError('运行名称必须为文字')
 label=unicodedata.normalize('NFC',value.strip()) or '未命名实验'
 if len(label)>40 or any(not (c.isalnum() or unicodedata.category(c).startswith('M') or c in '_-') for c in label):
  raise ValueError('运行名称最多40个字符，仅允许文字、数字、下划线和连字符')
 return label

def allocate_run(project,label,instant=None):
 project=Path(project)
 stamp=(instant or datetime.now(SHANGHAI)).astimezone(SHANGHAI).strftime('%Y-%m-%d_%H%M')
 base='run_'+normalize_run_label(label)+'_'+stamp
 import fcntl
 lockpath=project/'.run_names.lock'
 if lockpath.is_symlink():raise ValueError('运行命名锁不能是符号链接')
 with lockpath.open('a+') as lock:
  fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
  # ponytail: O(existing runs) name scan; index only if large projects make this measurable.
  names={unicodedata.normalize('NFC',p.name).casefold() for p in project.iterdir()}
  number=1
  while True:
   name=base if number==1 else base+'_'+str(number).zfill(2)
   if name.casefold() not in names:
    path=project/name
    try:path.mkdir()
    except FileExistsError:pass
    else:return path.resolve()
   number+=1

def start(package,notebook,branch,namespace,output='',resume=False,background=True,resource_root=None,run_label=''):
 if os.environ.get('PWB_RUN_ID') or os.environ.get('PWB_ATTEMPT_ID'):
  raise ValueError('This is a standalone notebook; use a separate kernel outside the workbench worker.')
 package=Path(package).expanduser().resolve();notebook=Path(notebook).expanduser().resolve()
 resource_root=Path(resource_root).resolve() if resource_root is not None else Path(__file__).resolve().parent
 if resource_root!=Path(__file__).resolve().parent or not resource_root.is_relative_to(package/'.resources'):
  raise ValueError('Runtime must load from this package verified resource cache')
 entries=json.loads((resource_root/'NOTEBOOKS.json').read_text())['entries']
 entry=next((e for e in entries if e['branch']==branch),None)
 if not entry or notebook!=package/entry['filename'] or namespace!=entry['namespace']:
  raise ValueError('Notebook/branch/namespace does not match the explicit packaged entry')
 document=normal_document(json.loads(notebook.read_text()))
 source=hashlib.sha256(json.dumps([(c['id'],c['cell_type'],c['source']) for c in document['cells']],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
 resources=json.loads((resource_root/'RUNTIME_FILES.json').read_text())['files']
 for item in resources:
  p=resource_root/item['path']
  if not p.resolve().is_relative_to(resource_root) or not p.is_file() or p.is_symlink() or digest(p)!=item['sha256']:raise ValueError('Packaged resource missing or changed: '+item['path'])
 label=normalize_run_label(run_label)
 if resume and not output:raise ValueError('Resume requires an explicit existing run directory')
 if not output and any(p.name=='90_ARCHIVE' for p in (notebook.parent,*notebook.parents)):raise ValueError('Output cannot be in research archive')
 root=Path(output).expanduser().resolve() if output else allocate_run(notebook.parent,label)
 allowed_project_run=root.parent==notebook.parent and root.name.startswith('run_')
 if ((root==package or root.is_relative_to(package)) and not allowed_project_run) or any(p.name=='90_ARCHIVE' for p in (root,*root.parents)):
  raise ValueError('Output must be a separate run_ under this design project or outside the package')
 versions={}
 for name in ('rc-foundry','atomworks','biotite','torch','numpy','scipy'):
  try:versions[name]=importlib.metadata.version(name)
  except importlib.metadata.PackageNotFoundError:versions[name]='UNAVAILABLE'
 identity={'schema':'sr56-standalone-layout-run-v3','branch':branch,'namespace':namespace,'notebook_source_sha256':source,
           'resources':resources,'sampler':sampler_identity(),'python':sys.executable,'prefix':sys.prefix,'versions':versions,'output':str(root)}
 if resume:
  if not output or not root.is_dir() or not (root/'checkpoints/standalone_identity.json').is_file():raise ValueError('Resume requires an explicit existing standalone run with identity')
  if json.loads((root/'checkpoints/standalone_identity.json').read_text())!=identity:raise ValueError('Standalone resume identity conflict; create a new run')
  frozen=root/'checkpoints/input/notebook.ipynb'
  if not frozen.is_file() or [(c['id'],c['cell_type'],c['source']) for c in normal_document(json.loads(frozen.read_text()))['cells']]!=[(c['id'],c['cell_type'],c['source']) for c in document['cells']]:raise ValueError('Frozen notebook differs; resume refused')
  state=json.loads((root/'monitor/session.json').read_text())
  if state['namespace']!=namespace or state['branch']!=branch:raise ValueError('Monitor identity conflict')
 elif output:
  if root.exists():raise ValueError('New output directory already exists; choose a new path or explicitly resume')
  root.mkdir(parents=True,exist_ok=False)
 import fcntl
 lock=(root/'.standalone.lock').open('a+')
 try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:
  lock.close();raise RuntimeError('This output directory is already owned by another active notebook kernel')
 try:
  if not resume:
   (root/'checkpoints/input').mkdir(parents=True);atomic(root/'checkpoints/input/notebook.ipynb',document);atomic(root/'checkpoints/standalone_identity.json',identity)
  helper_path=resource_root/'sr56_feedback.py'
  spec=importlib.util.spec_from_file_location('sr56_standalone_feedback_'+uuid.uuid4().hex,helper_path)
  helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
  class StrictSession(helper.Session):
   def event(self,*args,**kwargs):
    if not getattr(self,'_sequence_initialized',False):
     rows=helper.read_events(self.monitor/'events.jsonl')[0]
     self.seq=max((int(r['seq']) for r in rows),default=0);self._sequence_initialized=True
    return super().event(*args,**kwargs)
   def configure(self,config,target,namespace,out_dir):
    fp=hashlib.sha256(helper.dumps(helper.clean(config)).encode()).hexdigest()
    if self.run.get('config_sha256') and self.run['config_sha256']!=fp:raise ValueError('Configuration differs from this run; create a new output directory')
    if namespace!=identity['namespace'] or not Path(out_dir).resolve().is_relative_to(root):raise ValueError('Configuration namespace/output differs from standalone identity')
    if self.run.get('target') and self.run['target']!=helper.clean(target):raise ValueError('Target differs from this run')
    super().configure(config,target,namespace,out_dir)
    saved=helper.read_json(self.monitor/'session.json',{})
    if (self.disabled or saved.get('config_sha256')!=fp or saved.get('namespace')!=namespace
        or saved.get('target')!=helper.clean(target) or saved.get('out_dir')!=str(Path(out_dir).resolve())):
     raise RuntimeError('Failed to commit monitoring configuration')
   def close(self):
    # Lock inode is retained: never unlink/recreate a lock while kernels exist.
    if getattr(self,'_standalone_lock',None):
     fcntl.flock(self._standalone_lock.fileno(),fcntl.LOCK_UN);self._standalone_lock.close();self._standalone_lock=None
   # Hold the directory lock until kernel exit, or an explicit new-run setup.
  session=StrictSession(root,branch,notebook_path=root/'checkpoints/input/notebook.ipynb',namespace=namespace,background=background,run_label=label)
  session._standalone_lock=lock
  session.run.setdefault('run_label',label)
  session.run.setdefault('display_timezone','Asia/Shanghai')
  session.run['layout_version']=3
  helper.write_json(session.monitor/'session.json',session.run)
  if not resume:
   title=html.escape(label)
   (root/'README.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>SR56 运行</title><h1>'+title+'</h1><p>一次运行对应一组参数；恢复需核验原始身份。反馈包为证据快照，非独立续跑包。</p><ul><li><a href="reports/index.html">结果报告（导出后可用）</a></li><li><a href="monitor/index.html">运行监视器</a></li><li><a href="feedback/">反馈快照</a></li></ul></html>',encoding='utf-8')
  os.environ['NESPRIN_RUN_ROOT']=str(root)
  os.environ['NESPRIN_AF3_ZIP']=str(resource_root/'inputs/fold_nesprin_sr54_sr56.zip')
  os.environ['NESPRIN_CANONICAL_FASTA']=str(resource_root/'inputs/Q6ZWQ0.fasta')
  return session
 except BaseException:
  fcntl.flock(lock.fileno(),fcntl.LOCK_UN);lock.close();raise
