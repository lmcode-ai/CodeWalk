"""Curate fresh admissions and explicitly restored originals without mixing their validation status."""
import base64
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import sys
import zipfile
import argparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def jsonl(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8',newline='\n') as stream:
        for row in rows:stream.write(json.dumps(row,sort_keys=True,ensure_ascii=True)+'\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--profile',default=str(ROOT/'configs/paper-reconstruction.json'))
    parser.add_argument('--output',default=str(ROOT/'outputs/paper-sized-benchmark'))
    parser.add_argument('--archive',default=str(ROOT/'outputs/paper-sized-benchmark.zip'))
    parser.add_argument('--allow-count-matched-reconstruction',action='store_true',
                        help='Explicitly export an experimental count-matched bank without a paper-alignment claim')
    args=parser.parse_args();profile=json.loads(Path(args.profile).read_text(encoding='utf-8'))
    aligned=False
    if profile.get('requires_verified_three_way_alignment'):
        from codewalk.alignment import require_alignment
        alignment=json.loads((ROOT/profile['alignment_report']).read_text())
        try:require_alignment(alignment);aligned=True
        except ValueError:
            if not args.allow_count_matched_reconstruction:raise
    out=Path(args.output).resolve()
    if out.exists():raise SystemExit('Curated output already exists; preserve it and select a new destination in the script')
    source=ROOT/'outputs/source-derived-datasets'
    banks=[p.parent for pattern in profile['bank_manifest_patterns'] for p in sorted(ROOT.glob(pattern))]
    public=defaultdict(list);judges=defaultdict(list);lineage=[];counts=defaultdict(Counter);labels=defaultdict(Counter)
    seen=set();semantic_groups=set();generation=[]
    for bank in banks:
        manifest_path=bank/'manifest.json'
        if not manifest_path.exists():continue
        report=json.loads(manifest_path.read_text(encoding='utf-8'))
        generation.append({'run':bank.relative_to(source).as_posix(),'requested':report['requested_tasks'],
            'accepted':len(report['accepted']),'complete':report['complete'],'blocked':report['blocked']})
        for accepted in report['accepted']:
            task_id=accepted['task_id'];domain=report['domain'];level=report['level']
            if domain=='codeclone' and set(accepted['atom_ids'])&set(profile.get('excluded_clone_atom_ids',[])):
                continue
            row=json.loads((bank/'tasks'/task_id/'task.json').read_text(encoding='utf-8'))
            private=bank/'private/candidates'/task_id
            judge=json.loads((private/'judge.json').read_text(encoding='utf-8'))
            if domain=='codeclone' and profile.get('balance_clone_to_expected_counts'):
                target=profile['expected_counts']['codeclone'][str(level)]
                limit=target//2 if judge['label']=='equivalent' else target-target//2
                if labels[domain][f'L{level}:{judge["label"]}']>=limit:continue
            unordered=domain=='bugfixing' or (domain=='codeclone' and row.get('composition_mode')!='chain')
            group=tuple(sorted(accepted['atom_ids'])) if unordered else tuple(accepted['atom_ids'])
            semantic=(domain,level,group)
            if semantic in semantic_groups:raise ValueError('Duplicate component group in curated data')
            semantic_groups.add(semantic)
            if task_id in seen:raise ValueError('Duplicate task identity across curated runs')
            seen.add(task_id)
            admission=json.loads((private/'admission.json').read_text(encoding='utf-8'))
            atoms=json.loads((private/'atoms.json').read_text(encoding='utf-8'))
            if admission.get('atom_gate') is not True or admission.get('reference_gate') is not True:raise ValueError('Unadmitted task')
            canonical=json.dumps(row,sort_keys=True,separators=(',',':'),ensure_ascii=True)
            if hashlib.sha256(canonical.encode()).hexdigest()!=accepted['public_sha256']:raise ValueError('Public input hash differs from admitted projection')
            admission_bytes=json.dumps(admission,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
            if hashlib.sha256(admission_bytes).hexdigest()!=accepted['admission_sha256']:raise ValueError('Admission evidence hash differs from generation receipt')
            public[domain].append(row);counts[domain][str(level)]+=1
            record={'task_id':task_id,'level':level}
            if domain in ('codeclone','bigo'):
                record['label']=judge['label'];labels[domain][f'L{level}:{judge["label"]}']+=1
            elif domain=='verus':
                reference=out/'judge/references'/f'{task_id}.rs';reference.parent.mkdir(parents=True,exist_ok=True)
                reference.write_text(judge['reference_source'],encoding='utf-8',newline='\n')
                record['reference_file']=reference.relative_to(out).as_posix()
            else:
                reference=out/'judge/references'/f'{task_id}.json';reference.parent.mkdir(parents=True,exist_ok=True)
                reference.write_text(json.dumps({'gold_patches':[a['payload']['gold_patch'] for a in atoms],
                    'base_commit':judge['base_commit'],'target_tests':judge['target_tests']},indent=2)+'\n',encoding='utf-8')
                record['reference_file']=reference.relative_to(out).as_posix();record['target_tests']=judge['target_tests']
            judges[domain].append(record)
            lineage.append({'task_id':task_id,'domain':domain,'level':level,'atom_ids':accepted['atom_ids'],
                'source_ids':accepted['source_ids'],'provenance':[a['provenance'] for a in atoms],
                'public_sha256':accepted['public_sha256'],'admission':admission,
                'implementation_sha256':report['implementation_sha256'],'backend_sha256':report.get('backend_sha256')})
    fresh_tasks=len(seen)
    restored_tasks=0
    if profile.get('published_repair_restore'):
        restored=ROOT/profile['published_repair_restore']
        restored_report=json.loads((restored/'manifest.json').read_text())
        if restored_report['validation_status']!='published_original_not_locally_readmitted':raise ValueError('Unexpected imported validation status')
        def records(path):return [json.loads(l) for l in path.read_text(encoding='utf-8').splitlines()]
        rr=records(restored/'model_inputs/bugfixing.jsonl');jj=records(restored/'judge/bugfixing.jsonl')
        ll=records(restored/'judge/lineage.jsonl');prep=records(restored/'preparation/bugfixing.jsonl')
        ids={r['task_id'] for r in rr}
        if len(ids)!=restored_report['tasks'] or any({r['task_id'] for r in group}!=ids for group in (jj,ll,prep)):
            raise ValueError('Imported repair views have inconsistent task identities')
        if ids&seen:raise ValueError('Imported task identity collides with generated bank')
        seen.update(ids);restored_tasks=len(ids)
        public['bugfixing'].extend(rr);judges['bugfixing'].extend(jj);lineage.extend(ll)
        counts['bugfixing'].update(str(r['level']) for r in jj)
        jsonl(out/'preparation/bugfixing.jsonl',prep)
    if {d:dict(c) for d,c in counts.items()}!=profile['expected_counts']:
        raise ValueError('Accepted counts do not match the declared reconstruction profile')
    for domain,rows in public.items():
        jsonl(out/'model_inputs'/f'{domain}.jsonl',rows);jsonl(out/'judge'/f'{domain}.jsonl',judges[domain])
    jsonl(out/'judge/lineage.jsonl',lineage)
    manifest={'variant':profile['variant'],'total_tasks':len(seen),
        'release_ready_as_paper_dataset':aligned,
        'admission_scope':'Reconstruction implementation gates; paper-method and historical-result identity are checked separately',
        'freshly_admitted_tasks':fresh_tasks,'restored_published_tasks':restored_tasks,
        'all_tasks_freshly_readmitted':restored_tasks==0,
        'counts_by_level':{d:dict(c) for d,c in counts.items()},'classification_labels':{d:dict(c) for d,c in labels.items()},
        'generation_runs':generation,'historical_scores_reusable':False,
        'source_overlap_with_initial_bank':'intentional; not an independent unseen-source test split',
        'original_public_counts':{'codeclone':{'1':100,'2':100,'3':100},'bugfixing':{'1':200,'2':200,'3':168},
                                  'verus':{'1':100,'2':100,'3':100,'10':100},'bigo':None},
        'limitations':{'codeclone':'Real FEMPD methods and original EvoSuite source recovered; differential suites regenerated/augmented, not historical CodeWalk admission suites.',
            'bugfixing':'Real original patches/tests/commits, only locally admitted repositories; native Windows Python environment differs from initial container images.',
            'verus':'Real algorithms and upstream reference proofs; modules/extra fixed wrappers, matched executable token projection, different toolchain; conservative i32-vector L10 subset.',
            'bigo':'Restricted extraction from 4900 actual CodeComplex programs; program-label agreement plus limited AST audit, empirical size fits; no cubic/np atoms, historical pool not recovered.'}}
    manifest['limitations'].update(profile.get('limitations',{}))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    (out/'README.md').write_text('''# Source-reconstructed benchmark

This is a newly generated, actually admitted source-derived bank, not a byte-for-byte
historical reconstruction and not synthetic toy functions. See manifest.json for exact counts,
lineage and limitations. Initial HF releases have not been modified.

`model_inputs/` contains only model-facing questions and source/repository files. `judge/`
contains labels, reference proofs, repair patches, component provenance and admission evidence.
Never mount the judge directory into an agent workspace or include it in a model prompt.
Task IDs are routing metadata. Materialize a selected row's `files` and optional
`binary_files_base64` using `codewalk materialize`; repair agents operate on the resulting
repository directory, not the entire JSON serialized into a prompt.

Classification judge JSONL is compatible with the grade-labels and score commands. Real
agent/provider runners and protected-specification proof grading remain separate.
No model scores are included. The bank intentionally reuses source components from the old
release and must not be represented as an independent source-disjoint evaluation split.

Licenses: preserve upstream notices. Repair repositories retain their own license files;
FEMPD and Verus upstream licensing is recorded in lineage. CodeComplex upstream source
redistribution terms were not verified; local recovery is not a new license grant. This
directory has not been uploaded or published remotely.
''',encoding='utf-8',newline='\n')
    if restored_tasks:
        readme=out/'README.md'
        text=readme.read_text().replace('actually admitted source-derived bank','source-derived bank with explicitly recorded validation status')
        text+='\n## Original repair bank restoration\n\n'+str(restored_tasks)+' repair task definitions were restored unchanged from the pinned public\nrelease, including their original groups and environment recipes. They have not all been\nfreshly executed locally. `preparation/bugfixing.jsonl` is harness metadata, not a model\nprompt; materialize the original repository environment before launching an agent.\nDo not claim all tasks passed new G1/G2 checks based on this import.\n\nSee manifest.json for freshly admitted versus restored counts and domain-specific\nreconstruction limitations. Exact paper counts do not establish historical reproduction.\n'
        readme.write_text(text,encoding='utf-8')
    if profile.get('requires_verified_three_way_alignment') and not aligned:
        readme=out/'README.md'
        readme.write_text('# Alignment status: count-matched reconstruction only\n\n'
            'HF identity, paper task/result provenance and composition-method alignment are not verified. '
            'This export cannot reproduce the historical paper results.\n\n'+readme.read_text(),encoding='utf-8')
    files=sorted(p for p in out.rglob('*') if p.is_file())
    (out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(out).as_posix()+'\n' for p in files),encoding='utf-8')
    target=Path(args.archive).resolve()
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in out.rglob('*') if p.is_file()):archive.write(path,'source-reconstructed-benchmark/'+path.relative_to(out).as_posix())
    print(json.dumps({'tasks':len(seen),'counts':manifest['counts_by_level'],'zip_bytes':target.stat().st_size},indent=2))


if __name__=='__main__':main()
