# ad3-capture

Continuous two-channel capture and edge extraction on a **Digilent Analog
Discovery 3**, through the WaveForms SDK, in Python.

Written for measuring stimulus timing in psychophysics rigs — photodiodes, TTL
triggers, audio line outputs — where the question is *when did this physically
happen*, to microseconds, over thousands of trials.

## Why not a bench scope

An oscilloscope driven over SCPI costs about a second and a half per armed
acquisition, which caps a sitting at n≈100. The AD3 records **continuously** to
host memory, so a single 80-second capture holds thousands of trials at 1 µs
resolution. Both channels share one acquisition and one timebase, so the
instrument's clock cancels in any interval measured between them and never has
to be reconciled with the host's.

## Install

```bash
pip install -e .
```

`libdwf` — Digilent's WaveForms SDK — is a **system library**, loaded with
`ctypes`, so pip cannot install it. Get it from
[Digilent](https://digilent.com/reference/software/waveforms/waveforms-3/start);
on Debian/Ubuntu the package also installs the udev rule the USB device needs.
Check it is visible before anything else:

```bash
python3 -c "from ctypes import CDLL, create_string_buffer as buf; \
            v = buf(32); CDLL('libdwf.so').FDwfGetVersion(v); print(v.value.decode())"
```

## Capture

```bash
ad3-capture --seconds 150 --rate 1e6 --channels 1,2 --out capture.npz
```

Nothing is fired from inside the capture loop: the thing being measured runs in
another process, so no busy-wait in the emitter can stall the drain and lose
samples. Start the capture first and let it outlive the stimulus.

By default the `.npz` holds the **edge times, not the samples** — at 1 MS/s a
90-second capture is 180 MB of int16 per channel and the analysis usually wants
only the crossings. Pass `--save-raw` when a waveform has to be looked at rather
than measured; envelope work (audio) needs it.

`--range`, `--offset` and `--attenuation` each accept one value or a
comma-separated value per channel, because the two rarely want the same
settings: a 0–5 V logic line and a 9 V-powered photodiode behind a ×10 probe do
not share a window.

## Analyse

```python
import numpy as np
from ad3 import rising_edges, falling_edges, logic_levels

z = np.load("capture.npz")
r = rising_edges(z["samples_ch1"], float(z["rate"]), relative=0.5)
```

Crossings are resolved **between** samples by linear interpolation, so the
resolution is not the sample interval — at 1 MS/s they land well inside a
microsecond.

Thresholds default to 2.5 V, which suits 0–5 V logic and nothing else. Pass
`relative=0.5` for anything whose amplitude you do not know in advance; it takes
the midpoint of the 1st–99th percentile of the data itself. A channel with no
signal is **refused** rather than thresholded, because a threshold placed in the
middle of a noise band returns a crossing every few samples — that refusal is
how an unplugged probe becomes an error message instead of a few thousand
spurious edges.

`logic_levels()` is the exception to the percentile rule and exists for
low-duty-cycle trains: a 1 %-duty TTL puts the 99th percentile on the boundary
between the two levels, not on the high one.

## Things the hardware will do to you

Collected the hard way; each cost at least an hour.

- **Do not use a USB hub.** Through a laptop dock, the AD3 enumerates at
  480 Mbit/s, accepts every configuration, and then delivers about 20 samples a
  second before stalling in `Running` forever. On a root port the same code runs
  at the full rate with zero lost samples. If a capture stalls at a ludicrous
  sample rate, this is why.
- **The analogue inputs are differential.** Each channel is a pair; a bare coax
  lead leaves the negative input floating and you read mains hum at a few
  millivolts. A scope probe ties it for you via its ground clip.
- **Range is measured at the probe.** With a ×10 probe the two reachable ranges
  become 50 V and 500 V rather than 5 V and 50 V. `AD3` refuses a range the
  device cannot honour instead of silently substituting one.
- **Check the signal is present before a long capture**, not after. Two seconds
  of `--seconds 2` costs nothing; a 330-second capture of a channel that turned
  out to be flat costs 330 seconds you cannot get back.

## Streaming rate, and why 1 MS/s is not always safe

Two things bound a capture, and only the first is obvious. The device sends
`rate × channels × 2` bytes per second and the host must absorb all of it; but
the draining loop also does its own work per iteration, and if that work
allocates, the interpreter is doing memory management inside the window where
the on-board 16384-sample buffer is filling — 16 ms of slack at 1 MS/s. Captures
at 1 MS/s lost a buffer even at real-time priority, where scheduling could not
be the cause. The output array is preallocated for exactly this reason.

If you must fire trials from inside the loop (`AD3.record(on_tick=...)`), the
slack is what a busy-wait has to fit inside. A 50 ms pulse held in `on_tick`
overruns the buffer and loses samples precisely where the falling edge is.

## Tests

```bash
python3 -m pytest tests/
```

They cover the half that can be tested without an instrument: threshold
selection, sub-sample interpolation, the low-duty-cycle case, and the refusal to
threshold a flat channel. The device path needs hardware, and its failures show
up as an impossible sample rate rather than as a subtly wrong number — so they
are caught by looking at the capture, not by a fixture.

## History

Extracted from [dlp-io8-g](https://github.com/chrplr/dlp-io8-g), where it was
written to characterise a USB TTL box and then reused for display and
audio-visual timing in [goxpyriment](https://github.com/chrplr/goxpyriment). The
commit history came across with it.

## Licence

Apache-2.0.
