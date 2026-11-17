"""Fail closed before describing or publishing a reconstruction as the paper dataset."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from codewalk.alignment import require_alignment


def main():
    p=argparse.ArgumentParser();p.add_argument('--report',default=str(ROOT/'docs/sources/three-way-alignment.json'))
    args=p.parse_args()
    try:require_alignment(json.loads(Path(args.report).read_text()))
    except ValueError as exc:print(str(exc));raise SystemExit(2)
    print('HF identities, paper task/result provenance and composition methods are all verified.')


if __name__=='__main__':main()
