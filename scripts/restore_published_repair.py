"""Restore the full original 568-task repair bank, with references kept private."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from codewalk.repair_restore import restore


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',default=str(ROOT/'data/bugfixing'))
    p.add_argument('--output',required=True);args=p.parse_args()
    print(json.dumps(restore(args.source,args.output),indent=2))


if __name__=='__main__':main()
