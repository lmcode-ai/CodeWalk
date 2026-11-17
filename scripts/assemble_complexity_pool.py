"""Merge recovered actual functions, retaining one tested argument layout per source function."""
import argparse
import ast
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--unary',required=True);p.add_argument('--multi',required=True)
    p.add_argument('--output',required=True);p.add_argument('--min-atoms',type=int,default=80)
    args=p.parse_args();out=Path(args.output)
    if out.exists():raise ValueError('Preserve existing pools; choose a new destination')
    atoms=[json.loads(l) for path in (args.unary,args.multi) for l in Path(path).read_text(encoding='utf-8').splitlines()]
    chosen={}
    for a in sorted(atoms,key=lambda a:(a['payload']['input_size']=='shared',a['id'])):
        tree=ast.parse(a['payload']['source']);key=ast.dump(tree.body[0],include_attributes=False)
        chosen.setdefault(key,a)
    pool=sorted(chosen.values(),key=lambda a:a['id'])
    if len(pool)<args.min_atoms:raise ValueError('Insufficient distinct real functions for the requested L1 size')
    out.mkdir(parents=True)
    (out/'atoms.jsonl').write_text(''.join(json.dumps(a)+'\n' for a in pool),encoding='utf-8')
    report={'source_functions':len(pool),'source_problems':len({a['source_id'] for a in pool}),
        'selection_policy':'One representative argument layout per distinct actual function; multiple functions per problem allowed. This differs from historical one-per-problem mining.'}
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
