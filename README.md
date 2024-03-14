Code and scripts to run 2D ultrasonic scans. 

Pulses are generated using an Ultratek Compact Pulser and data is collected with a Picoscope 2208B. 

Scan control is done using an Ender-3 3D printer gantry with 3D printed holders for the transducers.

Requirements:

pyserial

picosdk and associated drivers

ctypes

numpy

matplotlib

tqdm (progress bar)

bottleneck

if using USB-UT350 Tone Burst pulser: msl-loadlib and installation of required drivers. Make sure to add the location of
the SDK dll file USBUT.dll to the file usbut350Server.py

Currently tested on 64 bit windows. Picoscope controller will likely break on 32 bit machines

Running on Linux may require adjusting USB port permissions. The following seems to work:

sudo chmod 666 /dev/ttyUSB#

Also needed to install Tkinter on python: sudo apt-get install python3-tk

Then make sure the matplotlib backend is set to Tkinter:

import matplotlib

matplotlib.use('TkAgg')

import matplotlib.pyplot as plt
