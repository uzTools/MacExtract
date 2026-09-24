#!/usr/bin/env python3
"""m68kprof.py — per-function and per-block 68000 instruction counts from a
qemu-m68k `-d exec,nochain,in_asm` log (file or '-'). Instructions, not cycles.
Usage: m68kprof.py LOG [BINARY]   (BINARY enables addr2line on the top blocks)"""
import sys, re, collections, subprocess
src = open(sys.argv[1]) if sys.argv[1] != '-' else sys.stdin
binary = sys.argv[2] if len(sys.argv) > 2 else None
tb_len = {}; tb_func = {}
per_func = collections.Counter(); per_tb = collections.Counter(); total = 0
cur_pc = None; cur_n = 0; cur_func = None; in_block = False
trace_re = re.compile(r'^Trace \d+: 0x[0-9a-f]+ \[[0-9a-f]+/([0-9a-f]+)/[^\]]*\]\s*(\S*)')
for line in src:
    if in_block:
        if line.startswith('0x'):
            if cur_pc is None: cur_pc = int(line[2:line.index(':')], 16)
            cur_n += 1
            continue
        tb_len[cur_pc] = cur_n; tb_func[cur_pc] = cur_func
        in_block = False; cur_pc = None; cur_n = 0
        if not line.strip(): continue
    if line.startswith('IN:'):
        cur_func = line[3:].strip() or '?'; in_block = True; cur_pc = None; cur_n = 0
        continue
    m = trace_re.match(line)
    if m:
        pc = int(m.group(1), 16); n = tb_len.get(pc, 0)
        f = m.group(2) or tb_func.get(pc, '?')
        per_func[f] += n; per_tb[pc] += n; total += n
print("total %d instructions" % total)
for f, n in per_func.most_common(14):
    print("%12d %5.1f%%  %s" % (n, n * 100.0 / total, f))
if binary:
    print("--- hottest blocks")
    top = per_tb.most_common(28)
    out = subprocess.run(['m68k-linux-gnu-addr2line', '-f', '-e', binary] + ['0x%x' % pc for pc, _ in top],
                         capture_output=True, text=True).stdout.split('\n')
    for i, (pc, n) in enumerate(top):
        fn = out[2*i] if 2*i < len(out) else '?'; loc = out[2*i+1] if 2*i+1 < len(out) else '?'
        print("%11d %5.1f%%  0x%08x %3d instr/tb  %s  %s" % (n, n*100.0/total, pc, tb_len.get(pc,0), fn, loc.split('/')[-1]))
