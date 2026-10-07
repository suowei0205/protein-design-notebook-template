"""Synthetic stdlib check for feedback v2 paths, legacy reads and passive imports."""
import hashlib, json, os, stat, sys, tempfile, time, zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime as RealDatetime
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
import sr56_feedback as f

CIF='data_SYNTHETIC\nloop_\n_atom_site.group_PDB\n_atom_site.label_atom_id\n_atom_site.label_comp_id\n_atom_site.label_asym_id\n_atom_site.label_seq_id\n_atom_site.Cartn_x\n_atom_site.Cartn_y\n_atom_site.Cartn_z\n_atom_site.B_iso_or_equiv\nATOM CA ALA A 1 0 0 0 0.8\nATOM CA ALA B 1 4 0 0 0.8\nATOM CA ALA B 2 4 0 1 0.8\n#\n'
SVG=b'<svg xmlns="http://www.w3.org/2000/svg"><script>window.EVIL=true</script></svg>'

def put(root,name,text):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);return p

def fixture(root,legacy=False):
    root.mkdir();monitor='state' if legacy else 'monitor'
    out=root/'outputs_fixture' if legacy else root
    out.mkdir(exist_ok=True)
    run={'schema':f.SCHEMA,'run_id':'legacy' if legacy else 'modern','branch':'A_minibinder','attempt_id':'fixture',
         'created_at':'2026-10-07T00:00:00+00:00','status':'COMPLETED','namespace':'synthetic',
         'out_dir':str(out),'session_path':str(root/monitor/'session.json'),'config':{'CACHE_SCHEMA':'fixture-cache'},
         'target':{'chain':'A','sequence':'A'},'notebook_sha256':'synthetic','synthetic':True}
    f.write_json(root/monitor/'session.json',run);events=[];receipts={}
    for stage,key,leaf in [('main_rf3','rf3_0_0','d0_s0'),('refine_rf3','rf3','D0_C1_P0_K0_S0')]:
        phase='main' if stage=='main_rf3' else 'refine'
        models=out/(stage if legacy else phase+'/rf3')/leaf
        cp=put(models,'model.cif',CIF);conf=put(models,'confidence.json','{"summary":{"ranking_score":0.9}}')
        generated=put(out/(phase+'_rfd3' if legacy else phase+'/rfd3'),'generated.cif',CIF)
        mpnn=put(out/(phase+'_mpnn' if legacy else phase+'/mpnn'),'mpnn.cif',CIF)
        pair='main:D0:S0' if phase=='main' else 'refine:D0:C1:P0:K0:S0'
        payload={'input_seq':'AA','models':[{'mi':0,'cif':str(cp),'conf':str(conf)}]}
        receipt={'schema':'fixture-cache','run_namespace':'synthetic','ts':time.time(),'payload':payload,
                 'files':[{'path':str(p),'sha256':f.digest(p)} for p in (cp,conf)]}
        receipt_path=(models/'complete.json' if legacy else root/'checkpoints'/phase/'rf3'/leaf/'complete.json')
        f.write_json(receipt_path,{key:receipt})
        data={'id':pair+':M0','pair_id':pair,'design_index':0,'round':0 if phase=='main' else 1,
              'parent_index':0,'backbone':0,'sequence_index':0,'model_index':0,'sequence':'AA',
              'cif':str(cp),'conf':str(conf),'generated_path':str(generated),'mpnn_path':str(mpnn),
              'valid_output':True,'summary':{'ranking_score':0.9},'metrics':{},
              'assessment_artifacts':{'cif_sha256':f.digest(cp),'conf_sha256':f.digest(conf)}}
        events.append({'run_id':run['run_id'],'attempt_id':'fixture','ts':run['created_at'],'stage':stage,'event':'MODEL','key':data['id'],'data':data})
        events.append({'run_id':run['run_id'],'attempt_id':'fixture','ts':run['created_at'],'stage':stage,'event':'FINAL_SELECTED','key':data['id'],'data':{'id':data['id'],'selection':phase,'design_index':0}})
    for receipt_name,key,payload in [('main/checkpoint.json','rfd3_batch_0',{'n_generated':2}),('refine/refine_complete.json','D0_C1_round',{'selected':[[0,0,0,0]],'n_candidates':1}),('main/rf3/complete.json','rf3_1_0',{'input_seq':'AA','models':[]})]:
        destination=out/('checkpoint.json' if legacy else 'checkpoints/'+receipt_name)
        receipts=f.read_json(destination,{})
        receipts[key]={'schema':'fixture-cache','run_namespace':'synthetic','ts':time.time(),'payload':payload,'files':[]}
        f.write_json(destination,receipts)
    put(root,monitor+'/events.jsonl',''.join(f.dumps(e)+'\n' for e in events))
    put(root,'checkpoints/checkpoint_identity.json','broken but not a receipt')
    put(root,'main/rfd3/input.json','{"input":"not a receipt"}')
    put(root,'prep/target.cif',CIF);put(root,'reports/main/rankings.csv','score\n0.9\n')
    native=root/'reports/svg/native.svg';native.parent.mkdir(parents=True);native.write_bytes(SVG)
    put(root,monitor+'/executed_notebook.ipynb','{"cells":[]}');put(root,'main/mpnn/sequence.fasta','>synthetic\nAA\n')
    put(root,'resources/secret.json','{}');put(root,'reports/assets/ignore.json','{}')
    return run

