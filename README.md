# divasplit

Frame pacing and performance plugin for **Hatsune Miku: Project DIVA X, f and f 2nd** on PS Vita, made to go with the 60 fps VitaGrafix patches.

| Game | Title ID | Version |
|---|---|---|
| Project DIVA X | PCSB01007 / PCSE00867 | EU / US 1.00 |
| Project DIVA f | PCSB00419 / PCSE00326 | EU / US 1.00 |
| Project DIVA f 2nd | PCSB00554 / PCSE00434 | EU / US 1.00 |

In any other game or version the plugin stays idle.

> **Help wanted: which PVs drop below 60 fps for you?** Post them in [issue #1](https://github.com/xpuska513/divasplit/issues/1): the game, the PV and where in the song it drops. No logs needed. The heaviest PVs are what the next optimizations will target.

## What it does

- **AVS (adaptive vsync).** The games wait for the next screen refresh after every frame. A frame that takes even slightly longer than 16.7 ms then waits for the refresh after that, so a small slowdown becomes a drop straight from 60 to 30 fps. AVS skips that wait only when the frame is already late. A 17 ms frame stays 17 ms (about 58 fps instead of 30). It never goes above 60 fps, and frames are still flipped on vblank, so there is no tearing.
- **SYNC (frame-drop catch-up).** The engines have a built-in mode that scales game time by target/measured fps, so notes and animation keep real-time speed when the frame rate drops. The games never turn it on; this plugin can.
- **Engine optimizations (OPT, f and f 2nd).** Faster versions of the game's hottest per-frame work that give the same output: reusing 2D uniform data that hasn't changed, a cheaper sort-key calculation, fewer copies and calls per draw. On f 2nd's heaviest PV they save **4 ms of CPU per frame on stock clocks** and 1.6 ms overclocked; in f, +2 to +3 fps in heavy PVs. See [Engine optimizations](#engine-optimizations-opt).
- **Dynamic resolution and sharpening (f and f 2nd).** The 3D world's resolution follows the GPU load: full while the GPU keeps up, lower only while a heavy PV would drop, with the lowered image sharpened (contrast-adaptive, after AMD's CAS). On stock clocks f 2nd's heaviest PV goes from 47.6 to 57 fps; overclocked it holds 60, rendering above the game's own resolution in light moments. Off by default. See [Dynamic resolution and sharpening](#dynamic-resolution-and-sharpening-f-and-f-2nd).
- **Split render presets.** Redraw the 3D world (PV) less often while notes and UI still redraw every frame. This trades PV smoothness for CPU and GPU time.
- **Status bar** with fps and a per-frame timing breakdown: CPU work, waiting on the GPU, waiting for vblank, and 3D submit time.
- **Recording.** One line per second goes to `ux0:data/divasplit/log.csv`.
- **Thread view** (while recording). It shows how much of the time the main thread is running, ready but waiting for its core, or waiting on something, what it waits on, how busy each CPU core is with game threads, and each game thread's CPU time. It goes to `ux0:data/divasplit/threads.csv` and a second status bar line.
- **Settings per game**, remembered across launches and changeable from the **Quick Menu** (hold PS).
- **Development tools** (optional): a sampling profiler and a tracer that turn a recording into a per-thread timeline you can open in [Perfetto](https://ui.perfetto.dev). See [Development tools](#development-tools).

## Install

You need taiHEN (HENkaku / Ensō) and VitaShell.

### With the installer (easiest)

1. Install `divasplit_installer.vpk` with VitaShell.
2. Open **divasplit installer**. It shows what's installed and what's out of date.
3. Press X. It reboots when done.

It installs or updates:
- `ur0:tai/divasplit.suprx`
- the plugin lines in the taiHEN config (`ux0:tai/config.txt` if you have one, else `ur0:tai/config.txt`), fixing wrong paths
- the Quick Menu plugin, if QuickMenuReborn is installed
- the 60 fps blocks in VitaGrafix's `patchlist.txt` and `FPS=60` in its `config.txt`, if VitaGrafix is installed

Every file it edits is backed up to `<file>.bak` first. TRIANGLE uninstalls the plugin and leaves the VitaGrafix patches in place. SQUARE installs or removes the profiler kernel plugin (see [Development tools](#development-tools)).

Files you put in `ux0:data/divasplit/install/` (for example a test build of `divasplit.suprx`) are used instead of the bundled ones, then deleted. The installer remembers such a test build and never replaces it with the older copy inside the VPK; it shows as "test build (kept)".

### By hand

1. Copy `divasplit.suprx` to `ur0:tai/`.
2. In `ur0:tai/config.txt`, add a section for each game you have:
   - EU releases
   ```
   *PCSB01007
   ur0:tai/divasplit.suprx
   *PCSB00419
   ur0:tai/divasplit.suprx
   *PCSB00554
   ur0:tai/divasplit.suprx
   ```
   - US releases
   ```
   *PCSE00326
   ur0:tai/divasplit.suprx
   *PCSE00434
   ur0:tai/divasplit.suprx
   *PCSE00867
   ur0:tai/divasplit.suprx
   ```
3. Reboot.

### Quick Menu toggles (optional)

This needs [QuickMenuReborn](https://github.com/Ibrahim778/QuickMenuReborn/releases) v2.5.

1. Copy `QuickMenuReborn.suprx` to `ur0:tai/` and add it under `*main` in `config.txt`.
2. Copy `qmr_plugin.rco` (from the QuickMenuReborn release) to **`ur0:QuickMenuReborn/`**. Version 2.5 always loads it from `ur0:`, even if you keep its plugins on `ux0:`.
3. Copy `divasplit_qm.suprx` to `ux0:QuickMenuReborn/` (or `ur0:QuickMenuReborn/` if there is no `ux0:` folder).
4. Reboot.

Holding PS shows a *divasplit* section with these toggles:

- AVS
- SYNC
- Engine optimizations (OPT, f and f 2nd)
- Dynamic resolution (f and f 2nd)
- Sharpen 3D image (f and f 2nd)
- Status bar
- Recording
- 3D preset button
- Sharpening style button: adaptive or classic

They apply to the DIVA game that started last, and take effect in the running game within half a second.

## Controls in game

Hold **L + R**, then press:

| Button | Action |
|---|---|
| RIGHT | next 3D preset |
| LEFT | AVS on / off |
| UP | SYNC on / off |
| DOWN | recording + thread view on / off (in X, also shows the game's own profiler) |
| SELECT | engine optimizations (OPT): off → on → A/B → off |

**OPT** switches the [engine optimizations](#engine-optimizations-opt) (f 2nd only; on by default there). **A/B** switches them every second while recording; the `opt` column of `log.csv` says which way each second ran, so one recording compares both on nearly the same scenes. When you're not recording, A/B acts like on.

## Presets

| Preset | Effect |
|---|---|
| OFF | normal game |
| 3D 1/2 | 3D world drawn every 2nd frame |
| 3D+FX 1/2 | also the extra off-screen pass |
| ALL3D 1/2 | also the 3D setup / clear stage |
| 3D 1/3 | 3D world drawn every 3rd frame |
| NO 3D test | 3D world never redrawn. Diagnostic only: shows the fps with zero 3D drawing. |

## Reading the status bar

```
SPLIT OFF  SYNC OFF  AVS ON  58fps cpu 13.9 gpu 0.4 vs 2.4 3d 5.6
```

All numbers are milliseconds per frame, averaged over one second. `REC` (or `REC+PROF` with the profiler running) shows while recording, `OPT` / `OPT A/B` when the optimizations are on. With dynamic resolution on, `res` at the end is the 3D world's width.

| Field | Meaning |
|---|---|
| cpu | the game's main thread is working |
| gpu | blocked waiting for the GPU (`sceGxmBeginScene` / `EndScene` / `DisplayQueueAddEntry`) |
| vs | waiting for vblank |
| 3d | CPU time to submit the 3D world |

`cpu + gpu + vs` equals the frame time. When fps drops:

- **gpu grows:** the GPU is the bottleneck.
- **cpu grows:** the CPU is. In practice, X is mostly GPU-bound. f 2nd is CPU-bound without OPT; with OPT and AVS its heaviest PVs become GPU-bound.

While recording, a second line shows the thread view:

```
main run 78 rdy 1 wait 21  cores 80 35 - 4  wait <object name> 12
```

| Field | Meaning |
|---|---|
| run | % of the time the main thread is running |
| rdy | % it could run, but another thread has its core |
| wait | % it waits on something (vblank, GPU, another thread) |
| cores | % of the time a game thread runs on core 0, 1, 2, 3. `-` is the core the sampler itself runs on, which it can't see. |
| wait *name* | the object the main thread waits on most, and how often |

A sampler thread checks the game about 1000 times a second, only while recording. It stays on one core. When it briefly pushes the main thread off that core, that sample is left out.

## Recommended setup

**AVS on, OPT on, and in f and f 2nd dynamic resolution on, with the CPU and GPU overclocked** (e.g. with PSVshell). This gave the best experience in testing: f 2nd's heaviest PV at 59.6 fps on average. AVS removes the 60 → 30 drops, OPT cuts the main thread's work, the overclock covers most of the remaining dips, and dynamic resolution the rest. Overclocked, set `drs_max=960` in `opt.txt` so light moments render sharper than the game's own resolution (f stops at 896).

Without an overclock, dynamic resolution matters most in f 2nd: with OPT on, its heavy PVs are limited by the GPU. f is mostly limited by the CPU; dynamic resolution covers its GPU-heavy moments.

If a PV still drops a lot:
- **A split preset** frees CPU and GPU time, but the PV redraws less smoothly. 3D 1/2 + AVS held f 2nd's heaviest PV at 59.7 fps on average.
- **SYNC on** keeps game speed exact during dips. The trade-off is a small stutter.

## VitaGrafix 60 fps patch

The 60 fps patches for the EU releases (and X US) are in [`vitagrafix/`](vitagrafix). They are also submitted upstream as [VitaGrafixPatchlist PR #162](https://github.com/Electry/VitaGrafixPatchlist/pull/162).

Until that PR is merged, install them yourself:
1. In `ux0:data/VitaGrafix/patchlist.txt`, replace the game's existing block with the one from `vitagrafix/`.
2. Set `FPS=60` for that title in `ux0:data/VitaGrafix/config.txt`.

They include an input fix that matters with or without this plugin.

The games only accept a controller sample newer than the last one they used. At 60 fps there is about one sample per frame, so sometimes a frame gets none. The game then reads every button as released, which breaks hold notes and causes double presses. The fix makes the game always use the newest sample.

| Game | Patch lines |
|---|---|
| X | `0x283352` / `0x28335A` |
| f | `0x12E24` / `0x12E28` |
| f 2nd | `0x2896F6` / `0x2896FE` |

## Other releases (US / JP / ASIA)

Only the EU and US releases are supported so far, because every release puts the code at different addresses. `tools/port.py` ports both the 60 fps patch and the plugin addresses to another release of X, f or f 2nd. It finds each EU patch site by the code around it.

1. Dump the decrypted `eboot.bin` of **your own copy** (e.g. with FAGDec) and copy it to a PC.
2. Run the script:
   ```
   pip install capstone
   python3 tools/port.py eboot.bin.elf --title PCSE00434
   ```
3. Use what it prints:
   - The `@FPS` block goes into that title's block in `ux0:data/VitaGrafix/patchlist.txt`. Keep its existing `@IB` lines and replace any old `@FPS` lines.
   - The `GAMES[]` line goes into `src/main.c`.

The script lists any site it couldn't find for certain instead of guessing. A ported patch still needs a test run in game before sharing. If it works, please open an issue or PR with the output. Never share the eboot itself.

`tools/mkpatterns.py` rebuilds `tools/patterns.json` from the EU dumps (maintainer use).

## Files

| Path | Contents |
|---|---|
| `ux0:data/divasplit/settings.txt` | settings per game |
| `ux0:data/divasplit/opt.txt` | optional: which [engine optimizations](#engine-optimizations-opt) OPT switches, dynamic resolution's range, sharpening strength and threshold |
| `ux0:data/divasplit/shaders/` | optional: the sharpening shaders compiled by the installer (the plugin has the same ones built in) |
| `ux0:data/divasplit/log.csv` | recordings (each run starts with a header line) |
| `ux0:data/divasplit/threads.csv` | thread view, one block per second: `M` main thread state, `C` per core, `T` per thread (CPU % of one core), `W` what the main thread waits on |
| `ux0:data/divasplit/diag.txt` | load diagnostics for the current session |
| `ux0:data/divasplit/prof.bin`, `prof.txt` | profiler samples and stats of the last recording |
| `ux0:data/divasplit/trace.bin` | tracer records of the last recording |
| `ux0:data/divasplit/prof.on`, `trace.on` | create these (empty) to run the profiler / tracer while recording |
| `ux0:data/divasplit/install/` | test builds for the installer |

## Development tools

These are for finding out where the games spend their time. They're not needed to play.

**Profiler.** `divasplit_prof.skprx` is a small kernel plugin, installed with the installer's SQUARE (it goes under `*KERNEL`). At boot it only looks up two functions. While you record, and only if `ux0:data/divasplit/prof.on` exists, divasplit asks it to sample the game: about 500 times a second it pauses the game for ~0.25 ms, reads the registers and the stack return addresses of every game thread divasplit knows (up to 32), and resumes. A thread that is just waiting is written once, not every time. Samples go to `prof.bin`.

**Tracer.** With the profiler installed, divasplit also hooks the game's blocking calls at start (lock / condition / semaphore waits, sleeps, thread joins, the task system's locks, file reads, audio output, GPU and vblank waits). While you record, and only if `ux0:data/divasplit/trace.on` exists, every call that blocks for 20 µs or more goes to `trace.bin` with its thread, duration, object and caller, plus exact frame and render stage boundaries. Tracing is expensive (it pushed f 2nd to 30 fps), so use it to see who waits on whom, not for timings.

**On a PC** (`pip install capstone`, and the decrypted eboot of the same game):

```
python3 tools/profview.py prof.bin eboot.bin.elf [--stage 3] [--thread 0] [--ab log.csv]
python3 tools/perfetto.py prof.bin trace.bin eboot.bin.elf -o timeline.json --from 48 --to 53
python3 tools/abcompare.py log.csv [--cols fps,cpu,st3,st5]
```

- `profview.py`: milliseconds per frame by render stage, per function (self and with callees), for normal vs slow frames, and the system calls the game waited in. Functions come from the eboot's unwind table, so every sample maps to the function it was in.
- `perfetto.py`: a timeline for [ui.perfetto.dev](https://ui.perfetto.dev): frames and render stages on top, then per thread a flame chart of what it ran and a row of its blocking calls. Keep the window to a few seconds; a whole song is a large file.
- `abcompare.py`: an OPT A/B recording, each second compared with its neighbours in the other state, with an error bar. `log.csv` also has each render stage's CPU time (`st0`..`st7`).
- `profview.py --ab log.csv`: the same profile split into the OPT off and on seconds of an A/B recording.

Profiler times for code in the plugin itself can be misattributed: its stack scan sometimes picks up stale return addresses. Count samples by address range when it matters.

## Engine optimizations (OPT)

f 2nd EU 1.00, and the ones marked *f* for f EU 1.00 too (the two engines are close relatives; X has none). Each one replaces a piece of the game's per-frame work with a faster version that gives the same result. That was checked against the game's own code on a PC and with self-checks on the console. They were found with the profiler and measured with A/B recordings.

| Key in `opt.txt` | Games | What it does |
|---|---|---|
| `ureuse` | f 2nd, f | 2D draws (notes, UI, lyrics) upload a 4.9 KB block of shader constants each, and almost all of them are identical to the previous one. The engine already marks every change to that data, so when nothing changed the draw points at the block uploaded last time instead of copying it again. Cuts the notes/UI stage in half. |
| `centre` | f 2nd | The 3D sort keys average each character's position over all its bones with two matrix products per bone. Summing the bones first needs only two products in total. |
| `dirty` | f 2nd, f | Every draw clears 224 change flags one byte at a time; one `memset` instead. |
| `lsort` | f 2nd, f | Sorting the draw lists allocates and frees 27 list heads from a locked heap every call; a merge sort that needs no allocation, with the same order. |
| `matdup` | f 2nd, f | Per draw, ten tiny getter calls copy material colours, and a matrix product is computed twice; plain copies instead. |
| `palette` | f 2nd | Bone matrices go to the shader constants with three function calls per bone; plain copies instead. |
| `texwrap` | f 2nd | Texture wrap modes go through a three-level generic dispatch; the same writes, directly. |
| `keyset` | f 2nd | The character threads' animation curve evaluation, with its inner calls inlined (same instructions, same results). |
| `h2f` | f 2nd | Half → float conversion without its stack-guard overhead (checked for all 65,536 inputs at start). |
| `nolog` | f 2nd, f | The PV script player formats a debug line for every command into a buffer nothing reads; skipped. |
| `alloc` | f | Every frame, f allocates and frees thousands of 12-byte draw-list nodes and a few hundred 224-byte sprite nodes from the C++ heap, with a lock each; the main thread's ones come from two preallocated pools instead. |

All are on by default. `ux0:data/divasplit/opt.txt` can switch single ones (`1` on, `0` off, `2` = on and the only one OPT A/B compares). It is re-read every 2 seconds; `h2f` and `nolog` only at game start. `check=1` makes `ureuse` and `centre` compare every result with the game's own (slow, for testing). `nosort0=1` skips sorting the opaque 3D list (changes draw order, off by default).

**Measured** on f 2nd's heaviest PV, OPT A/B, about 200 paired seconds each:

| Clocks | AVS | fps, OPT off → on | Main-thread CPU per frame, off → on |
|---|---|---|---|
| overclocked | off | 51.3 → **55.9** | 14.9 → 13.3 ms |
| overclocked | on | 56.1 → **57.0** | 16.7 → 14.1 ms |
| stock | off | 29.9 → **33.5** | 21.6 → 17.6 ms |
| stock | on | 44.0 → **47.1** | 21.2 → 17.0 ms |

- Overclocked with AVS off, the worst 10% of seconds went from 31.4 to 49.9 fps.
- With AVS on, the time saved partly turns into waiting for the GPU: with OPT on, the GPU is what limits the heaviest PVs.
- Without AVS, a frame that still takes more than 16.7 ms drops to 30 fps, which is why stock clocks with AVS off gain the least.

**Measured in f**, OPT A/B with AVS on, about 200 paired seconds each:

| PV | fps, OPT off → on | Main-thread CPU per frame, off → on |
|---|---|---|
| DYE | 52.7 → **55.8** | 17.9 → 16.7 ms |
| Fire Flower | 54.3 → **56.3** | 16.5 → 14.2 ms |

The `alloc` pools alone, in DYE: +0.6 fps (±0.4).

## Dynamic resolution and sharpening (f and f 2nd)

Both games draw their 3D world below the screen's resolution and stretch it to the screen: f 2nd at 720×408, f at 640×352 (the notes and UI at the screen's 960×544). With OPT on, f 2nd's heavy PVs are limited by the GPU, and a lower 3D resolution is what frees the most GPU time: Kagerou Days on stock clocks goes from 47.6 fps at 720×408 to 59.5 at 480×272. f is mostly limited by the CPU, with GPU-heavy moments.

- **Dynamic resolution** picks the 3D resolution every frame. The games allocate their 3D buffers once (f 2nd 1024×544, f 1024×512) and only use the resolution as a viewport size, so changing it costs nothing. When frames are late and the main thread waits for the GPU clearly longer than it does when the GPU keeps up (each game has its own floor of driver work: about 1 ms a frame in f), it steps down (more at once when the GPU is far behind). After a second with the GPU not waiting, it steps up again. A step up that has to be undone makes it wait longer before trying again, so it doesn't bounce. In f 2nd menus are left alone; f has no PV flag, so it works there too.
- **Sharpening** runs when the 3D image is narrower than 640 (both games: only when dynamic resolution lowered it): a small extra GPU pass over the image at its own resolution, just before the game stretches it. The default style, *adaptive*, follows AMD's CAS (contrast-adaptive sharpening): it sharpens soft detail and holds back on edges that already have contrast, so stair-steps don't get crunchy. *Classic* is an unsharp mask clamped to the neighbouring pixels. The lower the resolution, the stronger it gets (×1.1 at 480 wide). About 1.7 ms of GPU time at 480×272 on stock clocks.
- **Valid regions** (OPT `region`): the game's 3D, tonemap and background passes are told the size of their image, so the GPU skips the unused part of the buffers. A small gain (about +0.5 fps at 720×408).

Dynamic resolution and sharpening are switches in the Quick Menu (per game), plus a button for the sharpening style. Dynamic resolution is off by default, sharpening on (it does nothing at the normal resolution). Settings in `opt.txt`:

- `drs_min=0 drs_max=0`: the range of widths, 0 for the game's own (f 2nd 480–720, f 448–640). Heights keep the game's shape. `drs_max` goes up to 960 in f 2nd and 896 in f.
- `sharpness=75` (0–100) and `sharpen_below=640` (0 for the game's own).

**Measured** on f 2nd's heaviest PV (Kagerou Days), AVS and OPT on:

| Clocks | 3D resolution | fps | worst 10% of seconds | 3D width |
|---|---|---|---|---|
| stock | fixed 720×408 (the game's) | 47.6 | 39.6 | 720 |
| stock | dynamic, 480–720 | **57.1** | 52.4 | about 480 |
| overclocked | dynamic, 480–960 | **59.6** | 59.8 | 480–960, average 576 |

A lighter PV, overclocked and dynamic: 59.8 fps at an average width of 670. In f, dynamic resolution is not measured with an A/B yet.

Tried and dropped: AMD's RCAS on the full-screen stretch (12 ms of GPU time a frame on stock clocks), two adaptive passes (looked "deep fried"), and FXAA before the sharpening (it looked good, but cost 8 fps in a heavy PV at 480 on stock clocks; the game's 3D is already 4× MSAA).

The shaders are built into the plugin. The installer also compiles them on the Vita when the system's shader compiler is there (`ur0:data/libshacccg.suprx`, extracted with ShaRKF00D); compiled copies in `ux0:data/divasplit/shaders/` take priority. You don't need the compiler.

## What we measured

Project DIVA f 2nd's heaviest PV, EU 1.00, profiled on the Vita. Times are the main thread's, in milliseconds per frame, without OPT.

- **The main thread is the bottleneck.** In normal frames it works about 12 ms: game update ~3, the 3D world (render stage 3) ~5.5, 2D notes and UI ~2.5, post effects ~0.6. In slow frames only the 3D world grows (+1.8 ms); everything else stays the same.
- **The other cores are mostly idle.** All game threads together use about 1.3 of the 3 cores games get.
- **The main thread waits for its workers twice a frame.** It hands the frame's task list to three `diva_task_disp` workers and waits ~1.85 ms for them, then waits ~1 ms for the character threads (`RobThread`). The task workers use per-thread render contexts, and the engine only has three, the first being the main thread's own, so the main thread can't simply join in as a fourth worker.
- **The 3D world's cost is per draw call**, spread over hundreds of small functions. The single biggest item is copying each draw's shader constants (about 850 copies, 850 KB a frame) into uncached GPU memory: ~1.5 ms. Copying costs per byte there, so only not copying helps (`ureuse`).

Experiments that did **not** help (measured with A/B recordings):

| Experiment | Result |
|---|---|
| NEON version of the game's 4×4 matrix multiply (bit-identical) | slower: 1.26 ms against 0.8. The function is tiny and called thousands of times a frame; NEON loads of data the game just wrote with scalar stores stall. Kept in the code, off. |
| Reuse identical uniform blocks by comparing their data | slower by ~0.8 ms: comparing costs about as much as writing. `ureuse` avoids the comparison by reading the engine's own change marks. Kept in the code, off. |
| Faster (aligned NEON) copies for the uniform uploads | no gain: the copies are limited by the GPU memory they write to. Removed. |
| Kicking the character threads earlier in the frame | its safety condition never held during play. Removed. |
| Main thread alone on its own core | slightly slower; it only waited for a free core ~2.5% of the frame |
| Main thread as a fourth task worker | not possible without a fourth render context (see above) |

With OPT on, what is left on f 2nd's main thread is mostly waiting for the worker threads, and the per-draw work of the 3D world. Details, addresses and the reverse-engineering notes are in [`docs/engine-notes.md`](docs/engine-notes.md).

## How it works

These are the engine notes (EU 1.00 offsets in seg0) behind the plugin.

- **Render stages.** Every frame, the engine calls `RenderStage(stage)` in a loop.
  - **X and f 2nd** have 8 stages, with the same layout in both games. RenderStage is at `0x271368` in X and `0x265920` in f 2nd.
    - 0: setup / clear
    - 2: extra pass
    - 3: 3D world
    - 4: post effects + composite
    - 5: 2D layers (notes, UI)
  - **f** has 14 stages, with RenderStage at `0x28C54E`.
    - 5: setup
    - 7: extra pass
    - 8: 3D world
    - 10: post effects
    - 11 / 12: 2D layers
  - The plugin hooks RenderStage by offset and skips stages according to the preset.
- **Frame manager.**
  - `GetDelta()` returns `step × max(1, target/measured)` when the catch-up flag is set.
  - Every frame, the game copies a "requested" byte into that flag:

    | Game | Requested byte → flag | Frame manager |
    |---|---|---|
    | X | `fm+0x2D` → `+0x2C` | pointer at `0x814F756C` |
    | f | `fm+0xEC` → `+0x18` | `0x816E7228` |
    | f 2nd | `fm+0xDC` → `+0x18` | `0x81787B18` |

  - SYNC writes the requested byte.
- **Vblank.** The main loop calls `sceDisplayWaitVblankStartMulti(vblank)` on the main thread.
  - AVS hooks that import and skips the wait when `vcount - vcount_at_last_frame >= vblank`, only on the thread that runs RenderStage.
  - The flip itself is `sceDisplaySetFrameBuf(..., NEXTFRAME)` from the GXM display queue callback.
- **Profiler.** X keeps its own CPU profiler in the frame manager, in microseconds:

  | Field | Offset |
  |---|---|
  | update | `+0x60` |
  | draw | `+0x70` |
  | swap | `+0xA0` |
  | sub-phases | `+0x118`–`+0x178` |

  The recording's detail columns come from these.

## Building

You need [VitaSDK](https://vitasdk.org) with the taiHEN stubs (`vdpm install taihen`).

```
mkdir build && cd build
cmake .. && make
```

This produces `divasplit.suprx` (game plugin), `divasplit_qm.suprx` (Quick Menu plugin), `divasplit_prof.skprx` (profiler kernel plugin) and `divasplit_installer.vpk`.

Shaders: `shaders/*.cg`. The installer compiles them on the Vita; copy the results from `ux0:data/divasplit/shaders/` to `shaders/compiled/` and run `python3 tools/gxp2h.py` to build them into the plugin.

Tests that run on a PC:
- `installer/test/test_edit.c`: the installer's file edits.
- `test/test_cuts.c`: `centre` and `lsort` against the game's versions, and the bytes of the `dirty` patch (`cc -O2 -ffp-contract=off -Isrc -o test_cuts test/test_cuts.c`).
- `test/test_r2.c`: `h2f` for all inputs, and `keyset` against vectors made by emulating the game's own machine code (`./test_r2 test/vectors/keyset.txt`).

## Credits

- Font: Terminus Font 8×14 bold, by Dimitar Toshkov Zhekov (SIL Open Font License 1.1). The bitmap header comes from Electry's PSVshell.
- Quick Menu: [QuickMenuReborn](https://github.com/Ibrahim778/QuickMenuReborn) by Ibrahim778 (MIT). Its headers and stub library are included in `qm/`.
- VitaGrafix and its patchlist, by Electry and contributors.
- Adaptive sharpening: the weighting of [AMD FidelityFX CAS](https://github.com/GPUOpen-Effects/FidelityFX-CAS) (MIT), reimplemented in `shaders/cas_f.cg`.
