##Author: Adapted from Steingart Lab
##Date Started:
##pithytimeout=0

from datetime import datetime
from time import time
from pytz import timezone
import figure
import picoscope
import pulser

TZ = timezone('EST')

################################################
'''This must be tweaked for each experiment'''

pulsing_params = picoscope.PulsingParams(
    delay=11,  # microseconds of delay before measurement
    voltage_range=0.8,  # voltage gain (i.e. y-axis range)
    duration=3,  # microseconds of measurement duration
    avg_num=64
)


################################################

def _print_stats(start: float) -> None:
    """Print information about pulse. Help function for pulse().

    For monitoring reliability throughout experiment.

    Args:
        start (float): Unix start time of pulse.
    """

    duration_ms = (time() - start) * 1000
    time_per_pulse_ms = duration_ms / pulsing_params.avg_num

    now_ = datetime.now(TZ)
    now_parsed = now_.strftime("%Y-%m-%d %H:%M:%S")

    print(
        f'''{now_parsed}: pulsing time {round(duration_ms)} ms,'''
        f'''{time_per_pulse_ms} per waveform.'''
    )


def pulse() -> dict[str, list[float]]:
    """Wrapper for a single pulse. Call this externally."""

    pulser.turn_on()
    start: float = time()
    # print(start, pulsing_params)
    waveform = picoscope.callback(pulsing_params=pulsing_params)
    _print_stats(start)
    pulser.turn_off()

    return waveform


def main():
    """Here for testing purposes, incl. before running experiments."""

    raw = pulse()
    waveform = raw['amps'][0]
    print(len(waveform))
    # print(raw.keys())
    figure.plot(data=waveform, pulsing_params=pulsing_params)


if __name__ == "__main__":
    main()


