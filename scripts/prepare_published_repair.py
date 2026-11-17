"""Prepare one original repair repository lazily; never loads or exposes gold patches."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from codewalk.repair_restore import prepare


def main():
    p=argparse.ArgumentParser();p.add_argument('--recipes',required=True);p.add_argument('--task-id',required=True)
    p.add_argument('--output',required=True);p.add_argument('--repository',help='Optional local Git object store; otherwise fetch the original GitHub commit archive')
    args=p.parse_args();print(json.dumps(prepare(args.recipes,args.task_id,args.output,repository=args.repository),indent=2))


if __name__=='__main__':main()
