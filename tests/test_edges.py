#!/usr/bin/env python3
"""Edge extraction, checked against synthetic data — no instrument needed.

The library's whole job is turning samples into times, and that half can be
tested without a Digilent on the bench. What cannot be tested here is the device
path (AD3.record), which needs hardware; those failures show up as an obviously
impossible sample rate rather than as a wrong number, so they are caught by
looking at the capture rather than by a fixture.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ad3 import falling_edges, logic_levels, raw_threshold, rising_edges  # noqa: E402

RATE = 1_000_000.0
RANGE_V, OFFSET_V = 5.0, 2.5


def counts(volts):
    """Volts -> the raw int16 counts the device would report on the 5 V range."""
    return np.clip((np.asarray(volts) - OFFSET_V) * 65536 / RANGE_V,
                   -32768, 32767).astype(np.int16)


# Every pulse starts START_S into its period, so the train begins LOW. A train
# that starts already high has no transition into its first pulse, and the count
# is then one short of the pulse count — correct behaviour, and a fixture that
# gets it wrong reads as a library bug.
START_S = 0.001


def square(period_s, width_s, n_periods, lo=0.0, hi=5.0, rise_s=0.0):
    """A TTL-like train. rise_s > 0 gives linear edges instead of vertical ones."""
    per = int(period_s * RATE)
    wid = int(width_s * RATE)
    off = int(START_S * RATE)
    rise = max(1, int(rise_s * RATE))
    v = np.full(per * n_periods, lo)
    for k in range(n_periods):
        s = k * per + off
        v[s:s + wid] = hi
        if rise_s:
            v[s:s + rise] = np.linspace(lo, hi, rise)
            v[s + wid:s + wid + rise] = np.linspace(hi, lo, rise)
    return v


def test_counts_and_times():
    v = square(0.010, 0.002, 20)
    r = rising_edges(counts(v), RATE)
    f = falling_edges(counts(v), RATE)
    assert len(r) == 20 and len(f) == 20
    # Every pulse is 2 ms wide and they repeat every 10 ms.
    assert np.allclose(f - r, 0.002, atol=2e-6)
    assert np.allclose(np.diff(r), 0.010, atol=2e-6)


def test_subsample_interpolation_beats_the_sample_interval():
    """A slow edge should be located far better than one sample period."""
    v = square(0.010, 0.002, 10, rise_s=0.000_050)  # 50 us ramps
    r = rising_edges(counts(v), RATE)
    # The 2.5 V threshold sits halfway up a 50 us ramp, so each crossing lands
    # 25 us after the pulse begins.
    assert np.allclose(r - (np.arange(10) * 0.010 + START_S), 0.000_025, atol=1e-6)


def test_relative_threshold_needs_no_amplitude():
    """relative=0.5 must work on a signal nothing knows the scale of."""
    v = square(0.010, 0.002, 20, lo=0.9, hi=1.4)  # a small photodiode swing
    r = rising_edges(counts(v), RATE, relative=0.5)
    assert len(r) == 20
    assert np.allclose(np.diff(r), 0.010, atol=2e-6)


def test_flat_channel_is_refused_not_guessed():
    """A disconnected input must raise rather than return noise crossings.

    This is the check that turns an unplugged probe into an error message
    instead of a few thousand spurious edges.
    """
    flat = counts(np.full(100_000, 0.002) + np.random.default_rng(0).normal(0, 0.0005, 100_000))
    with pytest.raises(ValueError, match="indistinguishable from noise"):
        rising_edges(flat, RATE, relative=0.5)
    # ...unless the caller insists.
    rising_edges(flat, RATE, relative=0.5, strict=False)


def test_logic_levels_survives_a_low_duty_cycle():
    """A 1%-duty pulse train: the 99th percentile is NOT the high level."""
    v = square(0.010, 0.000_100, 50)  # 100 us high, 10 ms period
    lo, hi = logic_levels(counts(v))
    assert np.isclose(OFFSET_V + RANGE_V * float(lo) / 65536, 0.0, atol=0.1)
    assert np.isclose(OFFSET_V + RANGE_V * float(hi) / 65536, 5.0, atol=0.1)


def test_raw_threshold_round_trips():
    assert np.isclose(OFFSET_V + RANGE_V * raw_threshold(2.5) / 65536, 2.5, atol=1e-3)
