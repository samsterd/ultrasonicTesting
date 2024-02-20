Code and scripts to run 2D ultrasonic scans. 

Pulses are generated using an Ultratek Compact Pulser and data is collected with a Picoscope 2208B. 

Scan control is done using an Ender-3 3D printer gantry with 3D printed holders for the transducers.

Requirements:

pyserial

picosdk and associated drivers

ctypes

numpy

matplotlib

Currently tested on 64 bit windows. Picoscope controller will likely break on 32 bit machines
