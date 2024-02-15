# Interface to interact with Picoscope 2208B and collect rapid block data from a simple trigger
# Intended to replace pulse.py for ultrasonic testing
# General program flow:
# openPicoscope() -> connects to picoscope using picosdk through USB
# setupMeasurement() -> takes experimental parameters and converts them to picoscope readable data, passes to scope
# collectData() -> runs measurement, performs averaging, returns waveform data
# closePicoscope() -> ends connection to picoscope








