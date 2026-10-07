"""Synthetic local-coordinate target preparation boundaries; CPU only."""
from pathlib import Path
import hashlib, json, sys, tempfile
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'runtime'))
from target_input import prepare_target
from fake_engines import synthetic_target, write_cif
import numpy as np
from biotite.structure import concatenate, get_residue_starts
from biotite.structure.io.pdb import PDBFile


def rejected(call, message=None):
    try:
        call()
    except (ValueError, KeyError, IndexError, FileNotFoundError) as exc:
        if message:
            assert message in str(exc), str(exc)
        return
    raise AssertionError('Invalid target input accepted')


def write_pdb(aa, path):
    file = PDBFile(); file.set_structure(aa); file.write(str(path))


def run():
    count = 0
    with tempfile.TemporaryDirectory(prefix='target-input-cpu-') as td:
        temp = Path(td).resolve(); aa = synthetic_target()
        paths = []
        for ext, writer in (('.cif', write_cif), ('.mmcif', write_cif), ('.pdb', write_pdb)):
            path = temp/('synthetic'+ext); writer(aa, path); paths.append(path)
            result, seq, provenance = prepare_target(path,'Q',None,'',temp/('prepared'+ext))
            assert len(seq)==11 and seq=='AGSVLTNDKEF'
            assert set(result.chain_id)=={'A'} and list(result.res_id[get_residue_starts(result)])==list(range(1,12))
            assert np.allclose(result.coord,aa.coord,atol=.001)
            assert provenance['source_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
            assert provenance['target_cif_sha256']==hashlib.sha256((temp/('prepared'+ext)/'target.cif').read_bytes()).hexdigest()
            assert provenance['residue_mapping'][0]=={'source_chain':'Q','source_res_id':101,'source_ins_code':'','target_chain':'A','target_res_id':1}
            assert provenance['residue_mapping'][-1]['source_res_id']==111
            prepared = temp/('prepared'+ext)
            before = {p.name:p.read_bytes() for p in prepared.iterdir()}
            repeat = prepare_target(path,'Q',None,seq, temp/('expected'+ext))
            assert repeat[1]==seq
            assert prepare_target(path,'Q',None,'',prepared)[2]==provenance
            assert {p.name:p.read_bytes() for p in prepared.iterdir()}==before
            count += 1
        path=paths[0]
        selected,seq,provenance=prepare_target(path,'Q',(103,107),'SVLTN',temp/'segment')
        assert seq=='SVLTN' and provenance['target_range']==[1,5]
        assert [x['source_res_id'] for x in provenance['residue_mapping']]==list(range(103,108))
        assert np.allclose(selected.coord,aa.coord[8:28],atol=.001);count+=1
        modified=aa.copy();modified.res_name[:4]='MSE';modified.hetero[:4]=True
        modified_path=temp/'modified.cif';write_cif(modified,modified_path)
        assert prepare_target(modified_path,'Q',(103,107),'SVLTN',temp/'modified-outside')[1]=='SVLTN';count+=1
        rejected(lambda:prepare_target(modified_path,'Q',(101,107),'',temp/'modified-inside'),'Modified');count+=1
        # Chain selection excludes another protein chain, water and ligand records.
        other=synthetic_target(3,'R',1);water=other[:1].copy();water.hetero[:]=True;water.res_name[:]='HOH';water.atom_name[:]='O'
        multichain=temp/'multichain.cif';write_cif(concatenate((aa,other,water)),multichain)
        assert prepare_target(multichain,'Q',None,'',temp/'multichain-out')[1]=='AGSVLTNDKEF';count+=1
        # A model must be explicit and repeatable; model 2 differs in coordinates.
        model_file=temp/'models.pdb';text=paths[2].read_text();atoms='\n'.join(x for x in text.splitlines() if x.startswith(('ATOM','HETATM')))+'\n'
        model_file.write_text('MODEL        1\n'+atoms+'ENDMDL\nMODEL        2\n'+atoms+'ENDMDL\nEND\n')
        assert prepare_target(model_file,'Q',None,'',temp/'model2',model=2)[2]['model']==2;count+=1
        # Explicit alternate-location policy selects one complete residue conformer.
        alt=temp/'altloc.pdb';lines=paths[2].read_text().splitlines();atom_lines=[x for x in lines if x.startswith('ATOM')]
        alt_lines=[]
        for line in atom_lines[:4]:
            alt_lines.append(line[:16]+'A'+line[17:54]+'  0.20'+line[60:])
        for line in atom_lines[:4]:
            x=float(line[30:38])+10.
            alt_lines.append(line[:16]+'B'+line[17:30]+f'{x:8.3f}'+line[38:54]+'  0.80'+line[60:])
        alt.write_text('\n'.join(alt_lines+atom_lines[4:])+'\nEND\n')
        first=prepare_target(alt,'Q',None,'',temp/'alt-first',altloc='first')[0]
        occupied=prepare_target(alt,'Q',None,'',temp/'alt-occupancy',altloc='occupancy')[0]
        assert np.allclose(first.coord[:4],aa.coord[:4],atol=.001)
        assert np.allclose(occupied.coord[:4],aa.coord[:4]+[10.,0.,0.],atol=.001);count+=1
        for kwargs in ({'chain':''},{'chain':'missing'},{'residue_range':(100,105)},{'residue_range':(101,112)},
                       {'residue_range':(105,101)},{'residue_range':(True,105)},{'residue_range':(101,)},
                       {'model':0},{'model':True},{'altloc':'all'},{'expected_sequence':None},{'expected_sequence':'AAAA'}):
            settings={'source':path,'chain':'Q','residue_range':None,'expected_sequence':'','directory':temp/'bad-arguments'}
            settings.update(kwargs);rejected(lambda s=settings:prepare_target(**s));count+=1
        for name,mutate in [('gap',lambda x:x.res_id.__setitem__(slice(12,None),x.res_id[12:]+1)),
                            ('backwards',lambda x:x.res_id.__setitem__(slice(12,16),99)),
                            ('nonstandard',lambda x:x.res_name.__setitem__(slice(0,4),'UNK')),
                            ('duplicate-atom',lambda x:x.atom_name.__setitem__(1,'N')),
                            ('degenerate',lambda x:x.coord.__setitem__(slice(None),0.))]:
            bad=aa.copy();mutate(bad);bad_path=temp/(name+'.cif');write_cif(bad,bad_path)
            rejected(lambda p=bad_path:prepare_target(p,'Q',None,'',temp/(name+'-out')));count+=1
        missing=aa[~((aa.res_id==102)&(aa.atom_name=='O'))];bad=temp/'missing.cif';write_cif(missing,bad)
        rejected(lambda:prepare_target(bad,'Q',None,'',temp/'missing-out'));count+=1
        duplicate=concatenate((aa[:4],aa[:4],aa[4:]));bad=temp/'duplicate.cif';write_cif(duplicate,bad)
        rejected(lambda:prepare_target(bad,'Q',None,'',temp/'duplicate-out'));count+=1
        # Insertion IDs are recorded, then normalized to a consecutive target range.
        inserted=aa.copy();inserted.res_id[4:8]=101;inserted.ins_code[4:8]='A';inserted.res_id[8:]-=1
        ins=temp/'insertion.cif';write_cif(inserted,ins)
        assert prepare_target(ins,'Q',None,'',temp/'insert-out')[2]['residue_mapping'][1]['source_ins_code']=='A';count+=1
        # Every persisted identity/artifact change refuses resume without rewriting evidence.
        prepared=temp/'identity';prepare_target(path,'Q',None,'',prepared)
        before={p.name:p.read_bytes() for p in prepared.iterdir()};raw=path.read_bytes();path.write_bytes(raw+b'# content change\n')
        rejected(lambda:prepare_target(path,'Q',None,'',prepared),'changed')
        assert {p.name:p.read_bytes() for p in prepared.iterdir()}==before;path.write_bytes(raw);count+=1
        rejected(lambda:prepare_target(path,'Q',(102,108),'',prepared),'changed');count+=1
        target=prepared/'target.cif';target.write_bytes(target.read_bytes()+b'# tamper\n')
        tampered={p.name:p.read_bytes() for p in prepared.iterdir()}
        rejected(lambda:prepare_target(path,'Q',None,'',prepared),'changed');assert {p.name:p.read_bytes() for p in prepared.iterdir()}==tampered;count+=1
        target.write_bytes(before['target.cif']);record=prepared/'target.provenance.json';provenance=json.loads(record.read_text());provenance['source_chain']='changed';record.write_text(json.dumps(provenance))
        rejected(lambda:prepare_target(path,'Q',None,'',prepared),'changed');count+=1
        linked=temp/'linked.cif';linked.symlink_to(path)
        rejected(lambda:prepare_target(linked,'Q',None,'',temp/'linked-out'),'symlinks');count+=1
        parent=temp/'input-link';parent.symlink_to(temp,target_is_directory=True)
        rejected(lambda:prepare_target(parent/path.name,'Q',None,'',temp/'ancestor-out'),'symlinks');count+=1
        out=temp/'out-link';out.symlink_to(temp/'outside',target_is_directory=True)
        rejected(lambda:prepare_target(path,'Q',None,'',out),'symlinks');assert not (temp/'outside').exists();count+=1
        unsupported=temp/'source.txt';unsupported.write_bytes(raw)
        rejected(lambda:prepare_target(unsupported,'Q',None,'',temp/'unsupported-out'),'formats');count+=1
        rejected(lambda:prepare_target(temp/'absent.cif','Q',None,'',temp/'absent-out'),'missing');count+=1
        oversized=temp/'oversized.cif'
        with oversized.open('wb') as stream:stream.truncate(64*1024**2+1)
        rejected(lambda:prepare_target(oversized,'Q',None,'',temp/'oversized-out'),'64 MiB')
        assert not (temp/'oversized-out').exists();count+=1

        # Nonfinite coordinates and unavailable models are refused by parser/preparation.
        nan=aa.copy();nan.coord[0,0]=np.nan;bad=temp/'nan.cif';write_cif(nan,bad)
        rejected(lambda:prepare_target(bad,'Q',None,'',temp/'nan-out'));count+=1
        rejected(lambda:prepare_target(path,'Q',None,'',temp/'missing-model',model=99));count+=1
    print(f'PASS target_input: {count} synthetic checks, non-32 target, PDB/mmCIF, mapping, resume refusal; no GPU/network')
    return count

if __name__=='__main__':run()
