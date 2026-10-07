"""Deterministic synthetic demo, local links and display-name boundaries; no science."""
from pathlib import Path
import hashlib, json, re, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_top10_demo import build, DEST, TARGET

def run():
    build(check=True)
    d=json.loads((DEST/'index.json').read_text());assert d['synthetic'] and d['counts']['actual_models']==80
    assert d['target']['sequence']==TARGET and len(d['main'])==len(d['best'])==10
    assert len(d['nodes'])==40 and len({n['pair_id'] for n in d['nodes']})==40
    meta=json.loads((DEST/'data/viewer.js').read_text().removeprefix('window.VIEWER_META=').strip().removesuffix(';'))
    models={m['id']:(n,m) for n in d['nodes'] for m in n['models']};assert len(models)==80
    for n in d['nodes']:
        assert 'SYNTHETIC' in n['pair_id'] and len(n['sequence'])==40
        for m in n['models']:
            assert m['synthetic'] and 'SYNTHETIC' in m['id']
            cif=(DEST/m['cif']).read_text();assert 'SYNTHETIC DEMO' in cif
            rows=[line.split() for line in cif.splitlines() if line.startswith('ATOM ')]
            conf=json.loads((DEST/m['conf']).read_text());assert conf['synthetic']
            assert len(rows)==len(conf['confidences']['atom_plddts'])==(len(TARGET)+len(n['sequence']))*4
            for atom,p,ch in zip(rows,conf['confidences']['atom_plddts'],conf['confidences']['atom_chain_ids']):
                assert atom[6]==ch and abs(float(atom[14])-p)<1e-8
            ca={r[15]:float(r[14])*100 for r in rows if r[17]=='B' and r[18]=='CA'}
            assert meta['models'][m['id']]['ca_plddt']==ca
        for key in ('generated','mpnn','script'):assert (DEST/n[key]).is_file()
    for row in d['main']:
        n,m=models[row['candidate_id']];assert n['baseline'] and m['round']==0
        assert meta['baselines'][str(row['design_index'])]==m['id']
    for row in d['best']:
        n,m=models[row['candidate_id']]
        eligible=[model for node in d['nodes'] if node['design_index']==row['design_index'] for model in node['models']]
        assert m['summary']['ranking_score']==max(x['summary']['ranking_score'] for x in eligible)
    manifest=json.loads((DEST/'GENERATED.json').read_text())
    for rel,sha in manifest['files'].items():assert hashlib.sha256((DEST/rel).read_bytes()).hexdigest()==sha
    for p in DEST.rglob('*'):
        assert not p.is_symlink()
        if p.is_file():assert not re.search(r'/Users/|/home/|/media/|[a-z]+://',p.read_text()),p
    html=(DEST/'index.html').read_text();assert 'SYNTHETIC DEMO' in html and 'af3_names.js' in html
    for rel in re.findall(r'(?:src|href)="([^"]+)"',html):assert (DEST/rel).is_file(),rel
    for file in ('runtime/assets/af3_names.js','runtime/assets/report.js','examples/top10-demo/viewer_app.js'):
        subprocess.run(['node','--check',str(ROOT/file)],check=True)
    check=(ROOT/'runtime/assets/af3_names.js').read_text()+'''
const assert=require('assert');const c={protein:'demo-protein',region:'demo-region',helix:'A-helix',uniprot:'DEMO',residue_range:[1,11],mode:'binder',synthetic:true};
assert.equal(window.AF3_NAMES.format(c,'refine:SYNTHETIC-D0:C3:P0:K0:S0:M1',1),'SYNTHETIC demo-protein demo-region A-helix DEMO 1-11 binder-rank1-refine:SYNTHETIC-D0:C3:P0:K0:S0:M1');
assert(window.AF3_NAMES.format(c,'test',0).includes('unranked'));
assert(window.AF3_NAMES.format(c,'test','1').includes('binder-rank1-'));
assert(window.AF3_NAMES.format(c,'test','1.5').includes('unranked'));
assert(window.AF3_NAMES.format(c,'test','').includes('unranked'));
assert(window.AF3_NAMES.format({},'test',null).includes('待填UniProt'));
assert(window.AF3_NAMES.format({...c,mode:'unconditional',residue_range:'NA'},'test',1).includes('NA unconditional-rank1-test'));
assert.equal(window.AF3_NAMES.context({branch:'A_minibinder',namespace:'sr56_unknown',target:{}},false).uniprot,'待填UniProt');
assert.equal(window.AF3_NAMES.context({branch:'template_project',target:{source_chain:'Q',residue_mapping:[{source_res_id:101},{source_res_id:111}]}},true).residue_range,'author:Q:101-111');
'''
    check+='const esc=x=>String(x);let tab="best";const data={main:[{design_index:"7",rank:"2"}],best:[{design_index:"7",rank:"1"}],af3_naming:c};\n'
    check+=next(line for line in (DEST/'viewer_app.js').read_text().splitlines() if line.startswith('function af3Block('))+'\n'
    check+='assert(af3Block("one",{design_index:7},{id:"test"}).includes("binder-rank1-test"));assert(af3Block("two",{design_index:7},{id:"test"}).includes("binder-rank2-test"));'
    subprocess.run(['node','-e','global.window={};'+check],check=True)
    print('PASS: synthetic TOP10 deterministic bytes, 80 model evidence pairs, baselines, best selection, local links and AF3 names')

if __name__=='__main__':run()
