#!/usr/bin/env python3
"""Turn a divasplit profiler recording (ux0:data/divasplit/prof.bin) into a
per-function profile of the game's main thread.

    python3 profview.py prof.bin eboot.bin.elf [--heavy-ms 18] [--top 25] [--stage 3]
    python3 profview.py prof.bin eboot.bin.elf --ab log.csv [--rec N]

eboot.bin.elf is the decrypted eboot of the same game version. Function
boundaries come from its unwind table (.ARM.exidx), so every sample maps to the
function it was in. Addresses are segment 0 offsets, as in the VitaGrafix
patches and the disassembly.

Reports, in ms of main thread time per frame:
  - where the time goes per render stage
  - self time per function (where the CPU was)
  - inclusive time per function (any sample with that function on the stack)
  - light vs heavy frames: which functions grow when the frame rate drops
    (with --ab: OPT off vs on windows of an A/B recording instead, matched by
    the frame column of log.csv)
"""
import argparse
import bisect
import collections
import json
import os
import struct
import sys

from thumbelf import VitaElf

PROF_MAGIC = 0x46525044
F_USER, F_REGS, F_STACK, F_SYSCALL = 1, 2, 4, 8
HEADER = struct.Struct('<16I')
SAMPLE_HEAD_V1 = struct.Struct('<IIhBBIIIIIII')   # t, frame, stage, flags, nstack, pc, lr, sp, cpsr, kpc, kcpsr, cost
SAMPLE_HEAD_V3 = struct.Struct('<IIbBBBIIIIIII')  # t, frame, stage, thread, flags, nstack, ...

# functions we already know, by module NID
KNOWN = {
    0x0A3FF027: {0x271368: 'RenderStage'},                     # X
    0x544807B3: {0x28C54E: 'RenderStage', 0x13D00: 'GetDelta'},   # f (EU)
    0xDB737975: {0x265920: 'RenderStage', 0xAE7A: 'GetDelta'},     # f 2nd (EU)
    0x1BA9AC18: {0x28C54E: 'RenderStage', 0x13D00: 'GetDelta'},   # f (US)
    0x31DAC716: {0x265920: 'RenderStage', 0xAE7A: 'GetDelta'},     # f 2nd (US)
}


class Code:
    def __init__(self, path):
        self.elf = VitaElf(path)
        e = self.elf
        entry = struct.unpack_from('<I', e.data, 0x18)[0]
        mi = e.segs[entry >> 30][1] + (entry & 0x3FFFFFFF)
        exidx_top, exidx_end = struct.unpack_from('<II', e.data, mi + 32 + 44)
        starts = set()
        for off in range(exidx_top, exidx_end, 8):
            rel = struct.unpack_from('<I', e.text, off)[0] & 0x7FFFFFFF
            if rel & 0x40000000:
                rel -= 0x80000000
            starts.add(((off + rel) & 0xFFFFFFFF) & ~1)
        self.starts = sorted(starts)
        self.names = KNOWN.get(e.module_nid, {})
        self.stubs = self._import_stubs(mi)

    def _import_stubs(self, mi):
        """seg0 offset of each import stub -> function name (nids.json, from vita-headers)."""
        e = self.elf
        nids = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nids.json')))
        def va2off(va):
            for _, off, v, fsz, _ in e.segs:
                if v <= va < v + fsz:
                    return off + va - v
        imp_top, imp_end = struct.unpack_from('<II', e.data, mi + 44)
        stubs = {}
        o = e.segs[0][1] + imp_top
        while o < e.segs[0][1] + imp_end:
            size, _, _, nf = struct.unpack_from('<HHHH', e.data, o)
            nid_tab, ent_tab = struct.unpack_from('<II', e.data, o + (0x1C if size == 0x34 else 0x14))
            for i in range(nf):
                nid = struct.unpack_from('<I', e.data, va2off(nid_tab) + 4 * i)[0]
                stub = struct.unpack_from('<I', e.data, va2off(ent_tab) + 4 * i)[0]
                stubs[stub - e.text_va] = nids.get(f'0x{nid:08X}', f'nid_{nid:08X}')
            o += size
        return stubs

    def call_target(self, ret_off):
        """Name of the import called just before a return address, or None."""
        t = self.elf.text
        hw1, hw2 = struct.unpack_from('<HH', t, ret_off - 4)
        if (hw1 & 0xF800) != 0xF000 or (hw2 & 0xC000) != 0xC000:
            return None
        sign = (hw1 >> 10) & 1
        j1, j2 = (hw2 >> 13) & 1, (hw2 >> 11) & 1
        i1, i2 = 1 - (j1 ^ sign), 1 - (j2 ^ sign)
        imm = (sign << 24) | (i1 << 23) | (i2 << 22) | ((hw1 & 0x3FF) << 12) | ((hw2 & 0x7FF) << 1)
        if sign:
            imm -= 1 << 25
        target = ret_off + imm
        if not hw2 & 0x1000:        # blx: ARM target, word aligned
            target &= ~3
        return self.stubs.get(target)

    def func(self, off):
        i = bisect.bisect_right(self.starts, off) - 1
        return self.starts[i] if i >= 0 else None

    def name(self, f):
        if isinstance(f, str):
            return f
        n = self.names.get(f)
        return f'0x{f:06X}' + (f' {n}' if n else '')

    def is_return(self, off):
        """off follows a call: bl / blx imm (32-bit) or blx reg (16-bit)."""
        t = self.elf.text
        if off < 4 or off > len(t):
            return False
        hw1, hw2 = struct.unpack_from('<HH', t, off - 4)
        if (hw1 & 0xF800) == 0xF000 and (hw2 & 0xC000) == 0xC000:
            return True
        hw = struct.unpack_from('<H', t, off - 2)[0]
        return (hw & 0xFF87) == 0x4780


