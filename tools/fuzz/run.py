#!/usr/bin/env python3
"""run.py — run each decoder harness for a fixed time and report.

    tools/fuzz/run.py [--seconds 600] [--jobs 2] [TARGET ...]

For each target: the seeds tools/fuzz/make_seeds.py wrote, a working
corpus under .tmp/fuzz/corpus/<target> kept between runs, and libFuzzer
for --seconds. Prints per target the edges covered (libFuzzer's `cov`),
features (`ft`), corpus size, executions, and the crash file if it
stopped on one. A crash input is kept in .tmp/fuzz/crashes/; its minimal
form and a unit test are the next step, by hand (TESTING.md, *Fuzzing
each decoder on its own*).
"""
import argparse
import concurrent.futures
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
TMP = os.path.join(REPO, ".tmp", "fuzz")

# target -> the seed directories it starts from
TARGETS = {
    "sit": ["sit", "sit13", "sit14", "arsenic"],
    "sit13": ["sit13"], "sit14": ["sit14"], "arsenic": ["arsenic"],
    "dd": ["dd", "ddn"], "ddn": ["ddn"],
    "lzh_static": ["lzh_static"], "lzh_dyn": ["lzh_dyn"],
    "now": ["now"], "spacesaver": ["spacesaver"], "superdisk": ["superdisk"],
    "implode": ["implode"], "shrink": ["shrink"], "reduce": ["reduce"],
}


def one(target, seconds, build):
    binary = os.path.join(build, "fz_" + target)
    corpus = os.path.join(TMP, "corpus", target)
    crashes = os.path.join(TMP, "crashes")
    os.makedirs(corpus, exist_ok=True)
    os.makedirs(crashes, exist_ok=True)
    seeds = [os.path.join(TMP, "seeds", s) for s in TARGETS[target]]
    seeds = [s for s in seeds if os.path.isdir(s)]
    log = os.path.join(TMP, "log-%s.txt" % target)
    cmd = [binary, corpus] + seeds + [
        "-max_total_time=%d" % seconds, "-timeout=20", "-rss_limit_mb=2560",
        "-max_len=262144", "-print_final_stats=1",
        "-artifact_prefix=%s/%s-" % (crashes, target)]
    with open(log, "w") as f:
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    text = open(log, errors="replace").read()
    cov = re.findall(r"cov: (\d+) ft: (\d+) corp: (\d+)/", text)
    execs = re.search(r"stat::number_of_executed_units: (\d+)", text)
    crash = re.findall(r"Test unit written to (\S+)", text)
    return {
        "target": target, "rc": r.returncode,
        "cov": cov[-1][0] if cov else "?", "ft": cov[-1][1] if cov else "?",
        "corpus": cov[-1][2] if cov else "?",
        "execs": execs.group(1) if execs else "?",
        "crash": crash[-1] if crash else "",
        "seeds": sum(len(os.listdir(s)) for s in seeds),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=600)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--build", default=os.path.join(REPO, "build", "fuzz"))
    ap.add_argument("targets", nargs="*")
    a = ap.parse_args()
    targets = a.targets or list(TARGETS)
    for t in targets:
        if t not in TARGETS:
            raise SystemExit("run: no target %s" % t)
    print("%-11s %6s %6s %6s %6s %10s  %s" % ("target", "seeds", "cov", "ft",
                                             "corpus", "execs", "crash"))
    with concurrent.futures.ThreadPoolExecutor(a.jobs) as ex:
        for r in ex.map(lambda t: one(t, a.seconds, a.build), targets):
            print("%-11s %6s %6s %6s %6s %10s  %s" % (
                r["target"], r["seeds"], r["cov"], r["ft"], r["corpus"],
                r["execs"], r["crash"] or ("-" if r["rc"] == 0
                                           else "rc %d" % r["rc"])),
                flush=True)


if __name__ == "__main__":
    main()
