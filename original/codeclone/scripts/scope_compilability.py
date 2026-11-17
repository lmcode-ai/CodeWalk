import json
import random
import re

with open("clusters.json") as f:
    clusters = json.load(f)

funcs = {}
with open("../Code-Code/Clone-detection-BigCloneBench/dataset/data.jsonl") as f:
    for line in f:
        obj = json.loads(line)
        funcs[obj["idx"]] = obj["func"]

JDK_ONLY_HINTS = ["java.util.", "java.security.", "java.lang.", "java.io.", "java.text.", "java.math."]
EXTERNAL_HINTS = ["IOUtils", "org.apache.", "com.google.", "org.springframework.", "Log4j", "org.hibernate"]
NEEDS_CONTEXT_HINTS = ["this.", "super.", "getClass()"]  # weak signal for instance-field dependence


def quick_classify(src):
    if any(h in src for h in EXTERNAL_HINTS):
        return "external_dep"
    # heuristic: uses an identifier that's not a local var/param and not a JDK type,
    # e.g. a bare lowercase identifier used as an object before any declaration --
    # too fragile to detect reliably here, just flag obvious instance-field access
    if re.search(r"\bconn(ection)?\.|`?\bjdbc\.|\bstmt\.|\bpstmt\.", src):
        return "likely_instance_field"
    return "looks_standalone"


rng = random.Random(0)
for cid, members in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
    sample = rng.sample(members, min(30, len(members)))
    counts = {"external_dep": 0, "likely_instance_field": 0, "looks_standalone": 0}
    for idx in sample:
        counts[quick_classify(funcs[idx])] += 1
    print(f"cluster {cid} (n={len(members)}): sample of {len(sample)} -> {counts}")
