"""Deterministic resource bundles and notebook pins. Stdlib; no model imports."""
from pathlib import Path
import argparse,ast,hashlib,io,json,zipfile
ROOT=Path(__file__).resolve().parents[1]
def encoded(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def digest(b):return hashlib.sha256(b).hexdigest()
def build(check=False):
 for package in [ROOT/'template',ROOT/'examples/SR56']:
  manifest=json.loads((package/'manifest.json').read_text())
  files={p.relative_to(ROOT/'runtime').as_posix():p.read_bytes() for p in sorted((ROOT/'runtime').rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
  for p in sorted((package/'inputs').rglob('*')):
   if p.is_file():files[p.relative_to(package).as_posix()]=p.read_bytes()
  files['NOTEBOOKS.json']=encoded(manifest)
  listing=lambda:[{'path':n,'bytes':len(b),'sha256':digest(b)} for n,b in sorted(files.items())]
  files['RUNTIME_FILES.json']=encoded({'schema':'sr56-runtime-files-v2','files':listing()})
  files['RESOURCE_MANIFEST.json']=encoded({'schema':'sr56-compact-resources-v1','files':listing()})
  stream=io.BytesIO()
  with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as z:
   for name,data in sorted(files.items()):
    info=zipfile.ZipInfo(name,date_time=(2026,10,7,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,data)
  raw=stream.getvalue();pin=digest(raw);archive=package/'resources.zip'
  if check:assert archive.read_bytes()==raw,('Stale bundle: run python scripts/build.py',package)
  else:archive.write_bytes(raw)
  for entry in manifest['entries']:
   p=package/entry['filename'];nb=json.loads(p.read_text());cell=nb['cells'][3];source=''.join(cell['source']);lines=source.splitlines(True)
   nodes=[n for n in ast.parse(source).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='RESOURCE_BUNDLE_SHA256' for t in n.targets)]
   assert len(nodes)==1
   if check:assert ast.literal_eval(nodes[0].value)==pin,('Stale notebook pin',p)
   else:
    n=nodes[0];lines[n.lineno-1:n.end_lineno]=['RESOURCE_BUNDLE_SHA256 = '+repr(pin)+'\n'];cell['source']=''.join(lines).splitlines(True);p.write_bytes(encoded(nb))
  print(('CHECKED' if check else 'BUILT'),package.relative_to(ROOT),pin)
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');build(parser.parse_args().check)
