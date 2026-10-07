"""Rebuild fictional TOP10 data from fixed formulas, never from research files."""
from pathlib import Path
import argparse, csv, hashlib, io, json, math, tempfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'examples/top10-demo'
TARGET = 'AGSVLTNDKEF'  # Existing CPU fixture sequence, not the SR56 target.
AA = dict(zip('ACDEFGHIKLMNPQRSTVWY', 'ALA CYS ASP GLU PHE GLY HIS ILE LYS LEU MET ASN PRO GLN ARG SER THR VAL TRP TYR'.split()))
NOTE = 'SYNTHETIC DEMO: fictional sequence, coordinates and metrics; no scientific inference.'

def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2)+'\n'

def cif(sequence, design, round_, model, generated=False):
    # Same toy helix formula as tests/fake_engines.py; no parsed structures or RNG.
    headers = 'group_PDB id type_symbol label_atom_id label_alt_id label_comp_id label_asym_id label_entity_id label_seq_id pdbx_PDB_ins_code Cartn_x Cartn_y Cartn_z occupancy B_iso_or_equiv auth_seq_id auth_comp_id auth_asym_id auth_atom_id pdbx_PDB_model_num'.split()
    lines = ['data_SYNTHETIC_DEMO', '# '+NOTE, 'loop_']+['_atom_site.'+h for h in headers]
    confidences, binder_ca, serial = [], {}, 0
    for chain, seq in [('A',TARGET),('B',sequence)]:
        for r, letter in enumerate(seq,1):
            theta=(r-1)*1.745
            ca=[1.5*(r-1),2.3*math.cos(theta),2.3*math.sin(theta)]
            if chain=='B':ca=[ca[0]+3,ca[1]+10+design*.1,ca[2]+round_*.3+model*.1]
            p=1. if chain=='A' else ([.42,.61,.81,.94][(r+design+model)%4])
            if chain=='B':binder_ca[str(r)]=p*100
            for atom,element,off in [('N','N',(-.7,.3,0)),('CA','C',(0,0,0)),('C','C',(.7,.2,0)),('O','O',(1.,.8,.1))]:
                serial+=1;coord=[ca[i]+off[i] for i in range(3)]
                fields=['ATOM',serial,element,atom,'.',AA[letter],chain,1 if chain=='A' else 2,r,'?',*(f'{v:.3f}' for v in coord),'1.00',f'{p:.2f}',r,AA[letter],chain,atom,1]
                lines.append(' '.join(map(str,fields)));confidences.append(p)
    lines.append('#')
    confidence={'synthetic':True,'note':NOTE,'confidences':{'atom_plddts':confidences,'atom_chain_ids':['A']*(len(TARGET)*4)+['B']*(len(sequence)*4)}}
    return '\n'.join(lines)+'\n',confidence,binder_ca

