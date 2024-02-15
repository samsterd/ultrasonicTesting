import ctypes
import numpy as np
from picosdk.ps2000a import ps2000a as ps

# Create chandle and status ready for use
#chandle is a unique integer signed int that will identify the picoscope throughout the script
#it is simply initialized here, it won't be tied to an instrument until connectPico() is run
chandle = ctypes.c_int16()
status = {}

#connect to any picoscope in a USB port
#basically a Hello World for python testing
def connectPico():

    #OpenUnit() takes the pointer to the chandle identifier and will return the number for it
    #passing a None/null pointer as the second argument tells openUnit to look for any picoscope in a USB port rather than search for a specific one
    picoReturn = ps.ps2000aOpenUnit(ctypes.byref(chandle), None)

    return picoReturn, chandle

#test persistence of chandle by pinging the connected picoscope
def pingPico(picoHandle):

    return ps.ps2000aPingUnit(chandle)

print(connectPico())