def members(path):
    with zipfile.ZipFile(path) as z:return {name:z.read(name) for name in z.namelist()}

def signed(contents,path,schema=f.BUNDLE_SCHEMA):
    raw=contents.copy();m=json.loads(raw.pop('MANIFEST.json'));raw.pop('SHA256SUMS.txt')
    m['schema']=schema
    if schema==f.SCHEMA:
        m.pop('layout_version',None);m.pop('report_entry',None)
    m['files']=[{'path':n,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()} for n,b in sorted(raw.items())]
    raw['MANIFEST.json']=f.dumps(m).encode();raw['SHA256SUMS.txt']=(''.join(e['sha256']+'  '+e['path']+'\n' for e in m['files'])+hashlib.sha256(raw['MANIFEST.json']).hexdigest()+'  MANIFEST.json\n').encode()
    with zipfile.ZipFile(path,'w') as z:
        for name,blob in raw.items():z.writestr(name,blob)
    return path

def rejects(path):
    try:f.verify_bundle(path)
    except (ValueError,KeyError,zipfile.BadZipFile):return
    raise AssertionError('Unsafe bundle accepted')

class FrozenDatetime(RealDatetime):
    @classmethod
    def now(cls,tz=None):return cls(2026,10,7,12,34,56,tzinfo=tz)

