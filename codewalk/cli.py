from __future__ import annotations
import argparse
import json
from pathlib import Path
from . import data
from .domains import DOMAINS
from .graph import sample_groups
from .evaluation import summarize, grade_label


def write_json(path, value):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="CodeWalk release preparation tools (not historical generator recovery)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser('evaluate', help='Grade submissions against a versioned local benchmark')
    p.add_argument('domain', choices=DOMAINS)
    p.add_argument('--root', required=True)
    p.add_argument('--submissions', required=True)
    p.add_argument('--config', help='Toolchain/runtime JSON; use isolated runtimes for untrusted code')
    p.add_argument('--output', required=True)
    p = sub.add_parser("download")
    p.add_argument("domain", choices=DOMAINS)
    p.add_argument("--destination", default="data")
    p.add_argument("--include-verus-sources", action="store_true")
    p = sub.add_parser("inspect")
    p.add_argument("domain", choices=DOMAINS)
    p.add_argument("--root", required=True)
    p.add_argument("--output")
    p = sub.add_parser("plan", help="Produce candidate plans; does not render or admit benchmark tasks")
    p.add_argument("domain", choices=DOMAINS)
    p.add_argument("--atoms", required=True)
    p.add_argument("--level", required=True, type=int)
    p.add_argument("--count", default=1, type=int)
    p.add_argument("--seed", default=42, type=int)
    p.add_argument("--max-attempts", default=10000, type=int)
    p.add_argument("--max-per-source", type=int)
    p.add_argument("--output", required=True)
    p = sub.add_parser("score")
    p.add_argument("--tasks", required=True)
    p.add_argument("--attempts", required=True)
    p.add_argument("--n", type=int, required=True)
    p.add_argument("--output", required=True)
    p = sub.add_parser("grade-labels")
    p.add_argument("domain", choices=("codeclone", "bigo"))
    p.add_argument("--tasks", required=True, help="JSONL with task_id, level, label (judge only)")
    p.add_argument("--responses", required=True, help="JSONL with task_id, sample_idx, response")
    p.add_argument("--output", required=True)
    p = sub.add_parser("export-inputs", help="Export answer-free model payloads, not environment setup")
    p.add_argument("domain", choices=("bugfixing", "codeclone", "verus"))
    p.add_argument("--root", required=True)
    p.add_argument("--output", required=True)
    p = sub.add_parser("generate", help="Render executable tasks and run real domain admission")
    from .composition.registry import BACKENDS
    p.add_argument("domain", choices=BACKENDS)
    p.add_argument("--atoms", required=True, help="Version-1 normalized atomic JSONL, not published composite records")
    p.add_argument("--output", required=True, help="New/empty generation directory")
    p.add_argument("--level", required=True, type=int)
    p.add_argument("--count", default=1, type=int)
    p.add_argument("--seed", default=42, type=int)
    p.add_argument("--max-candidates", default=100, type=int)
    p.add_argument("--max-per-source", type=int)
    p.add_argument("--config", help="Execution, toolchain and domain options JSON")
    p.add_argument('--groups',help='Optional JSONL candidate plan with atom_ids; still requires compatibility and admission')
    p = sub.add_parser('materialize',help='Write one public task to a fresh model workspace, excluding judge data')
    p.add_argument('--inputs',required=True)
    p.add_argument('--task-id',required=True)
    p.add_argument('--output',required=True)
    args = parser.parse_args()
    try:
        if args.command == 'materialize':
            import base64
            matches=[r for r in data.read_jsonl(args.inputs) if r.get('task_id')==args.task_id]
            if len(matches)!=1:raise ValueError('Expected exactly one matching task ID')
            row=matches[0];root=Path(args.output)
            if row.get('workspace_state')=='requires_preparation_from_separate_recipe':
                raise ValueError('Original repair task requires scripts/prepare_published_repair.py and its separate preparation recipe')
            if root.exists() and any(root.iterdir()):raise ValueError('Model workspace must be new or empty')
            files=row.get('files',{});binary=row.get('binary_files_base64',{})
            if not files and not binary:raise ValueError('Task contains no public files')
            if set(files)&set(binary):raise ValueError('Text/binary path collision')
            targets={name:data.safe_path(root,name) for name in (*files,*binary)}
            for name,target in targets.items():
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(files[name].encode('utf-8') if name in files else base64.b64decode(binary[name],validate=True))
            print(json.dumps({'task_id':args.task_id,'files':len(targets),'question':row.get('question','')},indent=2))
        elif args.command == 'evaluate':
            from .benchmark import evaluate
            config = json.loads(Path(args.config).read_text(encoding='utf-8')) if args.config else {}
            results = list(evaluate(args.root, args.domain, data.read_jsonl(args.submissions), config))
            destination = Path(args.output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(''.join(json.dumps(row) + '\n' for row in results), encoding='utf-8')
            print(json.dumps({'attempts': len(results), 'infra_errors': sum(row['status'] == 'infra_error' for row in results)}, indent=2))
        elif args.command == "generate":
            from .composition import generate
            config = json.loads(Path(args.config).read_text(encoding='utf-8')) if args.config else {}
            report = generate(args.domain,data.read_jsonl(args.atoms),args.output,level=args.level,
                count=args.count,seed=args.seed,max_candidates=args.max_candidates,
                max_per_source=args.max_per_source,config=config,
                groups=[r['atom_ids'] for r in data.read_jsonl(args.groups)] if args.groups else None)
            print(json.dumps({"complete":report['complete'],"accepted":len(report['accepted']),
                              "rejected":len(report['rejected']),"blocked":report['blocked']},indent=2))
            if not report['complete']:
                parser.exit(2,'generation incomplete; see manifest.json and private execution evidence\n')
        elif args.command == "download":
            result = data.download(args.domain, args.destination, include_verus_sources=args.include_verus_sources)
            print(json.dumps({"repo_id": result["repo_id"], "revision": result["revision"], "files": len(result["files"])}, indent=2))
        elif args.command == "inspect":
            result = data.inspect(args.domain, args.root)
            if args.output:
                write_json(args.output, result)
            print(json.dumps(result, indent=2))
        elif args.command == "plan":
            domain = DOMAINS[args.domain]
            groups = sample_groups(data.read_jsonl(args.atoms), domain.compatible,
                level=args.level, count=args.count, seed=args.seed, directed=domain.DIRECTED,
                max_attempts=args.max_attempts, max_per_source=args.max_per_source)
            write_json(args.output, {"kind": "candidate_plans_not_admitted_tasks", "seed": args.seed,
                                   "plans": [domain.plan(group) for group in groups]})
        elif args.command == "score":
            write_json(args.output, summarize(data.read_jsonl(args.tasks), data.read_jsonl(args.attempts), args.n))
        elif args.command == "grade-labels":
            tasks = data.read_jsonl(args.tasks)
            bank = {r["task_id"]: r for r in tasks}
            if len(bank) != len(tasks):
                raise ValueError("Duplicate task ids")
            results = []
            for row in data.read_jsonl(args.responses):
                if row["task_id"] not in bank:
                    raise ValueError("Unknown task id")
                grade = grade_label(args.domain, row["response"], bank[row["task_id"]]["label"])
                results.append({"task_id": row["task_id"], "sample_idx": row["sample_idx"], **grade})
            p = Path(args.output)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("".join(json.dumps(r) + "\n" for r in results), encoding="utf-8")
        elif args.command == "export-inputs":
            records = [data.public_record(args.domain, r, args.root) for r in data.records(args.domain, args.root)]
            p = Path(args.output)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    main()
