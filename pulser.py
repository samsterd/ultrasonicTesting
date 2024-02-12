##Author:
##Date Started:
##Notes: One-stop-shop for interfacing with Ultratek pulser.

from dataclasses import asdict, dataclass
from functools import partial
from time import sleep
from typing import Callable

import requests

IP = '192.168.0.20'
PORT = '9002'
URL = f"http://{IP}:{PORT}"

PRF = 'P500'


@dataclass
class PulserProperties:
    """Everything needed to configure Ultratek pulser."""
    damping: str = 'D0'
    mode: str = 'M0'
    pulse_voltage: str = 'V300'
    pulse_width: str = 'W220'
    pulse_repetition_rate: str = 'P500'
    mode: str = 'T0'  # internal
    # LPF: str = 'L2' #low pass filter of 48 MHz


def _send(command: str, message) -> None:
    return requests.get(f'{URL}/{command}/{message}').text


def config(pulser_properties: PulserProperties):
    for message in asdict(pulser_properties).values():
        _write(message)
        sleep(.05)


_read: Callable = partial(_send, 'read')
_write: Callable = partial(_send, 'writecf')

#this
turn_on: Callable = partial(_write, PRF)
turn_off: Callable = partial(_write, 'P0')
