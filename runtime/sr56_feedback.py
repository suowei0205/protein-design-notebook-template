#!/usr/bin/env python3
"""SR56 offline observation, report and feedback export. Standard library only.

No inference engine is loaded. Existing inference checkpoints remain authoritative.
Use: export RUN_ROOT | render RUN_ROOT | merge ZIP... --output DIR | verify ZIP.
"""
from __future__ import annotations
import argparse, csv, hashlib, importlib.metadata, io, json, math, os, platform, re, shlex
import shutil, stat, subprocess, sys, tempfile, threading, time, traceback, uuid, zipfile, unicodedata
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from pathlib import Path, PurePosixPath

SCHEMA = 'sr56-feedback-v1'  # Session identity remains compatible.
BUNDLE_SCHEMA = 'sr56-feedback-v2'
LAYOUT_VERSION = 2
BRANCHES = [h+'_'+k for k in ('minibinder','short_peptide') for h in 'ABC'] + ['template_project']
HERE = Path(__file__).resolve().parent
ASSETS = HERE/'assets' if (HERE/'assets').is_dir() else HERE.parent/'assets'
_TERMINAL = {'COMPLETED','FAILED','INTERRUPTED','NOT_RUN'}
_SESSIONS = {}

def state_dir(root):
    root=Path(root)
    return root/'monitor' if (root/'monitor/session.json').is_file() or not (root/'state/session.json').is_file() else root/'state'

def now(): return datetime.now(timezone.utc).isoformat(timespec='milliseconds')
def clean(x):
    if isinstance(x, dict): return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x, (list,tuple)): return [clean(v) for v in x]
    if isinstance(x, Path): return str(x)
    if isinstance(x, float) and not math.isfinite(x): return None
    if hasattr(x,'tolist'): return clean(x.tolist())
    if hasattr(x,'item'): return clean(x.item())
    if x is None or isinstance(x,(str,int,float,bool)): return x
    return str(x)
def dumps(x): return json.dumps(clean(x),ensure_ascii=False,allow_nan=False,separators=(',',':'))
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def atomic(path, data, overwrite=True):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex[:8]+'.tmp')
    try:
        if isinstance(data,bytes):tmp.write_bytes(data)
        else:tmp.write_text(data,encoding='utf-8')
        if overwrite:os.replace(tmp,path)
        else:os.link(tmp,path)
    finally:
        if tmp.exists():tmp.unlink()
def write_json(path,obj): atomic(path,dumps(obj)+'\n')
METADATA_LIMITS = {'MANIFEST.json':128*1024**2, 'report.json':1024*1024**2,
                   'SHA256SUMS.txt':128*1024**2}
DATA_SUFFIXES = {'.json','.jsonl','.csv','.tsv','.xvg','.md','.txt','.log',
                 '.mdp','.ndx','.top','.itp','.pdb','.cif','.fasta','.ipynb'}

def bounded_json(path, limit=1024*1024**2):
    path=Path(path)
    if path.stat().st_size>limit:raise ValueError('Feedback metadata exceeds safety limit: '+path.name)
    with path.open('rb') as stream:raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('Feedback metadata exceeds safety limit: '+path.name)
    return json.loads(raw)

def bounded_coordinates(path):
    path=Path(path);limit=25*1024**2
    if path.stat().st_size>limit:raise ValueError('Structure coordinates exceed safety limit')
    with path.open('rb') as stream:raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('Structure coordinates exceed safety limit')
    return raw.decode('utf-8')

def _zip_metadata(z,name):
    limit=METADATA_LIMITS[PurePosixPath(name).name]
    if z.getinfo(name).file_size>limit:raise ValueError('Feedback metadata exceeds safety limit: '+name)
    with z.open(name) as stream:raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('Feedback metadata exceeds safety limit: '+name)
    return raw

def safe_data_path(value):
    # Reject browser URL syntax and aliases even when the filesystem accepts it.
    if not isinstance(value,str) or not value or any(c in value for c in ('\\',':','%','?','#')):return None
    p=PurePosixPath(value)
    if p.is_absolute() or str(p)!=value or '..' in p.parts or any(ord(c)<32 for c in value):return None
    if any(part.endswith((' ','.')) for part in p.parts):return None
    return value

def is_data_member(value):
    return safe_data_path(value) is not None and PurePosixPath(value).suffix.lower() in DATA_SUFFIXES

def read_json(path,default=None):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return default

def read_events(path):
    rows=[];issues=[]
    try:
        with Path(path).open(encoding='utf-8') as stream:
            for index,line in enumerate(stream,1):
                if not line.strip():continue
                try:row=json.loads(line)
                except ValueError:
                    issues.append({'level':'warning','code':'TRUNCATED_EVENT','message':f'事件第{index}行不完整或损坏，已跳过；计数仅采用已提交记录。'});continue
                if isinstance(row,dict):rows.append(row)
    except FileNotFoundError:pass
    return rows,issues

def safe_inside(root,value):
    if not value:return None
    base=Path(root).resolve();p=Path(value)
    if not p.is_absolute():p=base/p
    try:
        resolved=p.resolve();resolved.relative_to(base)
        # Permit OS aliases above ROOT (macOS /var), reject symlinks within evidence.
        for part in (p,*p.parents):
            if part.is_symlink() and base in part.resolve().parents:return None
        if resolved.is_file():return resolved
    except (OSError,ValueError):pass
    return None

def assert_write_path(root,path):
    """Reject linked components beneath a declared output root before writing."""
    root=Path(root).resolve();path=Path(path).absolute()
    try:
        parts=path.relative_to(root).parts
        if '..' in parts:raise ValueError('Noncanonical output path')
        cursor=root
        for part in parts:
            cursor=cursor/part
            if cursor.is_symlink():raise ValueError('Output symlink rejected: '+str(cursor))
        path.resolve().relative_to(root)
    except ValueError as exc:raise ValueError('Unsafe output path: '+str(path)) from exc
    return path


def assert_write_tree(root,path):
    path=assert_write_path(root,path)
    if path.is_dir():
        for child in path.rglob('*'):
            if child.is_symlink():raise ValueError('Output symlink rejected: '+str(child))
    return path

def relative(root,p):return str(Path(p).resolve().relative_to(Path(root).resolve())).replace(os.sep,'/')
def stable_key(c):
    score=c.get('ranking_score');finite=isinstance(score,(int,float)) and not isinstance(score,bool) and math.isfinite(score)
    return (0 if finite else 1,-score if finite else 0,
            tuple(int(c.get(k) or 0) for k in ('design_index','round','parent_index','backbone','sequence_index','model_index')))

class NullSession:
    def event(self,*a,**k):pass
    def configure(self,*a,**k):pass
    def finish(self,*a,**k):pass

def _warn(exc):
    try:sys.__stderr__.write('[SR56 feedback] '+sanitize_text(exc)+'\n')
    except Exception:pass

def _safe(method):
    def wrapped(self,*a,**k):
        if getattr(self,'disabled',False):return None
        try:return method(self,*a,**k)
        except Exception as e:
            _warn(type(e).__name__+': '+str(e))
            try:atomic(self.monitor/'feedback_error.txt',sanitize_text(traceback.format_exc()))
            except Exception:pass
            return None
    return wrapped

def sanitize_text(text):
    """Mask labelled credentials, including complete multiword authorization values."""
    return re.sub(r'(?im)((?:["\']?(?:token|api[_-]?key|authorization|password)["\']?)\s*[=:]\s*)[^\r\n]*',
                  r'\1[REDACTED]',str(text))

def sanitize_messages(value):
    if isinstance(value,dict):
        return {k:(sanitize_text(v) if k in ('message','traceback','error','error_message') and isinstance(v,str)
                   else sanitize_messages(v)) for k,v in value.items()}
    if isinstance(value,list):return [sanitize_messages(v) for v in value]
    return value

class _Tee:
    def __init__(self,original,path):
        self.original=original;self.path=path;self.pending='';self.continuing_secret=False
    def _append(self,text):
        try:
            with self.path.open('a',encoding='utf-8') as f:f.write(text);f.flush()
        except OSError:pass
    def write(self,text):
        result=self.original.write(text);self.pending+=text
        while '\n' in self.pending:
            line,self.pending=self.pending.split('\n',1)
            self._append(('[REDACTED]' if self.continuing_secret else sanitize_text(line))+'\n')
            self.continuing_secret=False
        # Avoid unbounded retention for long lines; suppress the continuation rather than leak it.
        if len(self.pending)>65536:
            self._append(sanitize_text(self.pending[:65536])+'[TRUNCATED]')
            self.pending='';self.continuing_secret=True
        return result
    def drain(self):
        if self.pending:
            self._append('[REDACTED]' if self.continuing_secret else sanitize_text(self.pending))
            self.continuing_secret=self.continuing_secret or bool(re.search(r'(?i)(token|api[_-]?key|authorization|password)\s*[=:]',self.pending))
            self.pending=''
    def flush(self):
        # A partial print may continue after flush; keep it until a full line or terminal drain.
        self.original.flush()
    def __getattr__(self,n):return getattr(self.original,n)

