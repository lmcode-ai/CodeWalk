"""Run actual four-domain generation at N=1/2/3/10 with trusted synthetic atoms."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from codewalk.composition import generate
from examples.generation_demo import prepare


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--java-config')
    parser.add_argument('--verus-config')
    args=parser.parse_args()
    root=Path(args.output).resolve()
    if root.exists() and any(root.iterdir()): raise SystemExit('Use a new/empty output directory')
    root.mkdir(parents=True,exist_ok=True)
    summary={'scope':'real tools on trusted synthetic atoms; not historical dataset reproduction',
             'cases':[],'complete':True}
    for domain in ('bigo','bugfixing','codeclone','verus'):
        config_path=args.java_config if domain=='codeclone' else args.verus_config if domain=='verus' else None
        config=json.loads(Path(config_path).read_text()) if config_path else {}
        for level in (1,2,3,10):
            work=root/f'{domain}-L{level}'
            atoms=prepare(domain,work/'fixtures',level)
            report=generate(domain,atoms,work/'generated',level=level,config=config)
            case={'domain':domain,'level':level,'complete':report['complete'],
                  'accepted':len(report['accepted']),'blocked':report['blocked'],'rejected':report['rejected']}
            summary['cases'].append(case)
            summary['complete'] &= report['complete']
            print(json.dumps(case),flush=True)
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    if not summary['complete']: raise SystemExit(2)


if __name__=='__main__': main()