def run():
    with tempfile.TemporaryDirectory(prefix='sr56-feedback-check-') as tmp:
        temp=Path(tmp).resolve();root=temp/'new';old=temp/'old';fixture(root);fixture(old,True)
        for r in (root,old):
            strict=f.collect(r);monitor=f.collect_monitor(r)
            assert strict['counts']['rf3_pairs']==3 and strict['counts']['rf3_models']==2
            assert monitor['counts']['rf3_pairs']==3 and monitor['counts']['rf3_models']==2
            assert strict['counts']['rfd3_generated']==2 and strict['counts']['rounds_completed']==1
            assert not any(i['code'].startswith('CHECKPOINT_') for i in strict['issues'])
        snap=temp/'snapshot';data=f.assemble(root,snap);loaded=f.load_report_data(snap)
        assert data['counts']==loaded['counts'] and len(f.selected_pairs(data))==2
        assert (snap/'README.html').read_text().find('reports/index.html')>=0
        assert (snap/'reports/svg/native.svg').read_bytes()==SVG
        assert not (snap/'data/source').exists() and not (snap/'resources').exists()
        assert not (snap/'reports/assets/ignore.json').exists()
        evidence=(root/'reports/svg/native.svg').read_bytes()
        f.render_report(root)
        assert (root/'reports/index.html').is_file() and (root/'reports/svg/native.svg').read_bytes()==evidence
        f.render_report(root,mode='monitor')
        assert (root/'monitor/index.html').is_file() and not (root/'monitor/live').exists()
        later=f.assemble(root,temp/'after-render')
        assert later['counts']==loaded['counts']
        assert not any(a['path'].startswith(('reports/data/','reports/assets/','monitor/assets/','monitor/data/')) for a in later['artifacts'])
        for c in loaded['candidates']:
            assert c['structure']['included']
            for key in ('script','generated','mpnn','rf3','conf'):
                ref=c['structure'][key];assert f.safe_data_path(ref) and (snap/ref).is_file()
        html=(snap/'reports/index.html').read_text();assert "? '../'+value : '';" in html
        assert all(f.safe_data_path(a['path']) for a in loaded['artifacts'])
        with patch.object(f,'datetime',FrozenDatetime):
            one=f.export_feedback(root);two=f.export_feedback(root)
            assert one.name=='feedback_2026-10-07_123456.zip' and two.name=='feedback_2026-10-07_123456_02.zip'
            with ThreadPoolExecutor(max_workers=2) as pool:concurrent=list(pool.map(lambda _:f.export_feedback(root),range(2)))
        assert len({one,two,*concurrent})==4 and all(p.is_file() for p in (one,two,*concurrent))
        for archive in (one,two,*concurrent):
            m=f.verify_bundle(archive);assert m['schema']==f.BUNDLE_SCHEMA and m['report_entry']=='reports/report.json'
            assert archive.with_suffix('.zip.sha256').read_text()==f.digest(archive)+'  '+archive.name+'\n'
        before=one.read_bytes()
        try:f.export_feedback(root,one)
        except FileExistsError:pass
        else:raise AssertionError('Existing explicit output overwritten')
        assert one.read_bytes()==before
        # A cold terminal export publishes both local views from one collection.
        cold=temp/'cold-terminal-export';fixture(cold)
        assert not (cold/'reports/index.html').exists() and not (cold/'monitor/index.html').exists()
        original_session=(cold/'monitor/session.json').read_bytes();original_svg=(cold/'reports/svg/native.svg').read_bytes()
        with patch.object(f,'collect',wraps=f.collect) as collecting,patch.object(f,'collect_monitor',side_effect=AssertionError('Unexpected second collection')):
            cold_zip=f.export_feedback(cold)
            assert collecting.call_count==1
        with zipfile.ZipFile(cold_zip) as archive:
            for name in ('index.html','report.json','artifact_index.json','summary.md','missing_structure_request.json','data/candidates.json'):
                assert (cold/'reports'/name).read_bytes()==archive.read('reports/'+name)
        terminal_html=(cold/'monitor/index.html').read_text()
        terminal_data=json.loads(terminal_html.split('<script id="report-data" type="application/json">',1)[1].split('</script>',1)[0])
        assert terminal_data['mode']=='monitor' and terminal_data['run']['status']=='COMPLETED'
        assert (cold/'monitor/session.json').read_bytes()==original_session and (cold/'reports/svg/native.svg').read_bytes()==original_svg
        finish_root=temp/'finish-without-watcher'
        session=f.start(finish_root,'A_minibinder',namespace='synthetic',notebook_sha256='synthetic',background=False,run_label='fixture')
        session.configure({'CACHE_SCHEMA':'fixture-cache'},{},'synthetic',finish_root)
        with patch.object(f,'collect',wraps=f.collect) as collecting,patch.object(f,'collect_monitor',side_effect=AssertionError('Unexpected second collection')):
            session.finish('COMPLETED');assert collecting.call_count==1
        assert (finish_root/'reports/index.html').is_file() and (finish_root/'monitor/index.html').is_file()
        assert f.verify_bundle(next((finish_root/'feedback').glob('*.zip')))['computation_status']=='COMPLETED'
        # Publication of generated local views obeys the same ROOT write boundary.
        view_outside=temp/'view-outside';view_outside.mkdir();put(view_outside,'sentinel.txt','unchanged')
        for component in ('reports/data','monitor/assets','monitor/index.html'):
            bad_view=temp/('linked-view-'+component.replace('/','-'));fixture(bad_view)
            (bad_view/component).symlink_to(view_outside if component!='monitor/index.html' else view_outside/'sentinel.txt',target_is_directory=component!='monitor/index.html')
            try:f.export_feedback(bad_view)
            except ValueError as exc:assert 'Output symlink' in str(exc) or 'Unsafe output path' in str(exc)
            else:raise AssertionError('Linked local generated view accepted: '+component)
            assert not (bad_view/'reports/index.html').exists()
            assert not list((bad_view/'feedback').glob('*.zip')) and not list((bad_view/'feedback').glob('*.sha256'))
            assert {p.name for p in view_outside.iterdir()}=={'sentinel.txt'} and (view_outside/'sentinel.txt').read_text()=='unchanged'
        # No default or nested explicit export can write through a directory link.
        export_outside=temp/'export-outside';export_outside.mkdir();put(export_outside,'sentinel.txt','unchanged')
        link_root=temp/'linked-export';fixture(link_root);(link_root/'feedback').symlink_to(export_outside,target_is_directory=True)
        try:f.export_feedback(link_root)
        except ValueError as exc:assert 'Unsafe output path' in str(exc)
        else:raise AssertionError('Default feedback directory symlink accepted')
        assert {p.name for p in export_outside.iterdir()}=={'sentinel.txt'}
        dangling_root=temp/'dangling-export';fixture(dangling_root)
        (dangling_root/'feedback').symlink_to(temp/'absent-export',target_is_directory=True)
        try:f.export_feedback(dangling_root)
        except ValueError:pass
        else:raise AssertionError('Dangling feedback directory symlink accepted')
        assert not (temp/'absent-export').exists()
        (root/'export-alias').symlink_to(export_outside,target_is_directory=True)
        try:f.export_feedback(root,root/'export-alias/deeper/explicit.zip')
        except ValueError:pass
        else:raise AssertionError('Explicit output symlink ancestor accepted')
        assert {p.name for p in export_outside.iterdir()}=={'sentinel.txt'}
        modern=members(one);legacy=modern.copy()
        report=json.loads(legacy.pop('reports/report.json'));report.pop('layout_version',None)
        report['run']['run_id']='legacy-import';legacy['report.json']=f.dumps(report).encode()
        lm=json.loads(legacy['MANIFEST.json']);lm['run_id']='legacy-import';legacy['MANIFEST.json']=f.dumps(lm).encode()
        legacy_zip=signed(legacy,temp/'legacy.zip',f.SCHEMA);f.verify_bundle(legacy_zip)
        # Legacy original wrapper references remain readable and republish at canonical ROOT paths.
        report=json.loads(legacy['report.json']);candidates=json.loads(legacy['reports/data/candidates.json'])
        report['evidence_files']={'candidates':'data/candidates.json','artifacts':'artifact_index.json','checkpoint_hashes':'data/checkpoint_hashes.json'}
        legacy['report.json']=f.dumps(report).encode()
        for c in candidates:
            for key in ('generated','mpnn','rf3','conf'):c['structure'][key]='data/source/'+c['structure'][key]
            c['structure']['script']=c['structure']['script'].removeprefix('reports/')
        legacy['reports/data/candidates.json']=f.dumps(candidates).encode()
        for name in list(legacy):
            if name.startswith('reports/data/'):legacy[name.removeprefix('reports/')]=legacy.pop(name)
            elif name in ('reports/artifact_index.json','reports/summary.md','reports/missing_structure_request.json'):legacy[name.removeprefix('reports/')]=legacy.pop(name)
        for name in list(legacy):
            if name.startswith(('main/','refine/','monitor/','checkpoints/','prep/','reports/svg/')):legacy['data/source/'+name]=legacy.pop(name)
        legacy_zip=signed(legacy,temp/'legacy.zip',f.SCHEMA)
        attacks=modern.copy();attacks['main/evil.html']=b'<script>EVIL</script>';attacks['main/evil.js']=b'window.EVIL=true';attacks['main/evil.svg']=SVG
        am=json.loads(attacks['MANIFEST.json']);am['snapshot_at']='2026-10-07T12:34:57+08:00';attacks['MANIFEST.json']=f.dumps(am).encode()
        attack_zip=signed(attacks,temp/'active.zip');f.verify_bundle(attack_zip)
        merged=temp/'merged';f.merge_bundles([one,legacy_zip,attack_zip],merged)
        # Every actual merged output subtree must stay inside its declared ROOT.
        merge_outside=temp/'merge-outside';merge_outside.mkdir();put(merge_outside,'sentinel.txt','unchanged')
        for component in ('runs','assets','data'):
            bad_out=temp/('linked-merge-'+component);bad_out.mkdir()
            f.write_json(bad_out/'merge_index.json',{'schema':f.SCHEMA,'imports':[]})
            prior_index=(bad_out/'merge_index.json').read_bytes()
            (bad_out/component).symlink_to(merge_outside,target_is_directory=True)
            try:f.merge_bundles([one],bad_out)
            except ValueError:pass
            else:raise AssertionError('Merge output directory symlink accepted: '+component)
            assert (bad_out/'merge_index.json').read_bytes()==prior_index and not (bad_out/'index.html').exists()
            assert {p.name for p in merge_outside.iterdir()}=={'sentinel.txt'}
        staging_out=temp/'linked-staging';staging_out.mkdir();staging_link=staging_out/'.import_link'
        staging_link.symlink_to(merge_outside,target_is_directory=True)
        class LinkedStaging:
            def __init__(self,*args,**kwargs):pass
            def __enter__(self):return str(staging_link)
            def __exit__(self,*args):pass
        with patch.object(f.tempfile,'TemporaryDirectory',LinkedStaging):
            try:f.merge_bundles([one],staging_out)
            except ValueError:pass
            else:raise AssertionError('Linked merge staging accepted')
        assert not (staging_out/'merge_index.json').exists() and not (staging_out/'index.html').exists()
        assert {p.name for p in merge_outside.iterdir()}=={'sentinel.txt'}
        collision=legacy.copy();collision['data/source/main/x.csv']=b'wrapped-original\n';collision['main/x.csv']=b'canonical-original\n'
        collision_manifest=json.loads(collision['MANIFEST.json']);collision_manifest['snapshot_at']='2026-10-07T12:34:59+08:00'
        collision['MANIFEST.json']=f.dumps(collision_manifest).encode()
        collision_zip=signed(collision,temp/'canonical-collision.zip',f.SCHEMA);f.verify_bundle(collision_zip)
        original_collision_bytes=collision_zip.read_bytes();prior_index=(merged/'merge_index.json').read_bytes()
        prior_runs={p.name for p in (merged/'runs').iterdir()}
        try:f.merge_bundles([collision_zip],merged)
        except ValueError as exc:assert 'Canonical evidence path collision' in str(exc)
        else:raise AssertionError('Legacy canonical evidence overwrite accepted')
        assert collision_zip.read_bytes()==original_collision_bytes
        assert (merged/'merge_index.json').read_bytes()==prior_index and {p.name for p in (merged/'runs').iterdir()}==prior_runs
        imported=f.read_json(merged/'merge_index.json')['imports'];assert len(imported)==3
        for item in imported:
            pub=merged/Path(item['path']).parent.parent;d=f.load_report_data(pub)
            assert (pub/'README.html').is_file() and f.digest(pub/'original-feedback.zip')==item['zip_sha256']
            assert d['counts']==loaded['counts'] and len(d['candidates'])==2
            assert not any(p.suffix=='.svg' or p.name in ('evil.html','evil.js') for p in pub.rglob('*'))
            assert all((pub/c['structure']['rf3']).is_file() for c in d['candidates'])
            assert not (pub/'data/source').exists()
        malicious=modern.copy();registry=next(n for n in malicious if n.startswith('reports/data/structures/'))
        malicious[registry]+=b'window.EVIL=true;'
        mm=json.loads(malicious['MANIFEST.json']);mm['snapshot_at']='2026-10-07T12:34:58+08:00';malicious['MANIFEST.json']=f.dumps(mm).encode()
        malicious_zip=signed(malicious,temp/'registry-evil.zip');f.verify_bundle(malicious_zip)
        before_index=(merged/'merge_index.json').read_bytes()
        try:f.merge_bundles([malicious_zip],merged)
        except ValueError:pass
        else:raise AssertionError('Executable structure registry accepted')
        assert (merged/'merge_index.json').read_bytes()==before_index
        f.merge_bundles([one],merged);assert len(f.read_json(merged/'merge_index.json')['imports'])==3
        for name in ('../escape','/escape','a\\b','a/../b'):
            path=temp/'unsafe.zip'
            with zipfile.ZipFile(path,'w') as z:z.writestr(name,b'bad')
            rejects(path)
        link=temp/'symlink.zip'
        with zipfile.ZipFile(link,'w') as z:
            info=zipfile.ZipInfo('main/link');info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,'../escape')
        rejects(link)
        unknown=modern.copy();m=json.loads(unknown['MANIFEST.json']);m['layout_version']=99;unknown['MANIFEST.json']=f.dumps(m).encode()
        rejects(signed(unknown,temp/'unknown.zip'))
        outside=put(temp,'outside.json','{}');(root/'main/link.json').symlink_to(outside)
        assert f.safe_inside(root,'main/link.json') is None and not any(p.name=='link.json' for p in f._source_files(root))
    print('PASS: new/old strict+monitor counts; canonical evidence+candidate refs; README; native SVG; UTC+8 collision/concurrency exports; hashes; v1/v2 verify/import/merge; traversal/symlink/active-source exclusions; export/merge linked-output refusal; staging guard; legacy canonical collision refusal; cold terminal+finish views from one collection; local view output guards')

if __name__=='__main__':run()