class Session:
    def __init__(self,root,branch,notebook_path=None,notebook_sha256=None,namespace=None,background=True,run_label=None):
        if branch not in BRANCHES:raise ValueError('Unknown branch '+str(branch))
        self.root=Path(root).resolve();self.monitor=state_dir(self.root);self.monitor.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.disabled=False;self.finished=False;self.seq=0;self.hook=None;self.tees=[]
        previous=read_json(self.monitor/'session.json')
        nb=Path(notebook_path) if notebook_path else None
        actual_sha=digest(nb) if nb and nb.is_file() else notebook_sha256
        document=read_json(nb,{}) if nb and nb.is_file() else {}
        source_sha=hashlib.sha256(dumps([(c.get('id'),c.get('cell_type'),c.get('source')) for c in document.get('cells',[])]).encode()).hexdigest() if document else actual_sha
        if previous and (previous.get('branch')!=branch or previous.get('notebook_source_sha256',previous.get('notebook_sha256'))!=source_sha):
            raise ValueError('监视运行身份不匹配；请使用新的运行目录。原监视记录保持不变。')
        self.run=previous or {'schema':SCHEMA,'run_id':uuid.uuid4().hex,'branch':branch,'helix':branch[0] if branch!='template_project' else None,
            'binder_class':branch.split('_',1)[1] if branch!='template_project' else None,'run_label':run_label,'notebook_sha256':actual_sha,'notebook_source_sha256':source_sha,'created_at':now(),'attempts':[]}
        self.attempt=uuid.uuid4().hex[:12]
        self.run.pop('ended_at',None)
        self.run.update(session_path=str(self.monitor/'session.json'),attempt_id=self.attempt,status='RUNNING',namespace=namespace or self.run.get('namespace'),source_root=str(self.root))
        self.run['attempts'].append({'attempt_id':self.attempt,'started_at':now(),'pid':os.getpid(),'notebook_file_sha256':actual_sha})
        write_json(self.monitor/'session.json',self.run)
        if nb and nb.is_file():shutil.copy2(nb,self.monitor/'executed_notebook.ipynb')
        self.event('START','session',key=self.attempt,pid=os.getpid())
        try:
            ip=get_ipython()  # noqa: F821
        except NameError:
            try:
                from IPython import get_ipython
                ip=get_ipython()
            except ImportError:ip=None
        self.ip=ip
        if ip:
            def hook(result):
                exc=getattr(result,'error_before_exec',None) or getattr(result,'error_in_exec',None)
                if exc and not self.finished and not getattr(exc,'sr56_setup_rejected',False):
                    state=read_json(self.monitor/'monitor_state.json',{})
                    self.event('ERROR',state.get('stage','notebook'),key=state.get('key',''),error_type=type(exc).__name__,message=str(exc),
                               traceback=''.join(traceback.format_exception(type(exc),exc,exc.__traceback__))[-30000:])
                    self.finish('INTERRUPTED' if isinstance(exc,KeyboardInterrupt) else 'FAILED')
            self.hook=hook;ip.events.register('post_run_cell',hook)
            for name in ('stdout','stderr'):
                old=getattr(sys,name);tee=_Tee(old,self.monitor/(name+'.log'));setattr(sys,name,tee);self.tees.append((name,old,tee))
        if background:
            log=(self.monitor/'observer.log').open('ab')
            try:
                subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'watch',str(self.root),'--attempt',self.attempt,'--pid',str(os.getpid())],
                    stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=(os.name!='nt'))
            finally:log.close()
    @_safe
    def configure(self,config,target,namespace,out_dir):
        config=clean(config);fp=hashlib.sha256(dumps(config).encode()).hexdigest()
        if self.run.get('config_sha256') and self.run['config_sha256']!=fp:
            self.event('ERROR','configuration',message='配置改变，监视记录拒绝混入原运行。')
            self.disabled=True;raise ValueError('Monitoring configuration identity conflict')
        versions={}
        for name in ('rc-foundry','atomworks','biotite','torch','numpy','scipy'):
            try:versions[name]=importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:versions[name]='NOT AVAILABLE'
        self.run.update(config=config,target=clean(target),namespace=namespace,out_dir=str(Path(out_dir).resolve()),
            config_sha256=fp,environment={'python':platform.python_version(),'platform':platform.system(),'versions':versions})
        write_json(self.monitor/'session.json',self.run)
        self.event('CONFIGURED','configuration',config_sha256=fp)
    @_safe
    def event(self,event,stage,key='',**data):
        with self.lock:
            self.seq+=1
            row={'seq':self.seq,'run_id':self.run['run_id'],'attempt_id':self.attempt,'ts':now(),
                 'monotonic_ns':time.monotonic_ns(),'event':event,'stage':stage,'key':str(key),'data':sanitize_messages(clean(data))}
            with (self.monitor/'events.jsonl').open('a',encoding='utf-8') as f:f.write(dumps(row)+'\n');f.flush()
            state={'run_id':self.run['run_id'],'attempt_id':self.attempt,'stage':stage,'event':event,'key':str(key),'updated_at':row['ts']}
            write_json(self.monitor/'monitor_state.json',state)
    @_safe
    def finish(self,status='COMPLETED'):
        if self.finished:return
        if status not in _TERMINAL:raise ValueError(status)
        self.event('END','session',key=self.attempt,status=status)
        self.run.update(status=status,ended_at=now());write_json(self.monitor/'session.json',self.run)
        self.finished=True
        if self.hook and self.ip:
            try:self.ip.events.unregister('post_run_cell',self.hook)
            except ValueError:pass
        for name,old,tee in self.tees:
            tee.drain()
            if getattr(sys,name) is tee:setattr(sys,name,old)
        try:
            path=export_feedback(self.root)
            print('离线反馈包:',path)
        except Exception as e:
            _warn('计算状态已保存，反馈导出失败，可手动重试: '+str(e))
            atomic(self.monitor/'feedback_error.txt',sanitize_text(traceback.format_exc()))

def start(root,branch,**kwargs):
    key=str(Path(root).resolve())
    prior=_SESSIONS.get(key)
    if prior and not prior.finished:
        # Re-running setup is a new attempt; retire hooks without marking computation complete.
        prior.event('END','attempt',status='RESTARTED')
        prior.finished=True
        if prior.hook and prior.ip:
            try:prior.ip.events.unregister('post_run_cell',prior.hook)
            except ValueError:pass
        for name,old,tee in prior.tees:
            tee.drain()
            if getattr(sys,name) is tee:setattr(sys,name,old)
    try:session=Session(root,branch,**kwargs);_SESSIONS[key]=session;return session
    except Exception as e:_warn(e);return NullSession()