def generate(destination):
    files={}
    def write(path,value):
        files[path]=value.encode('utf8');p=destination/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(files[path])
    nodes=[];main=[];best=[];meta={'models':{},'nodes':{},'baselines':{}};naming={'protein':'demo-protein','region':'demo-region','helix':'A-helix','uniprot':'DEMO-NO-UNIPROT','residue_range':[1,len(TARGET)],'mode':'binder','synthetic':True}
    for d in range(10):
        sequence=('AEKLGSVT'[(d%8):]+'AEKLGSVT'*6)[:40]
        design_nodes=[]
        for round_ in range(4):
            pair=f'SYNTHETIC-D{d:02}-C{round_}-P0-K0-S0';path=f'C{round_}P0K0'
            models=[];node={'pair_id':pair,'design_index':d,'round':round_,'path':path,'baseline':round_==0,'selected':False,'sequence':sequence,'models':models,'retained_model_ids':[],'script':f'data/structures/{pair}.js'}
            mapping={'target':'A','binder':'B','target_sequence':TARGET,'binder_sequence':sequence}
            generated='A'*40
            gen,_,_=cif(generated,d,round_,0,True);mpnn,_,_=cif(sequence,d,round_,0)
            node.update(generated=f'objects/{pair}-generated.cif',mpnn=f'objects/{pair}-mpnn.cif')
            write(node['generated'],gen);write(node['mpnn'],mpnn)
            meta['nodes'][pair]={'generated':{**mapping,'binder_sequence':generated},'mpnn':mapping}
            embedded={'generated':gen,'mpnn':mpnn,'models':[]}
            for model in range(2):
                candidate=('main' if round_==0 else 'refine')+f':SYNTHETIC-D{d:02}:C{round_}:P0:K0:S0:M{model}'
                score=round(.82-d*.009+(0 if d%3==0 else [.0,.045,.03,.02][round_])-model*.002,5)
                summary={'ranking_score':score,'iptm':round(.65+d*.008,3),'ptm':.7,'overall_plddt':.74,'overall_pae':5.2,'has_clash':False,'chain_pair_pae':[[0,4.8],[4.8,0]],'chain_pair_pae_min':[[0,2.1],[2.1,0]],'synthetic':True}
                metrics={'binder_self_rmsd_A':.25+round_*.1,'binder_pose_rmsd_A':round_*.35,'target_fragment_rmsd_A':0.,'target_contact_residues':3,'contact_atom_pairs':7,'min_distance_A':4.2,'has_geometric_clash':False,'synthetic':True}
                text,confidence,ca=cif(sequence,d,round_,model)
                m={'id':candidate,'round':round_,'path':path,'model_index':model,'summary':summary,'metrics':metrics,'valid_output':True,'synthetic':True,'cif':f'objects/{pair}-M{model}.cif','conf':f'objects/{pair}-M{model}.json'}
                write(m['cif'],text);write(m['conf'],dump(confidence));models.append(m);embedded['models'].append({'id':candidate,'cif':text})
                meta['models'][candidate]={**mapping,'ca_plddt':ca,'binder_ca_mean':sum(ca.values())/len(ca)}
            node['retained_model_ids']=[models[0]['id']];nodes.append(node);design_nodes.append(node)
            write(node['script'],'window.TOP10_STRUCTURES=window.TOP10_STRUCTURES||{};\nwindow.TOP10_STRUCTURES['+json.dumps(pair)+']='+json.dumps(embedded,ensure_ascii=False).replace('<','\\u003c')+';\n')
        baseline=design_nodes[0]['models'][0];meta['baselines'][str(d)]=baseline['id']
        winner=max((n['models'][0] for n in design_nodes),key=lambda m:m['summary']['ranking_score'])
        next(n for n in design_nodes if n['round']==winner['round'])['selected']=True
        main.append({'design_index':d,'candidate_id':baseline['id'],'ranking_score':baseline['summary']['ranking_score']})
        best.append({'design_index':d,'candidate_id':winner['id'],'ranking_score':winner['summary']['ranking_score']})
    for rows in (main,best):
        rows.sort(key=lambda r:(-r['ranking_score'],r['design_index']))
        for i,row in enumerate(rows,1):row['rank']=i
    data={'schema':'synthetic-top10-demo-v1','synthetic':True,'note':NOTE,'branch':'SYNTHETIC_DEMO','run_id':'SYNTHETIC-DEMO-NO-RUN','af3_naming':naming,'target':{'sequence':TARGET,'canonical_range':None,'source':'CPU toy fixture'},'source_archive':{'filename':'SYNTHETIC-formulas-only','sha256':'NOT_APPLICABLE_NO_SOURCE_ARCHIVE'},'counts':{'actual_models':80},'main':main,'best':best,'nodes':nodes,'scientific_GPU':'NOT RUN'}
    write('index.json',dump(data));write('data/index.js','window.TOP10='+json.dumps(data,ensure_ascii=False).replace('<','\\u003c')+';\n')
    write('data/viewer.js','window.VIEWER_META='+json.dumps(meta,ensure_ascii=False).replace('<','\\u003c')+';\n')
    write('target.fasta','>SYNTHETIC_DEMO_TARGET_NO_UNIPROT\n'+TARGET+'\n')
    for stem,rows in [('main_top10',main),('refine_best_top10',best)]:
        buf=io.StringIO();buf.write('# '+NOTE+'\n');writer=csv.DictWriter(buf,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows);write(stem+'.csv',buf.getvalue())
        fasta=''
        for row in rows:
            node=next(n for n in nodes if any(m['id']==row['candidate_id'] for m in n['models']))
            fasta+='>SYNTHETIC_DEMO '+row['candidate_id']+' rank'+str(row['rank'])+'\n'+node['sequence']+'\n'
        write(stem+'.fasta',fasta)
    write('GENERATED.json',dump({'synthetic':True,'note':NOTE,'generator':'scripts/build_top10_demo.py','coordinate_formula_source':'tests/fake_engines.py synthetic_target/make_complex','files':{path:hashlib.sha256(raw).hexdigest() for path,raw in sorted(files.items())}}))
    return files

def build(check=False):
    if check:
        with tempfile.TemporaryDirectory(prefix='top10-synthetic-') as td:
            expected=generate(Path(td))
            for rel,raw in expected.items():assert (DEST/rel).read_bytes()==raw,rel
            actual={p.relative_to(DEST).as_posix() for directory in ('data','objects') for p in (DEST/directory).rglob('*') if p.is_file()}
            assert actual=={rel for rel in expected if rel.startswith(('data/','objects/'))},'Unexpected generated files'
    else:generate(DEST)
    print(('CHECKED' if check else 'BUILT')+' SYNTHETIC TOP10: 10 designs, 40 paths, 80 fictional models; no research inputs')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');build(parser.parse_args().check)
