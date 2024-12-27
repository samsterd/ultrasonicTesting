Software and instructions for running a low cost ultrasonic testing apparatus for battery research.

More information can be found at doi.org/10.26434/chemrxiv-2024-qbq8q
# Setup Instructions
### Software

Note: These instructions assume some basic familiarity with setting up Python coding environments. More detailed, simplified 
instructions for setting up in PyCharm are included at the end.

Clone the software from the Github repository by 
>git clone https://github.com/changbatterygroup/ultrasonicTesting.git

The following modules should be installed in your local coding environment via pip:
>numpy, scipy, pyserial, ctypes, matplotlib, PyQt5, tqdm, msl-loadlib, bottleneck
> 
Picoscope and PicoSDK must also be downloaded and installed from PicoTech. These can be found at https://www.picotech.com/downloads

Python wrappers for the PicoSDK must also be installed. These can be found at https://github.com/picotech/picosdk-python-wrappers
After cloning the module from Github it must be installed by navigating in a terminal to the location of the associated setup.py file and running
>python setup.py install
> 
If using the tone burst pulser, the associated drivers must also be installed. In addition, the location of the SDK dll file
USBUT.dll must be added to the file usbut350Server.py

### Hardware

**Required Hardware:** All measurements require a Picoscope 2208B digital oscilloscope and either an Ultratek CompactPulser
or Ultratek USBUT350 Tone Burst Pulser. 

Scanning measurements require a USB enabled gantry that operates on GCode. We
have only tested with a Creality Ender-3 3D printer. The printer head will need to be removed and a 3D printed transducer
holder should be screwed in to use this as a scanning gantry.

Multiplexed measurements have only been tested with a Cytec CXAR Multiplexer. At least 2 modules are required to run
muliplexed measurements.

**Serial Ports:** Plug all hardware into USB ports. You may require adapters depending on the configurations your hardward was purchased in. 
Note that if your computer does not have enough ports, the Picoscope can be plugged into 
a USB hub but the Pulser, gantry, and multiplexer will not work unless plugged in directly to the computer.

**BNC Cables:** The pulser, trigger, measurement, and transducers are all connected by BNC cables. The specific arrangement
will depend on the type of measurement being performed. 

Figure 2 in https://doi.org/10.26434/chemrxiv-2024-qbq8q contains
diagrams for transmission, pulse-echo, and multiplexed measurements. The only constant is that the Trigger output of the 
Pulser is connected to Channel B on the Picoscope and the measurement is done on Channel A.


**NOTE:** Never directly connect the TX output of the Pulser to the Picoscope. The 300V output of the Pulser far exceeds 
the voltage limit of the Picoscope.

### First Measurement

Experiments are run through the script runUltrasonicExperiment.py. It is highly recommended to run experiments through the 
GUI. Ensure that 'gui': True is set in the experimentParams within the script and then run it. This should open a window to run the experiment.

The first time this is run, select Experiment Type : Setup in the dropdown menu. This will assist in identifying the USB
ports that the hardware is plugged into. The results are added to the file "setup_parameters.json" and are used in to
run future experiments through the GUI. First time setup on Linux will likely require setting USB port permissions (see 
troubleshooting)


**NOTE:** This process is under active development. It may crash or hang when an incorrect serial port is guessed.
Improving this process is on the near term development roadmap and future updates should streamline this.

**NOTE:** The multiplexer port is currently not included in this process. The serial port name must be manually added to
the parameter list as "multiplexerPort" : "port name" near the bottom of the parameter list.

**NOTE:** The names of USB ports on Linux systems depend on the order they are plugged in. If you unplug hardware and plug
it back in later, you will likely need to repeat this process since the names have probably changed.

Experiments can also be run without the GUI by manually populating the parameters at the top of runUltrasonicExperiment.py.
Serial port names are taken directly from the experimentParams list in the script (not from setup_parameters.json) 
when run in this mode.

### Data Processing and Analysis

The files pickleJar.py and sqliteUtils.py contain a number of useful functions for saving, loading, and analyzing data. 
Data is initially saved as an SQlite3 database. For larger data sets, it is highly recommended that these be converted to
pickles to improve the speed of loading and analysis.

Examples of loading data, converting it to pickles, and performing basic analysis and plotting is provided in exampleAnalysis.py

### Troubleshooting


Currently tested on 64 bit Windows and Ubuntu. Picoscope controller will likely break on 32 bit machines.

**Linux USB Port Permissions:** Running on Ubuntu may require adjusting USB port permissions. A temporary (but not secure) solution is to run the following
in the terminal:

>sudo chmod 666 /dev/ttyUSB#

More robust and secure solutions exist but we have not had the patience to learn and implement them.

**Plotting in Ubuntu:** Requires changing the backend in matplotlib to Tkinter.
Also needed to install Tkinter on Python if using Linux: sudo apt-get install python3-tk

Then make sure the matplotlib backend is set to Tkinter:

import matplotlib

matplotlib.use('TkAgg')

import matplotlib.pyplot as plt

**My measurement is taking too long:** First try a short measurement to check that everything is properly connected. 
Run a 'Single Pulse' experiment with 'Number of waveforms to average' set to 10. 

If the code crashes (Linux): you likely have USB permission issues (see above).

If the code hangs but nothing happens: the USB port for the Pulser or Scanner may be incorrect. Try rerunning the Setup experiment

If the code does run and plot but takes a long time (several seconds): check that the Pulser trigger output is connected
to the Picoscope Channel B