def resource_sample(pid):
    sample={'ts':now(),'gpus':[],'availability':'unavailable','process_alive':None}
    try:os.kill(pid,0);sample['process_alive']=True
    except ProcessLookupError:sample['process_alive']=False
    except (PermissionError,OSError):pass
    exe=shutil.which('nvidia-smi')
    if not exe:return sample
    try:
        r=subprocess.run([exe,'--query-gpu=uuid,name,utilization.gpu,memory.used,memory.total','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5,check=True)
        procs=subprocess.run([exe,'--query-compute-apps=gpu_uuid,pid,used_memory','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5)
        own={}
        if procs.returncode==0:
            for row in csv.reader(io.StringIO(procs.stdout)):
                if len(row)==3 and row[1].strip()==str(pid):
                    try:own[row[0].strip()]=float(row[2])
                    except ValueError:pass
        def number(v):
            try:return float(v)
            except ValueError:return None
        for row in csv.reader(io.StringIO(r.stdout)):
            if len(row)!=5:continue
            gpu_id,name,util,used,total=[v.strip() for v in row]
            sample['gpus'].append({'uuid':gpu_id,'name':name,'utilization_pct':number(util),'memory_used_mb':number(used),
                'memory_total_mb':number(total),'process_memory_mb':own.get(gpu_id)})
        sample['availability']='available'
    except (OSError,subprocess.SubprocessError):pass
    return sample

def watch(root,attempt,pid):
    root=Path(root);monitor=state_dir(root);last_render=0
    while True:
        run=read_json(monitor/'session.json',{})
        if run.get('attempt_id')!=attempt or run.get('status') in _TERMINAL:return
        sample=resource_sample(pid);sample['attempt_id']=attempt
        with (monitor/'resources.jsonl').open('a',encoding='utf-8') as f:f.write(dumps(sample)+'\n')
        write_json(monitor/'collector.json',sample)
        if time.monotonic()-last_render>=30:
            try:render_report(root,monitor,mode='monitor',structures=False)
            except Exception:atomic(monitor/'render_error.txt',sanitize_text(traceback.format_exc()))
            last_render=time.monotonic()
        if sample['process_alive'] is False:
            # Observer never declares compute success. The parent may have been killed.
            atomic(monitor/'observer_notice.txt','父进程已退出；最终结束状态未提交。请手动导出部分反馈。\n')
            return
        time.sleep(15)

_HASH_CACHE = {}
_RECEIPT_CACHE = {}
def checkpoint_receipts(root,run,issues,strict=True):
    """Reconcile atomic receipts, including commits whose observation was interrupted."""
    root=Path(root).resolve();out=Path(run.get('out_dir') or root/'__not_configured__')
    try:out.resolve().relative_to(root)
    except ValueError:raise ValueError('Checkpoint directory outside run root')
    receipts={};hashes={}
    # ponytail: v1 still scans/stats O(existing receipts/artifacts), not O(new work).
    # Parsed receipts and artifact hashes are memoized; introduce an index only after measurement.
    patterns=('checkpoints/main/checkpoint.json','checkpoints/refine/refine_complete.json','checkpoints/main/rf3/complete.json','checkpoints/main/rf3/*/complete.json','checkpoints/refine/rf3/*/complete.json','state/checkpoint.json','state/refine_complete.json','refine_complete.json','main_rf3/complete.json','main_rf3/*/complete.json','refine_rf3/*/complete.json','checkpoint.json','main_*/checkpoint.json','rf3_persist_*/complete.json','rf3_persist_*/d*/complete.json','refine_*/refine_complete.json','refine_*/rf3/*/complete.json')
    paths=sorted({p for base in {out,root} for pattern in patterns for p in base.glob(pattern)}) if not strict else sorted({p for base in {out,root/'checkpoints'} for p in base.rglob('*.json') if p.name in ('checkpoint.json','complete.json','refine_complete.json')})
    paths=[p for p in paths if safe_inside(root,p) is not None and not any(part in ('feedback','preview','live','resources','assets','data','weights','cache') for part in p.relative_to(root).parts)]
    for path in paths:
        sig=(str(path),path.stat().st_mtime_ns,path.stat().st_size)
        cached=_RECEIPT_CACHE.get(str(path)) if not strict else None
        if cached and cached[0]==sig:blob,raw_hash=cached[1:]
        else:
            raw=path.read_bytes()
            try:blob=json.loads(raw)
            except (ValueError,UnicodeDecodeError):blob=None
            raw_hash=hashlib.sha256(raw).hexdigest()
            if not strict:_RECEIPT_CACHE[str(path)]=(sig,blob,raw_hash)
        if not isinstance(blob,dict):
            issues.append({'level':'error','code':'CHECKPOINT_UNREADABLE','message':relative(root,path)});continue
        hashes[str(path)]=raw_hash
        for key,rec in blob.items():
            if not isinstance(rec,dict) or 'payload' not in rec:continue
            stage=None;identity=key
            if re.fullmatch(r'rfd3_batch_\d+',key):stage='main_rfd3'
            elif re.fullmatch(r'mpnn_design_\d+',key):stage='main_mpnn'
            elif re.fullmatch(r'rf3_\d+_\d+',key):stage='main_rf3'
            elif re.fullmatch(r'D\d+_C\d+_P\d+_rfd3',key):stage='refine_rfd3'
            elif re.fullmatch(r'D\d+_C\d+_P\d+_K\d+_mpnn',key):stage='refine_mpnn'
            elif re.fullmatch(r'D\d+_C\d+_round',key):stage='refine_round'
            elif key=='rf3' and re.fullmatch(r'D\d+_C\d+_P\d+_K\d+_S\d+',path.parent.name):
                stage='refine_rf3';identity=path.parent.name
            if key=='rf3' and re.fullmatch(r'd\d+_s\d+',path.parent.name):
                di,si=re.findall(r'\d+',path.parent.name);stage='main_rf3';identity=f'rf3_{di}_{si}'
            if not stage:continue
            try:
                if rec.get('run_namespace')!=run.get('namespace') or rec.get('schema')!=run.get('config',{}).get('CACHE_SCHEMA'):
                    raise ValueError('cache identity mismatch')
                for item in rec.get('files',[]):
                    p=safe_inside(root,item.get('path'))
                    if p is None:raise ValueError('artifact missing or outside run')
                    sig=(str(p),p.stat().st_mtime_ns,p.stat().st_size)
                    cached_hash=_HASH_CACHE.get(str(p))
                    actual=digest(p) if strict or not cached_hash or cached_hash[0]!=sig else cached_hash[1]
                    _HASH_CACHE[str(p)]=(sig,actual)
                    if actual!=item.get('sha256'):raise ValueError('artifact SHA-256 mismatch')
                    hashes[str(p)]=actual
                receipts[(stage,identity)]={'stage':stage,'key':identity,'data':rec['payload'],
                    'event':'CHECKPOINT','ts':datetime.fromtimestamp(rec['ts'],timezone.utc).isoformat(),
                    'checkpoint':relative(root,path),'files':{str(safe_inside(root,item.get('path'))):item.get('sha256') for item in rec.get('files',[])}}
            except (OSError,ValueError,KeyError,TypeError) as exc:
                issues.append({'level':'error','code':'CHECKPOINT_REJECTED','stage':stage,'message':relative(root,path)+' / '+key+': '+str(exc)})
    return receipts,hashes

def stage_unit(stage):
    return '模型' if stage.endswith('rf3') else '序列' if stage.endswith('mpnn') else '骨架' if stage.endswith('rfd3') else '记录'

def returned_units(stage,payload):
    if stage.endswith('rf3'):return len(payload.get('models',[]))
    return payload.get('n_generated',len(payload.get('paths',[]))) or 0

def copy_evidence(source,destination):
    if source.suffix.lower() in ('.log','.txt','.jsonl'):
        with source.open(encoding='utf-8') as src,destination.open('w',encoding='utf-8') as dst:
            for line in src:
                if source.suffix.lower()=='.jsonl':
                    try:line=dumps(sanitize_messages(json.loads(line)))+'\n'
                    except ValueError:line=sanitize_text(line)
                else:line=sanitize_text(line)
                dst.write(line)
    else:shutil.copy2(source,destination)

def report_projection(data):
    result={k:v for k,v in data.items() if k not in ('candidates','artifacts','checkpoint_hashes','events')}
    result.update(candidates=[],artifacts=[],events=[sanitize_messages(e) for e in data.get('events',[])[-150:] if e.get('event') not in ('MODEL','PAIR')],
                  layout_version=LAYOUT_VERSION,evidence_files={'candidates':'reports/data/candidates.json','artifacts':'reports/artifact_index.json','checkpoint_hashes':'reports/data/checkpoint_hashes.json'},
                  raw_events=('state' if '/state/' in str(data.get('run',{}).get('session_path','')) else 'monitor')+'/events.jsonl')
    return result

def write_report_data(data,destination):
    destination=Path(destination)/'reports'
    write_json(destination/'data/candidates.json',data.get('candidates',[]))
    write_json(destination/'artifact_index.json',data.get('artifacts',[]))
    write_json(destination/'data/checkpoint_hashes.json',data.get('checkpoint_hashes',{}))
    write_json(destination/'report.json',report_projection(data))

def load_report_data(source):
    source=Path(source)
    entry='reports/report.json' if (source/'reports/report.json').is_file() else 'report.json'
    report_path=safe_inside(source,entry)
    if report_path is None:raise ValueError('Missing or unsafe report metadata')
    data=bounded_json(report_path,METADATA_LIMITS['report.json'])
    version=data.get('layout_version',1)
    if isinstance(version,bool) or version not in (1,2) or (version==2)!=(entry=='reports/report.json'):raise ValueError('Unsupported report layout')
    for key,rel in data.get('evidence_files',{}).items():
        if key not in ('candidates','artifacts','checkpoint_hashes') or safe_data_path(rel) is None:raise ValueError('Unsafe report evidence reference')
        path=safe_inside(source,rel)
        if path is None:raise ValueError('Missing report evidence: '+rel)
        data[key]=bounded_json(path)
    return data

_MONITOR_CACHE={}
def _compact_assessment(data):
    paths=[data.get('cif'),data.get('conf'),data.get('sequence')]
    return (hashlib.sha256(dumps(paths).encode()).hexdigest(),data.get('assessment_artifacts'),data.get('valid_output'))

def _stream_monitor_events(path,state,run,resources=False):
    """Incremental reduction: retain keys/counts/fingerprints, never model/event arrays."""
    path=Path(path);key='resource' if resources else 'event'
    if not path.is_file():return
    stat=path.stat();signature=(stat.st_dev,stat.st_ino)
    if state.get(key+'_inode')!=signature or stat.st_size<state.get(key+'_offset',0):
        state[key+'_offset']=0;state[key+'_inode']=signature
        if resources:state['resources']=deque(maxlen=240)
        else:
            state.update(models={},jobs={},starts={},ends={},tail=deque(maxlen=150),stage_end={},progress=None)
    with path.open('rb') as src:
        src.seek(state.get(key+'_offset',0))
        while True:
            before=src.tell();line=src.readline()
            if not line:break
            if not line.endswith(b'\n'):src.seek(before);break
            state[key+'_offset']=src.tell()
            try:event=json.loads(line)
            except (ValueError,UnicodeDecodeError):continue
            if not isinstance(event,dict):continue
            if resources:
                state['resources'].append(event);continue
            if event.get('run_id')!=run['run_id']:continue
            kind=event.get('event');stage=event.get('stage');job=(stage,event.get('key'));data=event.get('data') or {}
            if not isinstance(data,dict):continue
            if kind=='MODEL':state['models'][str(data.get('id') or event['key'])]=_compact_assessment(data)
            elif kind not in ('PAIR',):state['tail'].append(sanitize_messages(event))
            if kind in ('COMMITTED','MODEL','PAIR'):state['progress']=max(state.get('progress') or '',event.get('ts',''))
            if event.get('attempt_id')==run.get('attempt_id'):
                if kind=='START':state['starts'][job]=event.get('monotonic_ns',0);state['stage_end'][stage]='RUNNING'
                if kind in ('COMMITTED','REUSED'):
                    state['jobs'][job]=kind;state['ends'][job]=event.get('monotonic_ns',0)
                if kind=='END':state['stage_end'][stage]=data.get('status','COMPLETED')

def collect_monitor(root):
    root=Path(root).resolve();run=read_json(state_dir(root)/'session.json',{})
    if run.get('schema')!=SCHEMA:raise ValueError('Missing supported monitoring identity')
    key=(str(root),run['run_id'],run.get('attempt_id'));state=_MONITOR_CACHE.setdefault(key,{})
    _stream_monitor_events(state_dir(root)/'events.jsonl',state,run)
    _stream_monitor_events(state_dir(root)/'resources.jsonl',state,run,True)
    issues=[];receipts,_=checkpoint_receipts(root,run,issues,strict=False)
    jobs=state.get('jobs',{});counts=defaultdict(int);stages=[];model_ids=set();valid=invalid=legacy=0
    for (stage,item),receipt in receipts.items():
        payload=receipt['data']
        if stage.endswith('rf3'):
            pair=('main:D%s:S%s'%tuple(map(int,item.split('_')[1:]))) if stage=='main_rf3' else ('refine:D%s:C%s:P%s:K%s:S%s'%tuple(map(int,re.findall(r'\d+',item))))
            for model in payload.get('models',[]):
                mid=pair+':M'+str(model['mi']);model_ids.add(mid);assessment=state.get('models',{}).get(mid)
                if not assessment:continue
                paths=[model.get('cif'),model.get('conf'),payload.get('input_seq')]
                if assessment[0]!=hashlib.sha256(dumps(paths).encode()).hexdigest():continue
                binding=assessment[1]
                if binding is None:legacy+=1
                elif not all(binding.get(k+'_sha256') and binding[k+'_sha256']==receipt['files'].get(str(safe_inside(root,model.get(k)))) for k in ('cif','conf')):continue
                valid+=assessment[2] is True;invalid+=assessment[2] is False
    cfg=run.get('config',{})
    for stage in ('main_rfd3','main_mpnn','main_rf3','refine_rfd3','refine_mpnn','refine_rf3','refine_round','export'):
        selected={k:v for k,v in receipts.items() if k[0]==stage};new=sum(jobs.get(k)=='COMMITTED' for k in selected);reused=sum(jobs.get(k)=='REUSED' for k in selected)
        duration=sum(max(0,(state['ends'][k]-state['starts'][k])/1e9) for k in selected if jobs.get(k)=='COMMITTED' and k in state.get('starts',{}))
        stages.append({'stage':stage,'status':state.get('stage_end',{}).get(stage,state.get('stage_end',{}).get('refine','OBSERVED' if selected else 'NOT_STARTED') if stage.startswith('refine') else ('OBSERVED' if selected else 'NOT_STARTED')),
                       'requested':sum(v['data'].get('n_requested',v['data'].get('n_requested_models',0)) or 0 for v in selected.values()),'requested_unit':stage_unit(stage),
                       'actual':len(selected),'completed':len(selected),'submitted_work_items':len(selected),'work_item_unit':'工作项',
                       'returned_units':sum(returned_units(stage,v['data']) for v in selected.values()),'new':new,'reused':reused,
                       'attempt_scope':'CURRENT_ATTEMPT','invalid':None,'duration_s':duration if new else None,'duration_scope':'CURRENT_ATTEMPT_NEW_INFERENCE'})
        counts['new_jobs']+=new;counts['reused_jobs']+=reused
    counts.update(planned_backbones=cfg.get('total_designs'),planned_main_pairs=cfg.get('main_pair_limit'),planned_refine_pairs=cfg.get('refine_pair_limit'),
                  rfd3_generated=sum(returned_units(s,r['data']) for (s,k),r in receipts.items() if s=='main_rfd3'),
                  mpnn_sequences=sum(returned_units(s,r['data']) for (s,k),r in receipts.items() if s=='main_mpnn'),
                  rf3_pairs=sum(s in ('main_rf3','refine_rf3') for s,k in receipts),rf3_models=len(model_ids),valid_models=valid,invalid_models=invalid,
                  assessment_missing=len(model_ids)-valid-invalid,legacy_unbound_assessments=legacy,attempt_scope='CURRENT_ATTEMPT')
    if legacy:issues.append({'level':'warning','code':'LEGACY_UNBOUND_ASSESSMENT','message':f'{legacy} 条历史评估仅路径与序列匹配，未记录工件绑定散列。'})
    collector=read_json(state_dir(root)/'collector.json',{});resources=list(state.get('resources',[]));events=list(state.get('tail',[]));progress=max([state.get('progress') or '']+[r['ts'] for r in receipts.values()]) or None
    if any(i['code'] in ('CHECKPOINT_REJECTED','CHECKPOINT_UNREADABLE') for i in issues):run=dict(run,status='EVIDENCE_INCOMPLETE')
    return {'schema':'sr56-report-v1','mode':'monitor','synthetic':run.get('synthetic',False),'generated_at':now(),
            'source_cutoff':max([run['created_at']]+[e.get('ts','') for e in events]+[r.get('ts','') for r in resources]+[collector.get('ts','')]),
            'run':run,'counts':dict(counts),'stages':stages,'events':events,'resources':resources,'candidates':[],'artifacts':[],
            'downloads':[],'branches':[],'issues':issues,'lineage':[],'refine_effects':[],'round_outcomes':[],
            'integrity':{'status':'SOURCE_SNAPSHOT','scope':'已核验工作项计数；评估绑定状态另列；CURRENT ATTEMPT 缓存时间不作为推理时间'},
            'progress_at':progress,'artifact_at':progress,'collector_at':collector.get('ts')}

# Outcome counts use verified receipts, never file mtime/count guesses.
def collect(root,mode='report'):
    root=Path(root).resolve();run=read_json(state_dir(root)/'session.json')
    if not run or run.get('schema')!=SCHEMA:raise ValueError('缺少受支持的 monitor/session.json；请使用接入监视器的新 notebook。')
    events,issues=read_events(state_dir(root)/'events.jsonl')
    events=[sanitize_messages(e) for e in events if e.get('run_id')==run['run_id']]
    resources,ri=read_events(state_dir(root)/'resources.jsonl');issues+=ri
    models={};pairs={};jobs={};starts={};duration=defaultdict(float);timed=set();reuses=set();new=set();lineage={};final={};stage_end={};current_jobs={};current_ends={}
    for e in events:
        data=e.get('data') or {}
        if not isinstance(data,dict):continue
        key=(e.get('stage'),e.get('key'));kind=e.get('event');attempt=e.get('attempt_id')
        if kind=='START':starts[(attempt,*key)]=e
        if kind in ('COMMITTED','REUSED'):
            # Latest observation of a committed key, one job even after multiple recoveries.
            jobs[key]=e
            if attempt!=run.get('attempt_id'):continue
            current_jobs[key]=kind;current_ends[key]=e
            if kind=='REUSED':reuses.add(key);new.discard(key)
            else:
                new.add(key);reuses.discard(key);begin=starts.get((attempt,*key))
                if begin and (attempt,*key) not in timed and key not in reuses:
                    timed.add((attempt,*key))
                    elapsed=max(0,(e.get('monotonic_ns',0)-begin.get('monotonic_ns',0))/1e9)
                    duration[e['stage']]+=elapsed
        if kind=='START' and attempt==run.get('attempt_id'):stage_end[e['stage']]='RUNNING'
        if kind=='END' and attempt==run.get('attempt_id'):stage_end[e['stage']]=data.get('status','COMPLETED')
        if kind=='MODEL':
            c=dict(data);c['id']=str(c.get('id') or e['key']);c.setdefault('pair_id',c['id'].rsplit(':M',1)[0])
            sm=c.pop('summary',{}) or {}
            for k in ('ranking_score','iptm','ptm','overall_plddt','overall_pae','has_clash'):c[k]=clean(sm.get(k,c.get(k)))
            c['errors']=c.get('errors') or []
            if isinstance(c['errors'],str):c['errors']=c['errors'].split('|')
            c.setdefault('metrics',{});c.setdefault('round',0);models[c['id']]=c
        if kind=='PAIR':pairs[e['key']]=data
        if kind=='LINEAGE':
            child=data.get('child_id');parent=data.get('parent_id')
            if child:lineage[(parent,child)]=dict(data)
        if kind=='FINAL_SELECTED':final[(data.get('selection',e['stage']),data.get('design_index'))]=dict(data,id=data.get('id') or e['key'])
        if kind in ('ERROR','INVALID'):
            issues.append({'level':'error' if kind=='ERROR' else 'info','code':kind,'message':str(data.get('message') or data.get('errors') or '无效输入'),
                'stage':e['stage'],'ts':e['ts'],'key':e.get('key'),'traceback':data.get('traceback')})
    receipts,checkpoint_hashes=checkpoint_receipts(root,run,issues,strict=mode!='monitor')
    for key in set(jobs)-set(receipts):
        issues.append({'level':'warning','code':'UNCONFIRMED_EVENT','stage':key[0],'message':'事件没有可核验断点，不计完成：'+key[1]})
    jobs=receipts
    new.intersection_update(jobs);reuses.intersection_update(jobs)
    duration=defaultdict(float)
    for key,kind in current_jobs.items():
        end=current_ends.get(key)
        begin=starts.get((run.get('attempt_id'),*key))
        if kind=='COMMITTED' and key in jobs and begin and end:duration[key[0]]+=max(0,(end.get('monotonic_ns',0)-begin.get('monotonic_ns',0))/1e9)
    pairs={};committed_model_ids=set()  # Only atomic receipts count as completed inference pairs.
    for (stage,key),receipt in receipts.items():
        if stage not in ('main_rf3','refine_rf3'):continue
        rec=receipt['data']
        if stage=='main_rf3':
            di,si=map(int,key.split('_')[1:]);pair=f'main:D{di}:S{si}'
            identity={'design_index':di,'sequence_index':si,'round':0}
        else:
            di,rnd,pi,k,si=map(int,re.findall(r'\d+',key));pair=f'refine:D{di}:C{rnd}:P{pi}:K{k}:S{si}'
            identity={'design_index':di,'round':rnd,'parent_index':pi,'backbone':k,'sequence_index':si}
        pairs.setdefault(pair,rec)
        for model in rec.get('models',[]):
            mid=pair+':M'+str(model['mi'])
            committed_model_ids.add(mid)
            if mid in models:
                assessment=models[mid]
                expected=receipt.get('files',{})
                same_paths=all(safe_inside(root,model.get(k)) is not None and str(safe_inside(root,assessment.get(k)))==str(safe_inside(root,model.get(k))) for k in ('cif','conf'))
                same_input=assessment.get('sequence')==rec.get('input_seq')
                binding=assessment.get('assessment_artifacts')
                matches=same_paths and same_input and all(expected.get(str(safe_inside(root,model.get(k))))==binding.get(k+'_sha256') and binding.get(k+'_sha256') for k in ('cif','conf')) if isinstance(binding,dict) else False
                if matches:
                    assessment['assessment_binding']='VERIFIED_RECEIPT';continue
                if binding is None and same_paths and same_input:
                    assessment['assessment_binding']='LEGACY_UNBOUND'
                    issues.append({'level':'warning','code':'LEGACY_UNBOUND_ASSESSMENT','message':mid+' 旧评估路径与序列一致，但未记录评估工件散列；不声称散列绑定。'})
                    continue
                issues.append({'level':'warning','code':'ASSESSMENT_IDENTITY_MISMATCH','message':mid+' 评估与当前已核验工作项不一致；旧指标、排名与选择已排除。'})
                models.pop(mid,None)
            summary={}
            models[mid]={**identity,'id':mid,'pair_id':pair,'model_index':model['mi'],'sequence':rec.get('input_seq'),
                'valid_output':None,'errors':['assessment_not_committed'],'metrics':{},**summary,
                'cif':model.get('cif'),'conf':model.get('conf'),'assessment_status':'UNASSESSED','assessment_binding':'UNASSESSED'}
            issues.append({'level':'warning','code':'ASSESSMENT_MISSING','stage':stage,'message':mid+' 已保存预测；有效性评估未提交，等待恢复。'})
    models={mid:c for mid,c in models.items() if mid in committed_model_ids}
    def assessed(mid):return mid in models and models[mid].get('assessment_binding') in ('VERIFIED_RECEIPT','LEGACY_UNBOUND')
    for item in final.values():
        if not assessed(item.get('id')):issues.append({'level':'warning','code':'SELECTION_EVIDENCE_MISSING','message':str(item.get('id'))+' 未找到与当前工件一致的已提交评估；不作为最终选择。'})
    final={k:v for k,v in final.items() if assessed(v.get('id'))}
    for item in lineage.values():
        if not assessed(item.get('parent_id')) or not assessed(item.get('child_id')):issues.append({'level':'warning','code':'LINEAGE_EVIDENCE_MISSING','message':str(item.get('parent_id'))+' -> '+str(item.get('child_id'))+' 缺少当前工件对应的父或子评估；不展示为已核验保留路径。'})
    lineage={k:v for k,v in lineage.items() if assessed(v.get('child_id')) and assessed(v.get('parent_id'))}
    for selected in final.values():
        if assessed(selected['id']):
            c=models[selected['id']];c['final_selected']=True
            if selected.get('formal_rank') is not None:c['formal_rank']=selected['formal_rank']
            c['selection']=selected.get('selection')
    candidates=sorted(models.values(),key=stable_key)
    grouped=defaultdict(list)
    for c in candidates:grouped[c['pair_id']].append(c)
    for group in grouped.values():
        valid=sum(c.get('valid_output') is True for c in group)
        for c in group:c.update(actual_models=len(group),valid_models=valid,valid_fraction=valid/len(group))
    refine_effects=[]
    for (selection,di),chosen in final.items():
        if selection!='refine':continue
        baseline=final.get(('main',di),{})
        a=models.get(baseline.get('id'),{});b=models.get(chosen['id'],{})
        av=a.get('ranking_score');bv=b.get('ranking_score')
        gain=bv-av if isinstance(av,(int,float)) and isinstance(bv,(int,float)) else None
        refine_effects.append({'design_index':di,'baseline_id':a.get('id'),'best_id':b.get('id'),'best_round':b.get('round'),'score_gain':gain,'outcome':'最终仍选 baseline' if b.get('round')==0 else '选择精修路径'})
    round_outcomes=[]
    for (stage,key),receipt in receipts.items():
        if stage!='refine_round':continue
        di,rnd=map(int,re.findall(r'\d+',key));r=receipt['data'];selected=r.get('selected',[])
        ids=[f'refine:D{di}:C{rnd}:P{pi}:K{k}:S{si}:M{mi}' for pi,k,si,mi in selected]
        missing=[mid for mid in ids if not assessed(mid)]
        if missing:issues.append({'level':'warning','code':'ROUND_SELECTION_EVIDENCE_MISSING','message':key+' 缺少当前工件对应评估：'+', '.join(missing)})
        ids=[mid for mid in ids if assessed(mid)]
        baseline=models.get(final.get(('main',di),{}).get('id'),{}).get('ranking_score')
        representative=models.get(ids[0],{}) if ids else {}
        score=representative.get('ranking_score')
        note='保留评估证据缺失' if missing else ('没有有效新输出' if r.get('status')=='no_valid_new_output' else ('本轮代表低于 baseline' if isinstance(score,(int,float)) and isinstance(baseline,(int,float)) and score<baseline else '已保留本轮路径'))
        round_outcomes.append({'design_index':di,'round':rnd,'representative_id':representative.get('id'),'retained_ids':ids,'n_candidates':r.get('n_candidates'),'outcome':note})
    cfg=run.get('config',{})
    counts={'planned_backbones':cfg.get('total_designs',cfg.get('n_batches',0)*cfg.get('diffusion_batch_size',1)),
        'planned_main_pairs':cfg.get('main_pair_limit'), 'planned_refine_pairs':cfg.get('refine_pair_limit'),
        'rfd3_generated':sum((e['data'].get('n_generated') or 0) for (s,k),e in jobs.items() if s=='main_rfd3'),
        'mpnn_sequences':sum((e['data'].get('n_generated') or 0) for (s,k),e in jobs.items() if s=='main_mpnn'),
        'rf3_pairs':len(pairs),'rf3_models':len(candidates),'valid_models':sum(c.get('valid_output') is True for c in candidates),
        'invalid_models':sum(c.get('valid_output') is False for c in candidates),
        'valid_pairs':len({c['pair_id'] for c in candidates if c.get('valid_output') is True}),
        'attempt_scope':'CURRENT_ATTEMPT','new_jobs':len(new),'reused_jobs':len(reuses),'reconstructed_jobs':len(set(jobs)-new-reuses),
        'rounds_completed':sum(s=='refine_round' for s,k in jobs)}
    stages=[]
    for stage in ('main_rfd3','main_mpnn','main_rf3','refine_rfd3','refine_mpnn','refine_rf3','refine_round','export'):
        sj=[e for (s,k),e in jobs.items() if s==stage]
        considered={e.get('key') for e in events if e.get('stage')==stage and e.get('event') in ('START','INVALID','COMMITTED','REUSED') and e.get('key')}
        stages.append({'stage':stage,'status':stage_end.get(stage,stage_end.get('refine','OBSERVED' if sj else 'NOT_STARTED') if stage.startswith('refine') else ('OBSERVED' if sj else 'NOT_STARTED')),
            'requested':sum(e['data'].get('n_requested',e['data'].get('n_requested_models',0)) or 0 for e in sj), 'actual':len(considered|{k for s,k in jobs if s==stage}),
            'requested_unit':stage_unit(stage),'work_item_unit':'工作项',
            'submitted_work_items':len(sj),'returned_units':sum(returned_units(stage,e['data']) for e in sj),'attempt_scope':'CURRENT_ATTEMPT',
            'completed':len(sj),'new':sum(s==stage for s,k in new),'reused':sum(s==stage for s,k in reuses),
            'invalid':len({e.get('key') for e in events if e.get('stage')==stage and e.get('event')=='INVALID'}),
            'duration_scope':'CURRENT_ATTEMPT_NEW_INFERENCE','duration_s':duration[stage] if stage in duration else None})
    if any(i['code'] in ('CHECKPOINT_REJECTED','CHECKPOINT_UNREADABLE') for i in issues):
        run=dict(run,status='EVIDENCE_INCOMPLETE')
    if mode=='report' and run.get('status')=='RUNNING':
        run=dict(run,status='INCOMPLETE');issues.append({'level':'warning','code':'INCOMPLETE','message':'未收到最终完成状态；这是部分结果快照。'})
    progress=sorted([e['ts'] for e in events if e.get('event') in ('COMMITTED','MODEL','PAIR')]+[r['ts'] for r in receipts.values()])
    collector=read_json(state_dir(root)/'collector.json',{})
    attempt_timeline=[{k:e.get(k) for k in ('attempt_id','ts','event','stage','key')}|{'status':(e.get('data') or {}).get('status')} for e in events if (e.get('event')=='END' or e.get('event')=='START' and e.get('stage')=='session') and isinstance(e.get('data') or {},dict)]
    return {'schema':'sr56-report-v1','mode':mode,'synthetic':run.get('synthetic',False),'generated_at':now(),
        'source_cutoff':max([run['created_at']]+[e['ts'] for e in events]+progress+[r['ts'] for r in resources if r.get('ts')]+([collector['ts']] if collector.get('ts') else [])),'run':run,'counts':counts,'stages':stages,
        'events':events,'attempt_timeline':attempt_timeline,'resources':resources,'candidates':candidates,'refine_effects':refine_effects,'round_outcomes':round_outcomes,'lineage':list(lineage.values()),'issues':issues,
        'artifacts':[],'downloads':[],'branches':[],'checkpoint_hashes':checkpoint_hashes,'integrity':{'status':'SOURCE_SNAPSHOT','scope':'完成数来自身份与工件散列核验后的断点；有效性来自已提交评估'},
        'progress_at':progress[-1] if progress else None,'artifact_at':progress[-1] if progress else None,
        'collector_at':collector.get('ts')}

def _copy_assets(destination):
    required=('report.html','report.css','report.js','3Dmol-min.js','SR56_Serif_CJK.ttf','SR56_Sans_CJK.ttf')
    if any(not (ASSETS/name).is_file() for name in required):raise ValueError('Trusted SR56 report resources are missing')
    dst=Path(destination)/'assets';dst.mkdir(parents=True,exist_ok=True)
    for p in ASSETS.iterdir():
        if p.is_file() and (p.name in ('3Dmol-min.js','3Dmol-min.js.LICENSE.txt','LICENSE_DEJAVU') or p.suffix.lower() in ('.ttf','.txt','.json')):
            target=dst/p.name
            if not target.exists() or target.stat().st_size!=p.stat().st_size or digest(target)!=digest(p):shutil.copy2(p,target)

def page(data,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True);_copy_assets(destination)
    payload={k:v for k,v in data.items() if k not in ('candidates','artifacts','checkpoint_hashes','events')};candidates=data.get('candidates',[])
    payload['candidates']=[]
    if data.get('mode')!='monitor':
        payload['candidates_script']=('reports/' if data.get('layout_version')==2 else '')+'data/candidates.js'
        atomic(destination/'data/candidates.js','window.SR56_CANDIDATES='+dumps(candidates).replace('<','\\u003c')+';\n')
        payload['artifacts_script']=('reports/' if data.get('layout_version')==2 else '')+'data/artifacts.js'
        atomic(destination/'data/artifacts.js','window.SR56_ARTIFACTS='+dumps(data.get('artifacts',[])).replace('<','\\u003c')+';\n')
    payload['events']=[{**e,'data':{k:v for k,v in (e.get('data') or {}).items() if k in ('status','message','errors','n_generated','n_requested','seed','n_generated_models','n_requested_models')}} for e in data.get('events',[])[-150:] if e.get('event') not in ('MODEL','PAIR') and isinstance(e.get('data') or {},dict)]
    template=(ASSETS/'report.html').read_text(encoding='utf-8')
    generic=data.get('run',{}).get('branch')=='template_project' or any(b.get('branch')=='template_project' for b in data.get('branches',[]))
    if generic:
        complete_template=(data.get('run',{}).get('namespace')=='design_template_pipeline_v2'
                           or any(b.get('identity',{}).get('namespace')=='design_template_pipeline_v2' for b in data.get('branches',[])))
        for old,new in [('SR56 ·','Design ·'),('SR56 —','Design —'),('SR56 报告','Design 报告'),('SR56 研究','Design 研究'),('>SR56<','>Design<'),('NESPRIN · SPECTRIN REPEAT 56','PROTEIN DESIGN · UNCONFIGURED TEMPLATE')]:
            template=template.replace(old,new)
        if complete_template:template=template.replace('UNCONFIGURED TEMPLATE','BINDER PIPELINE TEMPLATE')
    css=(ASSETS/'report.css').read_text(encoding='utf-8');js=(ASSETS/'af3_names.js').read_text(encoding='utf-8')+'\n'+(ASSETS/'report.js').read_text(encoding='utf-8')
    if generic:js=js.replace('SR56 — SIX BRANCH ATLAS','DESIGN — PROJECT ATLAS').replace('SR56 — RUN ARCHIVE','DESIGN — RUN ARCHIVE')
    if data.get('layout_version')==2:
        js=js.replace("? value : '';", "? '../'+value : '';",1)
    result=template.replace('__SR56_CSS__',css).replace('__SR56_JS__',js).replace('__SR56_DATA__',dumps(payload).replace('<','\\u003c'))
    atomic(destination/'index.html',result)
    return destination/'index.html'

def selected_pairs(data):
    candidates=data['candidates'];main=[c for c in candidates if not c.get('round') and c.get('valid_output')]
    best={}
    for c in main:
        di=c.get('design_index')
        if di not in best:best[di]=c
    ranked=sorted(best.values(),key=lambda c:(c.get('formal_rank') is None,c.get('formal_rank',0),stable_key(c)))
    designs={c['design_index'] for c in ranked[:10]}
    ids={c['id'] for c in ranked[:10]}
    ids.update(x['child_id'] for x in data['lineage'] if x.get('selected') and x.get('design_index') in designs)
    ids.update(x.get('parent_id') for x in data['lineage'] if x.get('selected') and x.get('design_index') in designs)
    ids.update(c['id'] for c in candidates if c.get('final_selected') and c.get('design_index') in designs)
    return {c['pair_id'] for c in candidates if c['id'] in ids}

_AA=dict(zip('ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split(),'ARNDCQEGHILKMFPSTWYV'))
def structure_projection(text,candidate,run,confidence=None,stage='rf3'):
    """Resolve each coordinate view from atom_site and exact known sequences only."""
    lines=text.splitlines();atoms=[]
    for i,line in enumerate(lines):
        if line.strip()!='loop_':continue
        j=i+1;headers=[]
        while j<len(lines) and lines[j].startswith('_'):
            headers.append(lines[j].strip());j+=1
        if not headers or not all(h.startswith('_atom_site.') for h in headers):continue
        for line in lines[j:]:
            if not line.strip() or line.startswith(('#','loop_','_')):break
            row=shlex.split(line)
            if len(row)!=len(headers):continue
            atoms.append(dict(zip([h.split('.',1)[1] for h in headers],row)))
    chains=defaultdict(list)
    for a in atoms:
        if a.get('label_atom_id')=='CA':chains[a.get('auth_asym_id',a.get('label_asym_id'))].append(a)
    seqs={k:''.join(_AA.get(a.get('label_comp_id'),'X') for a in aa) for k,aa in chains.items()}
    target=run.get('target',{}).get('sequence');binder=candidate.get('sequence')
    targets=[k for k,v in seqs.items() if v==target];binders=[k for k,v in seqs.items() if v==binder]
    if stage=='generated' and len(targets)==1:binders=[k for k in chains if k!=targets[0]]
    result={'target_chain':targets[0] if len(targets)==1 else None,'binder_chain':binders[0] if len(binders)==1 else None,'confidence_verified':False,'binder_ca_plddt':None}
    values=(confidence or {}).get('confidences',{}).get('atom_plddts',[])
    if isinstance(values,list) and len(values)==1 and isinstance(values[0],list):values=values[0]
    try:
        bs=[float(a['B_iso_or_equiv']) for a in atoms]
        ids=(confidence or {}).get('confidences',{}).get('atom_chain_ids',[])
        correspondence=defaultdict(set);reverse=defaultdict(set)
        if len(ids)==len(atoms):
            for identifier,a in zip(ids,atoms):
                chain=a.get('auth_asym_id',a.get('label_asym_id'));correspondence[str(identifier)].add(chain);reverse[chain].add(str(identifier))
        chain_ok=len(ids)==len(atoms) and all(len(v)==1 for v in correspondence.values()) and all(len(v)==1 for v in reverse.values())
        valid=chain_ok and len(values)==len(bs) and len(bs)>0 and all(0<=b<=1 and abs(float(v)-b)<=.00501 for v,b in zip(values,bs))
        if valid and result['binder_chain'] and result['target_chain']!=result['binder_chain']:
            ca=[float(a['B_iso_or_equiv'])*100 for a in chains[result['binder_chain']]]
            result.update(confidence_verified=True,binder_ca_plddt=sum(ca)/len(ca))
    except (KeyError,TypeError,ValueError):pass
    return result

def model_projection(candidate,text,run,confidence=None):
    return {**{k:candidate.get(k) for k in ('ranking_score','iptm','ptm','overall_plddt','has_clash','metrics')},'view':structure_projection(text,candidate,run,confidence)}

def _source_files(root):
    # Evidence only; generated pages and shared resources are never recopied.
    allowed={'state','monitor','checkpoints','reports','prep','target_fragment','main','refine','rankings','svg',
             'main_rfd3','main_mpnn','main_rf3','refine_rfd3','refine_mpnn','refine_rf3'}
    for p in Path(root).rglob('*'):
        rel=p.relative_to(root)
        if rel.parts[0] not in allowed and not rel.parts[0].startswith('outputs_'):continue
        if rel.parts[0] in ('state','monitor') and (p.name=='index.html' or any(part in ('assets','data') for part in rel.parts)):continue
        if any(part in ('feedback','live','input_sources','__pycache__','assets','data','preview','resources','weights','cache') for part in rel.parts):continue
        if rel.parts[0]=='reports' and (len(rel.parts)<2 or rel.parts[1] not in ('main','refine','rankings','svg')):continue
        if safe_inside(root,p) is None or safe_data_path(rel.as_posix()) is None:continue
        if p.suffix.lower() not in DATA_SUFFIXES|{'.svg'}:continue
        if p.name.startswith('kernel-') or p.name.endswith(('.tmp','.partial')):continue
        yield p


def write_readme(root):
    atomic(Path(root)/'README.html','<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Design feedback</title><a href="reports/index.html">打开反馈报告</a></html>\n')

def assemble(root,destination,mode='report',structures=True):
    if mode=='monitor':
        data=collect_monitor(root);page(data,destination);return data
    root=Path(root).resolve();dest=Path(destination).resolve();dest.mkdir(parents=True,exist_ok=True)
    data=collect(root,mode);data['layout_version']=LAYOUT_VERSION;keep=selected_pairs(data) if structures else set()
    selected_paths=set();candidate_paths={};pair_groups=defaultdict(list)
    for c in data['candidates']:
        pair_groups[c['pair_id']].append(c)
        paths={}
        for label,aliases in {'generated':('generated','generated_path','backbone_file'),
            'mpnn':('mpnn','mpnn_path','seq_file'),'rf3':('cif','rf3','model_cif'),'conf':('conf',)}.items():
            value=next((c[k] for k in aliases if c.get(k)),None)
            p=safe_inside(root,value)
            if p and safe_data_path(relative(root,p)):
                paths[label]=p
                if c['pair_id'] in keep or label=='conf':selected_paths.add(p)
        candidate_paths[c['id']]=paths
    # Preserve selected model sources and all numeric evidence; use source-relative paths.
    artifact_by_path={}
    for p in _source_files(root):
        rel=relative(root,p);structure=p.suffix.lower() in ('.cif','.pdb')
        include=(not structure) or p in selected_paths or rel.startswith(('target_fragment/','prep/'))
        if mode=='monitor':include=False
        row={'id':rel,'path':rel,'bytes':p.stat().st_size,'sha256':data.get('checkpoint_hashes',{}).get(str(p)),'included':include,
             'reason':None if include else '远程原件，未随包携带'}
        if include:
            before=p.stat();target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True)
            copy_evidence(p,target);row['sha256']=digest(target);row['download']=rel
            expected=data.get('checkpoint_hashes',{}).get(str(p))
            if expected and row['sha256']!=expected:
                data['issues'].append({'level':'warning','code':'CHANGED_AFTER_COLLECTION','message':f'{rel} 在计数核验后变化；该包是部分快照。'})
                data['run']['status']='INCOMPLETE'
            after=p.stat()
            if (before.st_mtime_ns,before.st_size)!=(after.st_mtime_ns,after.st_size):
                data['issues'].append({'level':'warning','code':'CHANGED_DURING_SNAPSHOT','message':f'{rel} 在导出期间变化；该包是部分快照。'})
                data['run']['status']='INCOMPLETE'
        artifact_by_path[str(p)]=row;data['artifacts'].append(row)
    data['checkpoint_hashes']={relative(root,Path(path)):sha for path,sha in data['checkpoint_hashes'].items()}
    for pair,group in pair_groups.items():
        has=pair in keep;payload={'models':[],'target_chain':data['run'].get('target',{}).get('chain','A')}
        first=group[0];p0=candidate_paths[first['id']]
        for k in ('generated','mpnn','rf3'):
            artifact=artifact_by_path.get(str(p0.get(k)),{})
            payload[k]=(dest/artifact['download']).read_text(encoding='utf-8') if has and artifact.get('included') else None
        payload['views']={k:structure_projection(payload[k],first,data['run'],stage=k) for k in ('generated','mpnn') if payload.get(k)}
        payload['contact_residue_ids']=first.get('metrics',{}).get('contact_residue_ids',[])
        pair_hash=hashlib.sha256(pair.encode()).hexdigest()[:20];script='reports/data/structures/'+pair_hash+'.js'
        for c in group:
            paths=candidate_paths[c['id']];links={}
            for k,p in paths.items():
                a=artifact_by_path.get(str(p),{})
                if a.get('included'):links[k]=a.get('download')
            if has and 'rf3' in links:c.update(model_projection(c,(dest/links['rf3']).read_text(encoding='utf-8'),data['run'],read_json(dest/links['conf'],{}) if 'conf' in links else {}))
            c['structure']={'key':pair,'included':has and 'rf3' in links,'script':script if has else None,
                **links,'reason':None if has and 'rf3' in links else '结构未随包携带或源文件缺失，可导出补取清单'}
            if has and 'rf3' in links:payload['models'].append({'mi':c.get('model_index'),'id':c['id'],'valid_output':c.get('valid_output'),'errors':c.get('errors',[]),'ranking_score':c.get('ranking_score'),'cif':(dest/links['rf3']).read_text(encoding='utf-8'),'downloads':links,**model_projection(c,(dest/links['rf3']).read_text(encoding='utf-8'),data['run'],read_json(dest/links['conf'],{}) if 'conf' in links else {}),'contact_residue_ids':c.get('metrics',{}).get('contact_residue_ids',[])})
            for k in ('generated','generated_path','backbone_file','mpnn','mpnn_path','seq_file','cif','rf3','model_cif','conf'):
                c.pop(k,None)
        if has:
            atomic(dest/script,'window.SR56_STRUCTURES=window.SR56_STRUCTURES||{};window.SR56_STRUCTURES['+dumps(pair)+']='+dumps(payload).replace('<','\\u003c')+';\n')
    if mode=='monitor':
        # Monitor is a lightweight status page: no artifact copies or coordinate payloads.
        data['events']=data['events'][-150:];data['resources']=data['resources'][-240:]
    else:
        data['downloads']=[{'label':'机器可读报告 JSON','path':'reports/report.json'},{'label':'反馈摘要 Markdown','path':'reports/summary.md'},
                           {'label':'全部工件索引','path':'reports/artifact_index.json'}]
        write_json(dest/'reports/artifact_index.json',data['artifacts'])
        write_json(dest/'reports/missing_structure_request.json',{'schema':'sr56-missing-request-v1','run_id':data['run']['run_id'],
            'notebook_sha256':data['run'].get('notebook_sha256'),'source_cutoff':data['source_cutoff'],
            'candidates':[{'id':c['id'],'pair_id':c['pair_id'],'structure':c.get('structure')} for c in data['candidates'] if not c.get('structure',{}).get('included')],
            'artifacts':[a for a in data['artifacts'] if not a['included']]})
        data['downloads'].append({'label':'全部缺失结构补取清单 JSON','path':'reports/missing_structure_request.json'})
        write_report_data(data,dest)
        counts=data['counts'];run=data['run']
        summary_label='Design' if run.get('namespace')=='design_template_pipeline_v2' else 'SR56'
        atomic(dest/'reports/summary.md',f"# {summary_label} {run['branch']} 反馈摘要\n\n运行：{run['run_id']}\n\n状态：{run['status']}\n\n截至：{data['source_cutoff']}\n\nRF3序列对：{counts['rf3_pairs']}；模型：{counts['rf3_models']}；有效模型：{counts['valid_models']}。\n\n结构：全量数据与精选结构；其余见 artifact_index.json。\n\n"+'\n'.join(f"- D{x['design_index']}: {x['outcome']}; score gain {x['score_gain']}" for x in data.get('refine_effects',[]))+'\n\n'+'\n'.join('- '+x['code']+': '+x['message'] for x in data['issues'])+'\n')
    page(data,dest/'reports');write_readme(dest)
    return data

def publish_generated_views(snapshot,root,data,terminal_monitor=False):
    """Reuse one snapshot's generated files; never copy its original evidence back."""
    root=Path(root).resolve();generated=Path(snapshot)/'reports';reports=root/'reports'
    names=('index.html','assets','data','report.json','artifact_index.json','summary.md','missing_structure_request.json')
    assert_write_path(root,reports)
    for name in names:assert_write_tree(root,reports/name)
    monitor=state_dir(root)
    if terminal_monitor:
        assert_write_path(root,monitor)
        for name in ('assets','index.html'):assert_write_tree(root,monitor/name)
    for name in names:
        source=generated/name
        files=sorted(p for p in source.rglob('*') if p.is_file()) if source.is_dir() else [source]
        for file in files:
            target=assert_write_path(root,reports/file.relative_to(generated))
            atomic(target,file.read_bytes())
    if terminal_monitor:
        view=dict(data,mode='monitor',candidates=[],artifacts=[],events=data.get('events',[])[-150:],resources=data.get('resources',[])[-240:])
        page(view,monitor)


def render_report(root,destination=None,mode='report',structures=True):
    root=Path(root).resolve()
    if mode=='monitor':
        destination=Path(destination) if destination else state_dir(root)
        if destination.absolute().is_relative_to(root):
            assert_write_path(root,destination)
            for name in ('assets','index.html'):assert_write_tree(root,destination/name)
        return assemble(root,destination,mode,structures)
    if destination is not None:return assemble(root,Path(destination),mode,structures)
    # Publish generated outputs from a private snapshot, preserving original evidence.
    with tempfile.TemporaryDirectory(prefix='.render_') as temp:
        snapshot=Path(temp)/'snapshot';data=assemble(root,snapshot,mode,structures)
        publish_generated_views(snapshot,root,data)
    return data

def export_feedback(root,output=None):
    root=Path(root).resolve();base=assert_write_path(root,root/'feedback');base.mkdir(exist_ok=True)
    run=read_json(state_dir(root)/'session.json',{});branch=run.get('branch','unknown');run_id=run.get('run_id','unknown')
    if branch not in BRANCHES or not isinstance(run_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',run_id):raise ValueError('Unsafe export identity')
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d_%H%M%S')
    desired=Path(output).absolute() if output else base/('feedback_'+stamp+'.zip')
    if desired.is_relative_to(root):assert_write_path(root,desired.parent)
    else:desired=desired.parent.resolve()/desired.name
    desired.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive claim prevents sequential/process collisions; publish only verified ZIP bytes.
    number=1
    while True:
        final=desired if number==1 else desired.with_name(desired.stem+f'_{number:02d}'+desired.suffix)
        claim=final.with_name(final.name+'.lock')
        assert_write_path(root if final.is_relative_to(root) else final.parent,claim)
        try:fd=os.open(claim,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        except FileExistsError:
            if output:raise FileExistsError('Feedback output is already reserved: '+str(final))
            number+=1;continue
        os.close(fd)
        if final.exists() or final.is_symlink() or final.with_suffix(final.suffix+'.sha256').exists() or final.with_suffix(final.suffix+'.sha256').is_symlink():
            claim.unlink()
            if output:raise FileExistsError('Feedback output already exists: '+str(final))
            number+=1;continue
        break
    partial=assert_write_path(root if final.is_relative_to(root) else final.parent,final.with_name(final.name+'.'+uuid.uuid4().hex+'.partial'))
    try:
        with tempfile.TemporaryDirectory(prefix='.export_',dir=base) as temp:
            stage=Path(temp)/'snapshot';data=assemble(root,stage)
            files=[{'path':p.relative_to(stage).as_posix(),'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted(stage.rglob('*')) if p.is_file()]
            manifest={'schema':BUNDLE_SCHEMA,'layout_version':LAYOUT_VERSION,'report_entry':'reports/report.json',
                'run_id':run_id,'branch':branch,'config_sha256':run.get('config_sha256'),
                'notebook_sha256':run.get('notebook_sha256'),'namespace':run.get('namespace'),'target':run.get('target'),
                'snapshot_at':now(),'source_cutoff':data['source_cutoff'],'package_complete':True,
                'computation_status':data['run']['status'],'files':files,'synthetic':data['synthetic']}
            write_json(stage/'MANIFEST.json',manifest)
            atomic(stage/'SHA256SUMS.txt',''.join(e['sha256']+'  '+e['path']+'\n' for e in files)+digest(stage/'MANIFEST.json')+'  MANIFEST.json\n')
            with zipfile.ZipFile(partial,'w',compression=zipfile.ZIP_DEFLATED,allowZip64=True) as z:
                for p in sorted(stage.rglob('*')):
                    if p.is_file():z.write(p,p.relative_to(stage).as_posix())
            verify_bundle(partial)
            publish_generated_views(stage,root,data,terminal_monitor=True)
            assert_write_path(root if final.is_relative_to(root) else final.parent,final)
            # Hard-link publication has no overwrite window even for a non-cooperating writer.
            os.link(partial,final);partial.unlink()
        # ZIP and sidecar each publish atomically; they are not a two-file transaction.
        assert_write_path(root if final.is_relative_to(root) else final.parent,final.with_suffix(final.suffix+'.sha256'))
        atomic(final.with_suffix(final.suffix+'.sha256'),digest(final)+'  '+final.name+'\n',overwrite=False)
        return final
    finally:
        if partial.exists():partial.unlink()
        claim.unlink()

def _safe_member(info):
    name=info.filename;p=PurePosixPath(name)
    if not name or '\\' in name or p.is_absolute() or '..' in p.parts or ':' in name or any(ord(c)<32 for c in name) or any(part.endswith((' ','.')) for part in p.parts):raise ValueError('Unsafe ZIP path: '+name)
    if stat.S_ISLNK(info.external_attr>>16):raise ValueError('ZIP symlink rejected: '+name)
    if name!=str(p):raise ValueError('Noncanonical ZIP path: '+name)
    if info.file_size>2*1024**3:raise ValueError('Unexpected >2GiB feedback member: '+name)

def verify_bundle(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=len({unicodedata.normalize('NFC',n).casefold() for n in names}):raise ValueError('Duplicate ZIP paths')
        if len(names)>500000 or sum(i.file_size for i in z.infolist())>20*1024**3:raise ValueError('Feedback archive exceeds safety limits')
        for info in z.infolist():_safe_member(info)
        manifest_raw=_zip_metadata(z,'MANIFEST.json');manifest=json.loads(manifest_raw)
        schema=manifest.get('schema')
        if schema==BUNDLE_SCHEMA:
            if manifest.get('layout_version')!=2 or manifest.get('report_entry')!='reports/report.json':raise ValueError('Unsupported feedback layout')
            report_entry='reports/report.json'
        elif schema==SCHEMA:
            if manifest.get('layout_version',1)!=1 or manifest.get('report_entry','report.json')!='report.json':raise ValueError('Unsupported legacy feedback layout')
            report_entry='report.json'
        else:raise ValueError('Unsupported feedback schema')
        if manifest.get('branch') not in BRANCHES or manifest.get('package_complete') is not True:raise ValueError('Unsupported or incomplete feedback manifest')
        if not isinstance(manifest.get('run_id'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',manifest['run_id']):raise ValueError('Unsafe run ID')
        declared=[e['path'] for e in manifest['files']]
        if len(declared)!=len(set(declared)) or set(names)!=set(declared)|{'MANIFEST.json','SHA256SUMS.txt'}:raise ValueError('ZIP members differ from manifest')
        for entry in manifest['files']:
            h=hashlib.sha256();size=0
            with z.open(entry['path']) as f:
                for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk);size+=len(chunk)
            if (size,h.hexdigest())!=(entry['bytes'],entry['sha256']):raise ValueError('Corrupt member: '+entry['path'])
        report=json.loads(_zip_metadata(z,report_entry));run=report['run']
        if report.get('layout_version',1)!=(2 if schema==BUNDLE_SCHEMA else 1):raise ValueError('Report layout differs from manifest')
        for key in ('run_id','branch','config_sha256','notebook_sha256','namespace','target'):
            if run.get(key)!=manifest.get(key):raise ValueError('Report identity differs: '+key)
        if report['source_cutoff']!=manifest['source_cutoff'] or run['status']!=manifest['computation_status']:raise ValueError('Report state differs from manifest')
        sums=_zip_metadata(z,'SHA256SUMS.txt').decode().splitlines()
        expected=[e['sha256']+'  '+e['path'] for e in manifest['files']]+[hashlib.sha256(manifest_raw).hexdigest()+'  MANIFEST.json']
        if sums!=expected:raise ValueError('SHA256SUMS mismatch')
        return manifest

def _registry_payload(path, expected_key):
    """Read the historical fixed assignment as JSON, never evaluate JavaScript."""
    path=Path(path);limit=128*1024**2
    if path.stat().st_size>limit:raise ValueError('Structure registry exceeds safety limit')
    with path.open('rb') as stream:raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('Structure registry exceeds safety limit')
    text=raw.decode('utf-8');prefix='window.SR56_STRUCTURES=window.SR56_STRUCTURES||{};window.SR56_STRUCTURES['
    if not text.startswith(prefix):raise ValueError('Untrusted structure registry syntax')
    decoder=json.JSONDecoder();key,end=decoder.raw_decode(text,len(prefix))
    if key!=expected_key or not text[end:].startswith(']='):raise ValueError('Structure registry key differs')
    payload,end=decoder.raw_decode(text,end+2)
    if text[end:].strip()!=';' or not isinstance(payload,dict):raise ValueError('Untrusted structure registry syntax')
    return payload

def rebuild_verified_view(source,destination):
    """Publish only passive evidence and trusted generated code from a verified tree.

    The caller verifies member hashes. Imported HTML, CSS, JS and SVG never enter
    destination. Frozen scientific counts/events are retained without recollection.
    """
    source=Path(source);destination=Path(destination)
    if destination.exists() and any(destination.iterdir()):raise ValueError('Publication directory must be empty')
    destination.mkdir(parents=True,exist_ok=True)
    data=load_report_data(source);data=sanitize_messages(json.loads(dumps(data)))
    copied=set();canonical_targets={};legacy=data.get('layout_version',1)==1
    data['layout_version']=LAYOUT_VERSION
    def canonical(value):
        ref=safe_data_path(value)
        if ref is None:return None
        return ref.removeprefix('data/source/') if legacy else ref
    metadata={'summary.md','run_snapshot.json','missing_files.json','reports/summary.md'}
    for path in sorted(source.rglob('*')):
        if safe_inside(source,path) is None:continue
        rel=path.relative_to(source).as_posix()
        if is_data_member(rel) and (rel.startswith(('data/source/','logs/','main/','refine/','state/','monitor/','checkpoints/','prep/','target_fragment/','main_rfd3/','main_mpnn/','main_rf3/','refine_rfd3/','refine_mpnn/','refine_rf3/','outputs_','rankings/','svg/','reports/main/','reports/refine/','reports/rankings/','reports/svg/')) or rel in metadata):
            if path.suffix.lower()=='.json' and path.stat().st_size>METADATA_LIMITS['report.json']:raise ValueError('Evidence JSON exceeds safety limit')
            output_rel=canonical(rel)
            if rel in metadata and not output_rel.startswith('reports/'):output_rel='reports/'+output_rel
            normalized=unicodedata.normalize('NFC',output_rel).casefold()
            if normalized in canonical_targets:raise ValueError('Canonical evidence path collision: '+canonical_targets[normalized]+' / '+rel)
            canonical_targets[normalized]=rel
            target=destination/output_rel;target.parent.mkdir(parents=True,exist_ok=True);copy_evidence(path,target);copied.add(output_rel)
    artifacts=[]
    for original in data.get('artifacts',[]):
        row=dict(original);rel=canonical(row.get('path'));requested=canonical(row.get('download'))
        row['path']=rel;row['id']=rel
        download=rel if rel in copied else requested if requested in copied else None
        row.pop('download',None);row['included']=download is not None
        if download:
            row['download']=download;row['bytes']=(destination/download).stat().st_size;row['sha256']=digest(destination/download)
        elif original.get('included'):row['reason']='Imported active or unavailable artifact omitted; original ZIP retained'
        artifacts.append(row)
    data['artifacts']=artifacts
    groups=defaultdict(list)
    aliases=('generated','generated_path','backbone_file','mpnn','mpnn_path','seq_file','cif','rf3','model_cif','conf','download','downloads','script','candidates_script')
    for candidate in data.get('candidates',[]):
        old=candidate.get('structure') or {};candidate['_import_structure']=old
        pair=str(candidate.get('pair_id') or old.get('key') or candidate['id']);groups[pair].append(candidate)
        for alias in aliases:candidate.pop(alias,None)
    for pair,candidates in groups.items():
        registry=None;payload={'models':[],'target_chain':data['run'].get('target',{}).get('chain','A')}
        for candidate in candidates:
            old=candidate.pop('_import_structure');links={}
            for label in ('generated','mpnn','rf3','conf'):
                ref=canonical(old.get(label))
                if ref in copied and (label=='conf' or Path(ref).suffix.lower() in ('.pdb','.cif')):links[label]=ref
            # Some old snapshots only embedded coordinate strings in their registry.
            # Parse exactly the known single assignment; regenerate it with safe JSON.
            script=safe_data_path(old.get('script'))
            if registry is None and script and script.startswith(('data/structures/','reports/data/structures/')) and script.endswith('.js') and safe_inside(source,script) is not None:
                registry=_registry_payload(source/script,pair)
            old_models=registry.get('models',[]) if registry else []
            old_model=next((m for m in old_models if isinstance(m,dict) and m.get('id')==candidate['id']),{})
            text=bounded_coordinates(destination/links['rf3']) if 'rf3' in links else old_model.get('cif')
            if text is None and registry and len(candidates)==1:text=registry.get('rf3')
            if text is not None and not isinstance(text,str):raise ValueError('Structure coordinates must be text')
            if text is not None and len(text.encode())>25*1024**2:raise ValueError('Structure coordinates exceed safety limit')
            if text:
                candidate.update(model_projection(candidate,text,data['run'],read_json(destination/links['conf'],{}) if 'conf' in links else {}))
                payload['models'].append({'mi':candidate.get('model_index'),'id':candidate['id'],
                    'valid_output':candidate.get('valid_output'),'errors':candidate.get('errors',[]),
                    'ranking_score':candidate.get('ranking_score'),'cif':text,'downloads':links,**model_projection(candidate,text,data['run'],read_json(destination/links['conf'],{}) if 'conf' in links else {}),
                    'contact_residue_ids':candidate.get('metrics',{}).get('contact_residue_ids',[])})
                payload.setdefault('rf3',text)
            for label in ('generated','mpnn'):
                coordinate=bounded_coordinates(destination/links[label]) if label in links else registry.get(label) if registry else None
                if coordinate is not None and (not isinstance(coordinate,str) or len(coordinate.encode())>25*1024**2):raise ValueError('Structure coordinates exceed safety limit')
                if coordinate:
                    payload.setdefault(label,coordinate);payload.setdefault('views',{})[label]=structure_projection(coordinate,candidate,data['run'],stage=label)
            generated='reports/data/structures/'+hashlib.sha256(pair.encode()).hexdigest()[:20]+'.js'
            candidate['structure']={'key':pair,'included':bool(text),'script':generated if text else None,**links,
                'reason':None if text else 'Structure omitted or unavailable; original ZIP retained'}
        if payload['models']:
            atomic(destination/generated,'window.SR56_STRUCTURES=window.SR56_STRUCTURES||{};window.SR56_STRUCTURES['+dumps(pair)+']='+dumps(payload).replace('<','\\u003c')+';\n')
    # Branch links and imported script aliases must not become extra active pages.
    data['branches']=[{k:v for k,v in b.items() if k!='path'} for b in data.get('branches',[])]
    data.pop('candidates_script',None)
    write_json(destination/'reports/artifact_index.json',artifacts)
    write_json(destination/'reports/missing_structure_request.json',{'schema':'sr56-missing-request-v1','run_id':data['run']['run_id'],
        'source_cutoff':data.get('source_cutoff'),'candidates':[c for c in data.get('candidates',[]) if not c['structure']['included']],
        'artifacts':[a for a in artifacts if not a['included']]})
    data['downloads']=[{'label':label,'path':path} for label,path in (
        ('机器可读报告 JSON','reports/report.json'),('反馈摘要 Markdown','reports/summary.md'),
        ('全部工件索引','reports/artifact_index.json'),('缺失结构补取清单','reports/missing_structure_request.json')) if path=='reports/report.json' or (destination/path).is_file()]
    write_report_data(data,destination);page(data,destination/'reports');write_readme(destination)
    return data

def merge_bundles(paths,output):
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    for name in ('runs','assets','data','index.html','merge_index.json'):
        assert_write_tree(out,out/name)
    index=read_json(out/'merge_index.json',{'schema':SCHEMA,'imports':[]})
    imports=index['imports']
    for item in imports:
        p=PurePosixPath(item['path'])
        if safe_data_path(item['path']) is None or not item['path'].startswith('runs/'):raise ValueError('Unsafe existing import index')
        assert_write_path(out,out/item['path'])
    seen={i['zip_sha256'] for i in imports}
    identities={i['run_id']:i['identity'] for i in imports}
    snapshots={(i['run_id'],i['snapshot_at']):i['zip_sha256'] for i in imports}
    # Validate every input before mutating the merged view.
    validated=[]
    for path in paths:
        path=Path(path);sha=digest(path)
        if sha in seen:continue
        m=verify_bundle(path);identity={k:m.get(k) for k in ('branch','config_sha256','notebook_sha256','namespace','target')}
        if m['run_id'] in identities and identities[m['run_id']]!=identity:raise ValueError('Conflicting identity for run '+m['run_id'])
        key=(m['run_id'],m['snapshot_at'])
        if key in snapshots and snapshots[key]!=sha:raise ValueError('Conflicting legacy snapshot contents')
        snapshots[key]=sha
        identities[m['run_id']]=identity;seen.add(sha);validated.append((path,sha,m,identity))
    # Rebuild every selected snapshot before publishing any of this batch.
    with tempfile.TemporaryDirectory(prefix='.import_',dir=out) as staging:
        assert_write_path(out,staging)
        publications=[];new_imports=[]
        for position,(path,sha,m,identity) in enumerate(validated):
            folder='runs/'+m['branch']+'_'+m['run_id'][:12]+'_'+sha[:12]
            dest=assert_write_path(out,out/folder)
            if dest.exists():raise ValueError('Unindexed publication already exists')
            temp=assert_write_path(out,Path(staging)/str(position));temp.mkdir();source=assert_write_path(out,temp/'source');source.mkdir()
            with zipfile.ZipFile(path) as z:z.extractall(source) # verified private staging, never published
            for item in m['files']:
                file=source/item['path']
                if file.stat().st_size!=item['bytes'] or digest(file)!=item['sha256']:raise ValueError('Extracted member changed')
            publication=assert_write_path(out,temp/'publication');rebuild_verified_view(source,publication)
            assert_write_path(out,publication/'original-feedback.zip')
            shutil.copy2(path,publication/'original-feedback.zip')
            if digest(path)!=sha or digest(publication/'original-feedback.zip')!=sha:raise ValueError('Source ZIP changed during import')
            publications.append((publication,dest))
            new_imports.append({'zip_sha256':sha,'run_id':m['run_id'],'branch':m['branch'],'identity':identity,'path':folder+'/reports/index.html',
                'snapshot_at':m['snapshot_at'],'source_cutoff':m['source_cutoff'],'status':m['computation_status'],'synthetic':m.get('synthetic',False)})
        published=[]
        try:
            for publication,dest in publications:
                assert_write_path(out,dest)
                dest.parent.mkdir(parents=True,exist_ok=True);os.replace(publication,dest);published.append(dest)
            imports.extend(new_imports);write_json(out/'merge_index.json',index)
        except BaseException:
            for dest in reversed(published):shutil.rmtree(dest)
            raise
    branches=[]
    for item in imports:
        snapshot=out/Path(item['path']).parent
        report=read_json(snapshot/'report.json',{})
        branches.append({**item,'counts':report.get('counts',{})})
    data={'schema':'sr56-report-v1','mode':'overview','synthetic':any(b['synthetic'] for b in branches),'generated_at':now(),
        'run':{'status':'IMPORTED','branch':'六分支总览','run_id':'local-collection'},'branches':branches,'counts':{},'candidates':[],
        'stages':[],'events':[],'resources':[],'lineage':[],'issues':[],'artifacts':[],
        'downloads':[{'label':'导入清单 JSON','path':'merge_index.json'}],'integrity':{'status':'VERIFIED','scope':'每个已导入ZIP的成员SHA-256与身份核验通过；计算状态独立显示'}}
    page(data,out);return out/'index.html'

def main():
    parser=argparse.ArgumentParser(description=__doc__);subs=parser.add_subparsers(dest='command',required=True)
    for name in ('export','render'):
        p=subs.add_parser(name);p.add_argument('root',type=Path);p.add_argument('--output',type=Path)
    p=subs.add_parser('verify');p.add_argument('zip',type=Path)
    p=subs.add_parser('merge');p.add_argument('zips',nargs='+',type=Path);p.add_argument('--output',type=Path,required=True)
    p=subs.add_parser('watch');p.add_argument('root',type=Path);p.add_argument('--attempt',required=True);p.add_argument('--pid',type=int,required=True)
    args=parser.parse_args()
    if args.command=='export':print(export_feedback(args.root,args.output))
    elif args.command=='render':render_report(args.root,args.output);print(args.output or args.root/'reports/index.html')
    elif args.command=='verify':print(dumps(verify_bundle(args.zip)))
    elif args.command=='merge':print(merge_bundles(args.zips,args.output))
    elif args.command=='watch':watch(args.root,args.attempt,args.pid)
if __name__=='__main__':main()
