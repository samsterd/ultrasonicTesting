# set of functions for controlling the Ender-3 for ultrasonic scanning
# modified from test_ender functions

# Functions:
#   openEnder(port)
#   writeToEnder(serialConnection, command)
#   moveEnder(serialConnection, axis, distance)
#   closeEnder(serialConnection)

import serial

# Opens a serial connection to the Ender-3
# Input: usb port address as a string (i.e. 'COM#' on windows or '/dev/ttyUSB#' on Unix)
# Output: a pyserial connection object for the Ender or -1 if an error occurs
def openEnder(port, baudRate = 115200):

    try:
        #Open serial port
        enderSerial = serial.Serial(port, baudRate)

    #catch errors in connection
    except serial.SerialException as error:
        print(f"Error: {error}")

        #return -1 for error
        return -1

    else:
        return enderSerial

# Writes a command to the ender
# Inputs: a single G-Code command string without spaces, newlines, or carriage returns
# Outputs: 0 if executed correctly, -1 if error
def writeToEnder(serialConnection, command):

    #Add space, carriage return, and newline to command
    formattedCommand = command + " \r\n"

    #try to write command to Ender
    try:
        serialConnection.write(formattedCommand.encode('utf-8'))

    except serial.SerialException as error:
        print(f"Error: {error}")
        return -1

    else:
        return 0

# Writes a series of commands to perform relative movements with the Ender
# Inputs: serial connection object, the axis of motion as a string ('X','Y', or 'Z'), and the distance to move (in mm) (can be negative)
# Outputs: 0 if executed correctly, -1 if error
def moveEnder(serialConnection, axis, distance):

    # Convert axis and distance inputs into the proper G-Code
    motionCommand = "G1 " + axis + str(distance)

    try:
        #Set ender to mm
        writeToEnder(serialConnection, "G21")

        #Set positioning to relative (not absolute)
        writeToEnder(serialConnection, "G91")

        #Pop the last state pushed onto the Ender stack
        writeToEnder(serialConnection, "M121")

        #Send motion command
        writeToEnder(serialConnection, motionCommand)

    except serial.SerialException as error:
        print(f"Error: {error}")
        return -1

    else:
        return 0

# Closes connection to the Ender
# Inputs: serialConnection object
# Outputs: 0 if succesful, -1 if error
def closeEnder(serialConnection):
    try:
        serialConnection.close()

    except serial.SerialException as error:
        print(f"Error: {error}")
        return -1

    else:
        return 0