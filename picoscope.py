##Author:
##Date Started:
##Notes: One-stop-shop for interfacing with Picotech oscilloscopes (picoscopes)

from dataclasses import asdict, dataclass
import json
import requests

IP: str = '192.168.0.10'
PORT: str = '5001'
URL = f'http://{IP}:{PORT}/get_wave'


@dataclass()
class PulsingParams:
    """All the params that should should be passed
    to a pulsing picoscope, no more, no less.

    Change at your leisure.
    """

    delay: int  # [us]
    duration: int  # [us]
    voltage_range: float  # [V]
    avg_num: int


def callback(pulsing_params: PulsingParams) -> dict[str, list[float]]:
    """Queries data from oscilloscope.

    Args:
        PulsingParams (dataclass): See definition at top of module.

    Returns:
        dict[str: list[float]]: Single key-value pair with values as
            acoustics pulse data.
    """

    try:
        response = requests.post(URL, data=asdict(pulsing_params)).text
        # print("Raw response: ", response)
        if not response:
            print("Empty response received.")
            return {}
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return {}

    return json.loads(response)
