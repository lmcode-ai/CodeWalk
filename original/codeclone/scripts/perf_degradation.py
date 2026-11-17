"""
Ln -> Ln+1 composition performance-degradation feasibility harness.

For a given model: prompt it to generate Java code solving each of a small set of
Ln problems (fixed signature `public static int[] solve(int[] a)`), grade with
execution-based unit tests (not the noisy embedding/LLM equivalence detector from
slice 2). Take the Ln problems the model solved correctly, compose every ordered
pair into an Ln+1 problem (do task i, then feed the result into task j), prompt the
model again, grade the same way. Report Ln pass rate, Ln+1 pass rate (restricted to
problems built from Ln-passing pairs), and whether there's a visible degradation
trend.

Usage:
    export TOGETHER_API_KEY="..."
    python3 perf_degradation.py --model "moonshotai/Kimi-K2.7-Code"
"""
import argparse
import json
import os
import re
import subprocess
import sys
import uuid

import requests

CHAT_URL = "https://api.together.ai/v1/chat/completions"
WORK_DIR = "perf_work"

# --- Ln problems: name -> (description, python reference implementation) ---
PROBLEMS = {
    "sort_asc": (
        "Sort the array in ascending order.",
        lambda a: sorted(a),
    ),
    "reverse": (
        "Reverse the order of the elements in the array.",
        lambda a: list(reversed(a)),
    ),
    "double_vals": (
        "Multiply every element in the array by 2.",
        lambda a: [x * 2 for x in a],
    ),
    "increment_vals": (
        "Add 1 to every element in the array.",
        lambda a: [x + 1 for x in a],
    ),
}

TEST_INPUTS = [
    [],
    [5],
    [3, 1, 2],
    [-5, 10, 0, -3, 8],
    [4, 4, 2, 2, 1],
]

METHOD_SIGNATURE = "public static int[] solve(int[] a)"

PROMPT_TEMPLATE = """Write a single Java method with exactly this signature:

{sig} {{ ... }}

The method should: {description}

Rules:
- Respond with ONLY the method (signature + body), nothing else.
- No class wrapper, no main method, no explanation, no markdown code fences.
- Do not modify the input array in a way that breaks correctness; return a new or
  mutated array as appropriate, whichever correctly implements the task.
- Assume the input array can be empty; handle that case correctly.
"""

DRIVER_TEMPLATE = """import java.util.Arrays;

public class Driver {{
{method_code}

    public static void main(String[] args) {{
        int[][] tests = {{
{test_literals}
        }};
        for (int[] t : tests) {{
            try {{
                int[] result = solve(t);
                System.out.println(Arrays.toString(result));
            }} catch (Throwable e) {{
                System.out.println("__ERROR__:" + e);
            }}
        }}
    }}
}}
"""


def compose_description(desc_a, desc_b):
    return f"First, {desc_a[0].lower()}{desc_a[1:]} Then, using that resulting array, {desc_b[0].lower()}{desc_b[1:]}"


def compose_ref(ref_a, ref_b):
    return lambda a: ref_b(ref_a(a))


def java_array_literal(arr):
    return "{" + ", ".join(str(x) for x in arr) + "}"


def build_prompt(description):
    return PROMPT_TEMPLATE.format(sig=METHOD_SIGNATURE, description=description)


def _call_model_once(prompt, model):
    api_key = os.environ.get("TOGETHER_API_KEY")
    if not api_key:
        sys.exit("TOGETHER_API_KEY not set in environment")
    resp = requests.post(
        CHAT_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 8000,
            "stream": True,
        },
        timeout=120,
        stream=True,
    )
    resp.raise_for_status()
    content = ""
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            break
        chunk = json.loads(payload)
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta", {})
        if delta.get("content"):
            content += delta["content"]
    return content


def call_model(prompt, model, retries=3):
    # Some models (observed: Kimi-K2.7-Code, Qwen3.5-9B) intermittently return an
    # empty completion even with a generous max_tokens budget -- retry rather than
    # silently recording a false FAIL.
    for attempt in range(retries):
        content = _call_model_once(prompt, model)
        if content.strip():
            return content
    return content  # last (empty) attempt, caller will record EXTRACT_FAILED


def extract_method(raw):
    # prefer a fenced code block if present
    m = re.search(r"```(?:java)?\s*\n(.*?)```", raw, re.DOTALL)
    code = m.group(1) if m else raw

    # find the method signature and brace-match to the end of its body
    idx = code.find("solve(")
    if idx == -1:
        return None
    # walk back to the start of the line containing the signature
    start = code.rfind("\n", 0, idx)
    start = 0 if start == -1 else start + 1
    brace_start = code.find("{", idx)
    if brace_start == -1:
        return None
    depth = 0
    for i in range(brace_start, len(code)):
        if code[i] == "{":
            depth += 1
        elif code[i] == "}":
            depth -= 1
            if depth == 0:
                return code[start:i + 1].strip()
    return None


