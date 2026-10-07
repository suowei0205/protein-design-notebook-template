"""Actual kernels: blank full notebook + six example bootstraps; no science."""
from pathlib import Path
import json,shutil,sys,tempfile,zipfile
import nbformat
from nbclient import NotebookClient
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]

def execute():
 count=0
 with tempfile.TemporaryDirectory(prefix='design-kernel-') as td:
  tmp=Path(td).resolve()
  for package_name in ('template','examples/SR56'):
   source=ROOT/package_name;package=tmp/package_name.replace('/','_');shutil.copytree(source,package,ignore=shutil.ignore_patterns('.resources','run_*','.run_names.lock','__pycache__'))
   entries=json.loads((package/'manifest.json').read_text())['entries']
   for e in entries:
    p=package/e['filename'];n=nbformat.read(p,as_version=4)
    # Only the historical bootstrap prefix, never science/dependency cells.
    if package_name!='template':
     source=''.join(n.cells[3].source).split('# SR56_FEEDBACK_END')[0]+'\n'
     synthetic="_feedback.configure({'pipeline_status':'NOT_RUN'},{'input':'BOOTSTRAP_ONLY'},_feedback.run['namespace'],_feedback.root)\n_feedback.finish('NOT_RUN')\n_feedback.close()\n"
     n=nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(source),nbformat.v4.new_code_cell(synthetic)])
    guard="import sys\nassert not any(n=='torch' or n.startswith(('rfd3','rf3','mpnn')) for n in sys.modules), 'Scientific engine was imported'\n"
    n.cells[3 if package_name=='template' else 0].source+='\n'+guard
    n.cells[-1].source+='\n'+guard
    NotebookClient(n,timeout=90,kernel_name='python3').execute(cwd=str(p.parent))
    runs=list(p.parent.glob('run_*'));assert len(runs)==1
    root=runs[0];session=json.loads((root/'monitor/session.json').read_text());assert session['status']=='NOT_RUN'
    for name in ('reports/index.html','monitor/index.html','checkpoints/input/notebook.ipynb'):assert (root/name).is_file()
    archives=list((root/'feedback').glob('*.zip'));assert len(archives)==1
    with zipfile.ZipFile(archives[0]) as z:
     assert z.testzip() is None;manifest=json.loads(z.read('MANIFEST.json'));assert manifest['computation_status']=='NOT_RUN' and manifest['layout_version']==2
    count+=1;print('KERNEL PASS',e['branch'],'— bootstrap/feedback only, NOT_RUN',flush=True)
 assert count==7
 print('PASS 7 actual kernels; no scientific engines, weights, GPU or remote tasks.')
if __name__=='__main__':execute()