def load(path):
    """Header dict and samples as (t, frame, stage, flags, nstack, pc, lr, sp, cpsr,
    kpc, kcpsr, cost, stack, thread, weight). From version 5 on, a waiting thread
    is only written when its state changes; weight is the number of sample
    periods a record stands for (1 for older files and running threads)."""
    data = open(path, 'rb').read()
    h = HEADER.unpack_from(data, 0)
    magic, version, header_size, sample_size, rate, nid, text_base, text_size, stack_words = h[:9]
    if magic != PROF_MAGIC:
        sys.exit(f'{path}: not a divasplit profiler file')
    names = ['main']
    if version >= 3:
        n = h[9]
        names = [data[64 + 32 * i:64 + 32 * (i + 1)].split(b'\0')[0].decode('latin1') for i in range(n)]
    stack = struct.Struct(f'<{stack_words}I')
    samples = []
    for off in range(header_size, len(data) - sample_size + 1, sample_size):
        if version >= 3:
            v = SAMPLE_HEAD_V3.unpack_from(data, off)
            s, thread = v[:3] + v[4:], v[3]
        else:
            s, thread = SAMPLE_HEAD_V1.unpack_from(data, off), 0
        st = stack.unpack_from(data, off + SAMPLE_HEAD_V1.size)
        samples.append(s + (st[:s[4]], thread, 1))
    if version >= 5 and samples:
        # pause period: the most common gap between pauses
        ts = sorted({x[0] for x in samples})
        gaps = sorted(b - a for a, b in zip(ts, ts[1:]) if b > a)
        period = gaps[len(gaps) // 4] if gaps else 2000
        last = {}
        for i, x in enumerate(samples):
            prev = last.get(x[13])
            if prev is not None and not samples[prev][3] & 1:
                w = max(1, round((x[0] - samples[prev][0]) / period))
                samples[prev] = samples[prev][:14] + (w,)
            last[x[13]] = i
    return dict(rate=rate, nid=nid, text_base=text_base, text_size=text_size, threads=names), samples


def ab_frames(log, rec):
    """Frames of the OPT off and on windows of an A/B recording, from log.csv's
    opt and frame columns (frame = the next window's first frame)."""
    import csv
    recs, cur = [], None
    for row in csv.reader(open(log)):
        if not row or row[0].startswith('#'):
            continue
        if row[0] == 't':
            cur = (row, [])
            recs.append(cur)
        elif cur:
            cur[1].append(dict(zip(cur[0], row)))
    recs = [r for r in recs if 'frame' in r[0]]
    if not recs:
        sys.exit(f'{log}: no recording with a frame column (needs divasplit with per-stage columns)')
    rows = recs[rec][1]
    off, on = set(), set()
    for a, b in zip(rows, rows[1:]):   # window b: frames [a.frame, b.frame)
        if a.get('frame') and b.get('frame'):
            (on if b['opt'] == '1' else off).update(range(int(a['frame']), int(b['frame'])))
    return off, on


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('prof')
    ap.add_argument('elf')
    ap.add_argument('--heavy-ms', type=float, default=18.0, help='frames longer than this are heavy (default 18)')
    ap.add_argument('--top', type=int, default=25)
    ap.add_argument('--stage', type=int, help='only samples taken in this render stage')
    ap.add_argument('--thread', default='0', help='thread to report on: index or name (default 0, the main thread)')
    ap.add_argument('--ab', metavar='LOG', help='compare OPT off / on windows of this A/B log.csv instead of light / heavy')
    ap.add_argument('--rec', type=int, default=-1, help='with --ab: which recording in log.csv (default -1, the last)')
    args = ap.parse_args()

    hdr, all_samples = load(args.prof)
    names = hdr['threads']
    thread = int(args.thread) if args.thread.isdigit() else next(
        (i for i, n in enumerate(names) if args.thread.lower() in n.lower()), None)
    if thread is None or thread >= len(names):
        sys.exit(f'no thread {args.thread}; sampled: ' + ', '.join(f'{i} {n}' for i, n in enumerate(names)))
    samples = [s for s in all_samples if s[13] == thread]
    code = Code(args.elf)
    if code.elf.module_nid != hdr['nid']:
        print(f'warning: recording is from module NID 0x{hdr["nid"]:08X}, the ELF is 0x{code.elf.module_nid:08X}')
    base, size = hdr['text_base'], hdr['text_size']
    # real time between samples: the pauses themselves stretch the nominal period
    pauses_t = sorted({x[0] for x in all_samples})
    period_ms = (pauses_t[-1] - pauses_t[0]) / 1000.0 / max(1, len(pauses_t) - 1)

    # frame lengths from the first sample of each frame
    first_t = {}
    for s in samples:
        first_t.setdefault(s[1], s[0])
    frames = sorted(first_t)
    frame_ms = {}
    for a, b in zip(frames, frames[1:]):
        if b == a + 1:
            frame_ms[a] = (first_t[b] - first_t[a]) / 1000.0
    heavy = {f for f, ms in frame_ms.items() if ms > args.heavy_ms}
    light = {f for f, ms in frame_ms.items() if ms <= args.heavy_ms}
    L1, L2, GROWTH = 'light', 'heavy', 'growth'
    if args.ab:
        off, on = ab_frames(args.ab, args.rec)
        light = {f for f in frame_ms if f in off}
        heavy = {f for f in frame_ms if f in on}
        L1, L2, GROWTH = 'off', 'on', 'on-off'

    def where(s):
        t, frame, stage, flags, n, pc, lr, sp, cpsr, kpc, kcpsr, cost, stack, _, _ = s
        if not flags & F_REGS:
            return '[no registers]', [], 'wait'
        rets = []
        for r in ((lr,) if flags & F_USER else ()) + stack:
            off = (r & ~1) - base
            if 0 <= off < size and r & 1 and code.is_return(off):
                rets.append(code.func(off))
        if flags & F_SYSCALL:       # v2: user registers saved on entry to the kernel
            for r in ((lr,) + stack):
                roff = (r & ~1) - base
                if 0 <= roff < size and r & 1 and code.is_return(roff):
                    name = code.call_target(roff)
                    return f'[kernel] {name}' if name else '[kernel] (via function pointer)', rets, 'wait'
            return '[kernel] (caller unknown)', rets, 'wait'
        if not flags & F_USER:
            return '[waiting / in the kernel]', rets, 'wait'
        off = pc - base
        if 0 <= off < size:
            return code.func(off), rets, 'game'
        # in a system library: name the import the innermost eboot frame called
        for r in ((lr,) + stack):
            roff = (r & ~1) - base
            if 0 <= roff < size and r & 1 and code.is_return(roff):
                name = code.call_target(roff)
                return f'[lib] {name}' if name else '[lib] (via function pointer)', rets, 'lib'
        return '[lib] (caller unknown)', rets, 'lib'
        

    groups = {'all': None, 'light': light, 'heavy': heavy}
    nframes = {'all': len(frame_ms), 'light': len(light), 'heavy': len(heavy)}
    self_c = {g: collections.Counter() for g in groups}
    incl_c = {g: collections.Counter() for g in groups}
    stage_c = {g: collections.Counter() for g in groups}
    kind_c = {g: collections.Counter() for g in groups}
    lib_callers = collections.Counter()
    pauses = []
    for s in samples:
        frame, stage = s[1], s[2]
        if frame not in frame_ms:
            continue
        if args.stage is not None and stage != args.stage:
            continue
        self_f, rets, kind = where(s)
        w = s[14]
        if kind == 'lib' and rets:
            lib_callers[rets[0]] += w
        # inclusive = CPU time only; waits have their own table
        incl = set(rets) if kind != 'wait' else set()
        if not isinstance(self_f, str):
            incl.add(self_f)
        for g, fs in groups.items():
            if fs is not None and frame not in fs:
                continue
            self_c[g][self_f] += w
            stage_c[g][stage] += w
            kind_c[g][(stage, kind)] += w
            for f in incl:
                incl_c[g][f] += w

    def ms(g, n):
        return n * period_ms / nframes[g] if nframes[g] else 0.0

    total = sum(stage_c['all'].values())
    avg = lambda fs: sum(frame_ms[f] for f in fs) / len(fs) if fs else 0
    if len(names) > 1:
        print('sampled threads, ms per frame (cpu = running in the game or a library, kernel = waiting or in a system call):')
        for i, n in enumerate(names):
            ts = [x for x in all_samples if x[13] == i and x[1] in frame_ms]
            cpu = sum(x[14] for x in ts if x[3] & F_USER) * period_ms / len(frame_ms)
            ker = sum(x[14] for x in ts if not x[3] & F_USER) * period_ms / len(frame_ms)
            print(f'  {i} {n:34s} cpu {cpu:5.2f}  kernel {ker:5.2f}')
        print(f'reporting on thread {thread} ({names[thread]})\n')
    print(f'{len(samples)} samples, one per {period_ms:.2f} ms (nominal {hdr["rate"]} Hz), {total} in complete frames'
          + (f' of stage {args.stage}' if args.stage is not None else ''))
    if args.ab:
        print(f'frames: {len(frame_ms)}, OPT off {len(light)} (avg {avg(light):.1f} ms), '
              f'OPT on {len(heavy)} (avg {avg(heavy):.1f} ms)')
    else:
        print(f'frames: {len(frame_ms)}, light {len(light)} (avg {avg(light):.1f} ms), '
              f'heavy > {args.heavy_ms:g} ms {len(heavy)} (avg {avg(heavy):.1f} ms)')
    pauses = [x[11] for x in all_samples if x[13] == 0]
    if pauses:
        print(f'profiler pause per sample: avg {sum(pauses) / len(pauses):.0f} us, max {max(pauses)} us')

    print('\nmain thread ms per frame by render stage (-1 = outside RenderStage: update, swap)')
    print('  game = eboot code, lib = system libraries (GPU API, libc), wait = blocked or in the kernel')
    print(f'  {"stage":>6} | {L1 + " game":>10} {"lib":>5} {"wait":>5} | {L2 + " game":>10} {"lib":>5} {"wait":>5} |'
          f' {GROWTH + " game+lib":>15}')
    for st in sorted(stage_c['all']):
        v = {(g, k): ms(g, kind_c[g][(st, k)]) for g in ('light', 'heavy') for k in ('game', 'lib', 'wait')}
        if sum(v.values()) < 0.05:
            continue
        growth = v['heavy', 'game'] + v['heavy', 'lib'] - v['light', 'game'] - v['light', 'lib']
        print(f'  {st:>6} | {v["light", "game"]:10.2f} {v["light", "lib"]:5.2f} {v["light", "wait"]:5.2f} |'
              f' {v["heavy", "game"]:10.2f} {v["heavy", "lib"]:5.2f} {v["heavy", "wait"]:5.2f} | {growth:+15.2f}')

    def table(title, counters, key=None):
        print(f'\n{title}')
        print(f'  {L1:>7} {L2:>7} {GROWTH:>7}  function')
        rows = []
        for f in counters['all']:
            lt, hv = ms('light', counters['light'][f]), ms('heavy', counters['heavy'][f])
            rows.append((lt, hv, f))
        rows.sort(key=key or (lambda r: -(r[0] * len(light) + r[1] * len(heavy))))
        for lt, hv, f in rows[:args.top]:
            print(f'  {lt:7.2f} {hv:7.2f} {hv - lt:+7.2f}  {code.name(f)}')

    waits = {g: collections.Counter({k: v for k, v in c.items() if isinstance(k, str)
                                     and (k.startswith('[kernel]') or k.startswith('[waiting'))})
             for g, c in self_c.items()}
    if any(waits['all'].values()):
        table('time in the kernel (ms per frame), by the system call the game made', waits)
    table('self time (ms per frame): where the CPU was', self_c)
    table('inclusive CPU time (ms per frame): function on the stack', incl_c)
    table(f'{GROWTH} (inclusive, ms per frame), largest increase first', incl_c, key=lambda r: -(r[1] - r[0]))
    table(f'{GROWTH} (inclusive, ms per frame), largest decrease first', incl_c, key=lambda r: r[1] - r[0])
    if lib_callers:
        print('\nsystem library time, by the eboot function that called it (samples)')
        for f, n in lib_callers.most_common(10):
            print(f'  {n:7d}  {code.name(f)}')


if __name__ == '__main__':
    main()