def compile_and_run(method_code, tag):
    attempt_dir = os.path.join(WORK_DIR, tag)
    os.makedirs(attempt_dir, exist_ok=True)
    src_path = os.path.join(attempt_dir, "Driver.java")
    test_literals = ",\n".join(f"            {java_array_literal(t)}" for t in TEST_INPUTS)
    driver_src = DRIVER_TEMPLATE.format(method_code=method_code, test_literals=test_literals)
    with open(src_path, "w") as f:
        f.write(driver_src)

    compile_proc = subprocess.run(
        ["javac", "-d", attempt_dir, src_path],
        capture_output=True, text=True, timeout=30,
    )
    if compile_proc.returncode != 0:
        return None, f"COMPILE_ERROR: {compile_proc.stderr.strip()[:300]}"

    run_proc = subprocess.run(
        ["java", "-cp", attempt_dir, "Driver"],
        capture_output=True, text=True, timeout=15,
    )
    if run_proc.returncode != 0:
        return None, f"RUNTIME_ERROR: {run_proc.stderr.strip()[:300]}"

    lines = [ln.strip() for ln in run_proc.stdout.strip().splitlines()]
    return lines, None


def parse_java_array(s):
    s = s.strip()
    if s == "[]":
        return []
    return [int(x.strip()) for x in s.strip("[]").split(",")]


def grade(description, ref, model, tag):
    prompt = build_prompt(description)
    raw = call_model(prompt, model)
    method_code = extract_method(raw)
    if method_code is None:
        return {"pass": False, "reason": "EXTRACT_FAILED", "raw": raw[:300]}

    lines, err = compile_and_run(method_code, tag)
    if err:
        return {"pass": False, "reason": err, "method_code": method_code}

    expected = [java_array_literal(ref(t)) for t in TEST_INPUTS]
    got_norm = []
    ok = True
    for line, exp in zip(lines, expected):
        if line.startswith("__ERROR__"):
            ok = False
            got_norm.append(line)
            continue
        try:
            got = parse_java_array(line)
            exp_list = [int(x) for x in exp.strip("{}").split(",")] if exp != "{}" else []
        except Exception:
            ok = False
            got_norm.append(line)
            continue
        got_norm.append(line)
        if got != exp_list:
            ok = False

    if len(lines) != len(expected):
        ok = False

    return {
        "pass": ok,
        "reason": None if ok else "MISMATCH",
        "got": got_norm,
        "expected": [str(ref(t)) for t in TEST_INPUTS],
        "method_code": method_code,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    args = p.parse_args()
    model = args.model
    tag_base = re.sub(r"[^A-Za-z0-9]", "_", model)

    print(f"=== Ln problems: {model} ===")
    ln_results = {}
    for name, (desc, ref) in PROBLEMS.items():
        res = grade(desc, ref, model, f"{tag_base}_{name}")
        ln_results[name] = res
        print(f"  {name}: {'PASS' if res['pass'] else 'FAIL (' + str(res['reason']) + ')'}")

    passing = [n for n, r in ln_results.items() if r["pass"]]
    ln_pass_rate = len(passing) / len(PROBLEMS)
    print(f"\nLn pass rate: {len(passing)}/{len(PROBLEMS)} = {ln_pass_rate:.2f}")
    print(f"Passing: {passing}")

    print(f"\n=== Ln+1 composed problems (built only from Ln-passing pairs): {model} ===")
    ln1_results = {}
    for i in passing:
        for j in passing:
            if i == j:
                continue
            desc_i, ref_i = PROBLEMS[i]
            desc_j, ref_j = PROBLEMS[j]
            comp_desc = compose_description(desc_i, desc_j)
            comp_ref = compose_ref(ref_i, ref_j)
            tag = f"{tag_base}_{i}_then_{j}"
            res = grade(comp_desc, comp_ref, model, tag)
            ln1_results[f"{i}_then_{j}"] = res
            print(f"  {i}_then_{j}: {'PASS' if res['pass'] else 'FAIL (' + str(res['reason']) + ')'}")

    if ln1_results:
        ln1_pass = sum(1 for r in ln1_results.values() if r["pass"])
        ln1_pass_rate = ln1_pass / len(ln1_results)
        print(f"\nLn+1 pass rate: {ln1_pass}/{len(ln1_results)} = {ln1_pass_rate:.2f}")
        print(f"Degradation (Ln - Ln+1): {ln_pass_rate - ln1_pass_rate:+.2f}")
    else:
        print("\nNo Ln+1 problems could be built (model passed 0 or 1 Ln problems).")
        ln1_pass_rate = None

    out = {
        "model": model,
        "ln_results": ln_results,
        "ln_pass_rate": ln_pass_rate,
        "ln1_results": ln1_results,
        "ln1_pass_rate": ln1_pass_rate,
    }
    with open(f"perf_results_{tag_base}.json", "w") as f:
        json.dump(out, f, indent=2, default=str)


if __name__ == "__main__":
    main()
