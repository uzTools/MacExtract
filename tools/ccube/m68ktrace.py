#!/usr/bin/env python3
"""m68ktrace.py — symbolically execute a straight-line 68k region, to read
a compiled butterfly out of `objdump` output.

    m68k-linux-gnu-objdump -b binary -m m68k:68000 -D CCOD.bin > ccod.asm
    tools/ccube/m68ktrace.py ccod.asm 0x30c2 0x3400

It tracks data registers, address registers and frame locals as symbolic
strings, and knows two things about this particular code: the 32-bit
multiply helper reached through `jsr %a4@(31482)`, and the
round-toward-zero idiom `tst.l X ; bge .+6 ; addq.l #1,X`. Everything it
cannot model it counts and prints, so a trace is never silently partial
— which matters, because the first version of this quietly dropped the
`asl.l` in the output stage and the butterfly read correctly anyway.

**What it bought, on `CCOD+0x2f3c`** (FORMATS.md, *What an Optimizer did
to the fork*): the eight rotations with their constants, the butterfly
wiring, the input mapping from the de-zigzag table, the exact rounding,
and the output stage. All of it in about an hour, against a day of
reading by eye that had produced a wrong guess.

**What it did not buy:** a working decoder. The transcribed network is
still 35 % wrong against the specimen, so a scaling step somewhere
between dequantisation and the first pass — or between the passes — is
not in the region traced. Widening it is the next move.

License: LGPL-2.1-or-later. See LICENSE and NOTICE.
"""
import re, sys

LINE = re.compile(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{4}\s+)+)\s*(\S+)\s*(.*)$')

def parse(path, lo, hi):
    out=[]
    for l in open(path):
        m=LINE.match(l)
        if not m: continue
        a=int(m.group(1),16)
        if a<lo or a>hi: continue
        out.append((a, m.group(3), m.group(4).strip()))
    return out

class S(str): pass
def e(x): return S(x)

def run(ins, verbose=False):
    D={i:e('d%d?'%i) for i in range(8)}
    A={i:e('a%d?'%i) for i in range(8)}
    M={}                      # fp@(-n) -> expr
    stack=[]
    unhandled={}
    out=[]
    i=0
    def loc(op):
        m=re.search(r'%fp@\((-?\d+)\)', op)
        return int(m.group(1)) if m else None
    def rd(op):
        m=re.match(r'%d(\d)$', op)
        if m: return D[int(m.group(1))]
        m=re.match(r'%a(\d)$', op)
        if m: return A[int(m.group(1))]
        m=re.match(r'#(-?\d+)$', op)
        if m: return e(m.group(1))
        n=loc(op)
        if n is not None: return M.get(n, e('L%d'%(-n)))
        return e('?'+op)
    while i < len(ins):
        a, mn, ops = ins[i]
        # round-toward-zero idiom: tstl X ; bges .+ ; addql #1,X
        if mn.startswith('tstl') and i+2 < len(ins) and ins[i+1][1].startswith('bge') \
           and ins[i+2][1].startswith('addql') and '#1' in ins[i+2][2]:
            n=loc(ops)
            if n is not None and n in M: M[n]=e('rtz(%s)'%M[n])
            i+=3; continue
        parts=[p.strip() for p in ops.split(',')] if ops else []
        if mn.startswith('moveal') or mn.startswith('moveaw'):
            src,dst=parts; m=re.match(r'%a(\d)$',dst)
            if m: A[int(m.group(1))]=rd(src)
        elif mn.startswith('movel') or mn.startswith('movew') or mn.startswith('moveb'):
            src,dst=parts
            if dst=='%sp@-': stack.append(rd(src))
            else:
                v=rd(src); m=re.match(r'%d(\d)$',dst)
                if m: D[int(m.group(1))]=v
                else:
                    n=loc(dst)
                    if n is not None:
                        M[n]=v; out.append((a,n,v))
        elif mn.startswith('moveq'):
            src,dst=parts; m=re.match(r'%d(\d)$',dst)
            if m: D[int(m.group(1))]=e(src.lstrip('#'))
        elif mn[:4] in ('addl','addw','subl','subw') or mn[:5] in ('addql','addqw','subql','subqw'):
            src,dst=parts; op='+' if mn.startswith('add') else '-'
            v=e('(%s %s %s)'%(rd(dst),op,rd(src)))
            m=re.match(r'%d(\d)$',dst)
            if m: D[int(m.group(1))]=v
            else:
                n=loc(dst)
                if n is not None: M[n]=v; out.append((a,n,v))
        elif mn.startswith('asrl') or mn.startswith('asrw'):
            src,dst=parts; m=re.match(r'%d(\d)$',dst)
            if m: D[int(m.group(1))]=e('(%s >> %s)'%(D[int(m.group(1))], rd(src)))
        elif mn.startswith('extl') or mn.startswith('extw'):
            pass
        elif mn.startswith('jsr'):
            if '31482' in ops:
                b=stack.pop() if stack else e('?'); c=stack.pop() if stack else e('?')
                D[0]=e('MUL(%s,%s)'%(c,b))
            else:
                D[0]=e('call')
        elif mn.startswith('clrw') or mn.startswith('clrl'):
            n=loc(ops)
            if n is not None: M[n]=e('0')
        elif mn.startswith('bra') or mn.startswith('nop'):
            pass
        else:
            unhandled[mn]=unhandled.get(mn,0)+1
        i+=1
    return out, unhandled

if __name__=='__main__':
    path, lo, hi = sys.argv[1], int(sys.argv[2],16), int(sys.argv[3],16)
    out,unh = run(parse(path, lo, hi))
    for a,n,v in out:
        if len(v) < 400: print('  %05x  L%-4d = %s' % (a, -n, v))
    if unh: print('\n  unhandled mnemonics:', unh)
