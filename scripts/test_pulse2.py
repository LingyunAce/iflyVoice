#!/usr/bin/env python3
"""Test pulsectl 24.x API"""
import os
os.environ.setdefault("PULSE_SERVER", "unix:/run/user/1000/pulse/native")
import pulsectl

def _sink_channels(sink):
    vol = sink.volume
    if hasattr(vol, "values"):
        return list(vol.values)
    return list(vol.value)

def _set_volume(pulse, sink, percent):
    percent = max(0, min(100, int(percent)))
    factor = percent / 100.0
    nchans = sink.channel_count
    vol = pulse.volume_get_all_chans(sink)
    # vol is a float value (flat volume)
    new_vol = factor
    pulse.volume_set_all_chans(sink, new_vol)

try:
    with pulsectl.Pulse("test") as p:
        sinks = p.sink_list()
        print(f"sinks: {len(sinks)}")
        for s in sinks:
            chans = _sink_channels(s)
            flat = p.volume_get_all_chans(s)
            print(f"  {s.name} chans={chans} flat={flat}")

        if sinks:
            s0 = sinks[0]
            # 尝试用 volume_set_all_chans
            p.volume_set_all_chans(s0, 0.5)
            print("set vol to 50% via volume_set_all_chans OK")
            flat2 = p.volume_get_all_chans(s0)
            print(f"  after set: flat={flat2}")

            # 恢复
            p.volume_set_all_chans(s0, 1.0)
            print("restored to 100%")
except Exception as e:
    import traceback
    traceback.print_exc()