**The program stops responding during a measurement:** This is safe to ignore. As long as the progress bar in the Python
terminal is updating, the output file size is increasing, and (if applicable) the scanner is moving, your measurement is
still working. The GUI becomes unresponsive during longer measurements but will return once the measurement completes.
Do not force quit the program as this will cause the measurement to end early.

**My scan is blurry at one edge:** You may need to adjust the rest time between rows. If you notice that the scanner moves
in a long, continuous motion at the start of a row before settling into normal collection this confirms the problem.
Open ultrasonicScan.py and change the end of row rest time near line 101 (time.sleep(#)) to a higher number. 
**NOTE:** A better solution to this issue (automatic adjustment of rest time) will be added soon.

### Detailed Setup Instructions in PyCharm
#### For Python Beginners
This guide is for setup on a 64-bit Windows system

- Download Python (if not already present)
    - Latest version, Windows 64bit
- Download Git (if not already present)
    - Standalone installer, Windows 64bit. Use all default options (there will be lots of options in the installer)
- Install PyCharm
    - Create new project. Use the default location, use ‘Project venv’ as Interpreter type. Use the latest version of Python
    - Once in the blank project, select the ‘Terminal’ in the bottom left side menu (>_ in a box)
    - Type ‘git clone https://github.com/samsterd/ultrasonicTesting.git’ and hit enter. The ultrasound code should now be copied into the project directory
- Install package dependencies
    - Bottom left side menus, select the stacked squares (’Python Packages’). Packages are installed using the search function, selecting the right package, and clicking install. If prompted to pick a version, use the latest (highest number) unless noted below
    - Packages to install in this way: pyserial, ~~ctypes~~  (ctypes is now included by default), numpy (version < 2), scipy, bottleneck, matplotlib, tqdm, msl-loadlib, PyQt5
- Install picoscope controller
    - Download and install PicoSDK for PicoScope 2208B from https://www.picotech.com/downloads. ‘
    - **Restart the computer** (this is critical - the python module will not install until the system path variables update via restart)
    - In the PyCharm terminal, run ‘git clone [https://github.com/picotech/picosdk-python-wrappers](https://github.com/picotech/picosdk-python-wrappers?tab=readme-ov-file).git’
    - Still in terminal, navigate to the picosdk folder: ‘cd picosdk-python-wrappers’. Then install the python package: ‘python [setup.py](http://setup.py) install’
    - The PicoSDK functions should now be installed in your virtual environment ‘.venv/Lib/site-packages/picosdk…’. Verify the installation by opening the script ‘picosdk-python-wrappers/anyScopeExamples/block.py’ and running it while the oscilloscope is plugged in. A popup should display briefly while the computer connects, and then a plot should appear. It will likely be noise, but creating a plot without any crashes is a success at this point.
    - You may now delete the folder ‘picosdk-python-wrappers’ that you cloned into the top level of your project (i.e. NOT the version in your .venv folder)
- Install tone burst drivers and SDK (skip if using Compact Pulser)
    - Install the drivers following instructions sent by Ultratek: http://download.usultratek.com/files/USBUT350Installation.pdf
        - Install software from link in step 3.1
        - Download and unzip the driver files. Note the location of the files.
        - Follow ‘disable driver signature’ instructions at the bottom
            - If on Windows 11: https://www.prajwaldesai.com/disable-driver-signature-enforcement-in-windows-11/ . Press and hold shift while clicking ‘Restart’ to reboot in Recovery mode. Once on blue screen: Advanced options → Start-up Settings → Restart → Press 7 (Disable driver signature enforcement)
        - Once rebooted, plug the pulser into a USB port. Open Device Manager and find the pulser (probably under ‘Other Devices’). Right click and select ‘Update driver’ then manually enter the driver location as the place where the driver files were unzipped. While installing, Windows may ask again if you trust the files - say yes.
    - Install the SDK following instructions sent by Ultratek: [http://download.usultratek.com/files/USBUT350SDKInstallation.pdf](https://nam10.safelinks.protection.outlook.com/?url=http%3A%2F%2Fdownload.usultratek.com%2Ffiles%2FUSBUT350SDKInstallation.pdf&data=05%7C02%7Csa3967%40drexel0.mail.onmicrosoft.com%7C1bffdc414d114ecb8b8708dc444b5f7a%7C3664e6fa47bd45a696708c4f080f8ca6%7C0%7C1%7C638460337804516222%7CUnknown%7CTWFpbGZsb3d8eyJWIjoiMC4wLjAwMDAiLCJQIjoiV2luMzIiLCJBTiI6Ik1haWwiLCJXVCI6Mn0%3D%7C0%7C%7C%7C&sdata=Ib7J1iI0c4JHuc7C0uGCAzdCm2tEyqVsdsds%2F7zecaE%3D&reserved=0) (user: download pw: usultratek)
        - Follow instructions for SDK for Microsoft C/C++
    - Add the path to the SDK .dll file to the experiment parameters in [runUltrasonicExperiment.py](http://runUltrasonicExperiment.py) under the name ‘dllFile’. The location should be ‘C:\\USUTSDK\\USBUTSDKC\\USBUT.dll’
- Plug in everything
    - Connect Picoscope and Pulser to computer via USB
    - Connect the trigger output on the tone burst pulser (the unmarked BNC outlet) to Channel A of the Picoscope
    - Connect the TX output of the pulser to one transducer. Connect the Picoscope Channel B to the other transducer
- To test everything is working, hold the two transducers together onto a piece of metal or plastic with some coupling gel and run a ‘single pulse’ experiment with the ‘measureDelay’ set to 0. You should see a very clear wave