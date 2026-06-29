#!/usr/bin/env python3
"""Test pulsectl on board"""
import os
os.environ.setdefault("PULSE_SERVER", "unix:/run/user/1000/pulse/native")
import pulsectl

def _sink_channels(sink):
    vol = sink.volume
    if hasattr(vol, "values"):
        return list(vol.values)
    return list(vol.value)

try:
    with pulsectl.Pulse("test") as p:
        sinks = p.sink_list()
        print(f"sinks: {len(sinks)}")
        for s in sinks:
            chans = _sink_channels(s)
            print(f"  {s.name} vol={chans}")
        if sinks:
            s0 = sinks[0]
            from pulsectl import PulseVolumeInfo
            s0.volume = PulseVolumeInfo("100%").with_factor(0.5)
            p.sink_volume_set(s0, s0.volume)
            print("set vol to 50% OK")
            sinks2 = p.sink_list()
            chans2 = _sink_channels(sinks2[0])
            print(f"  after set: vol={chans2}")
except Exception as e:
    import traceback
    traceback.print_exc()
