#####################################################################################################
## Name: MotorControlGUISr90                                                                       ## 
## Author: Nathan Burns                                                                            ##
## Date(s): Summer 2026                                                                            ##
## Purpose: This code creates a GUI control system for the translational stage setup used to test  ##
## the scintillating tiles light yield. See ELOG for more info and manual on how to use.           ##
#####################################################################################################

import serial
import time
import math
import datetime
import threading
import tkinter as tk
from tkinter import ttk
from tkinter import *
from tkinter import messagebox
from tkinter import filedialog
import subprocess as sub
import sys
import re
import os

import GraphingLightYield


# Global variables to keep track for the Sr90 setup
Sr90_config=0
Sr90_gain=0
Sr90_data_folder=''
tileAlignX = -6.65
tileAlignY = -5.50

# conversion settings
scan_range_cm = 12.7
steps_per_unit = 2000   # 1 cm is 2000 motor steps
tile_length = 4.8       # tile length in cm (should be 5cm but measurements show otherwise -> be sure to check)

speed = 2000
homing_speed = 2000

# connection settings 
#serial_port = "/dev/tty.usbmodem00038002941"            # I think was used for HRPPD
#serial_port = "/dev/ttyACM0"       # a general connection that tends to work
serial_port = "/dev/serial/by-id/usb-Velmex__Inc._VXC_Stepping_Motor_Controller_0003800294-if00"   # searches for usb ports with velmex id

baud_rate = 57600   # communication speed (baud is number of times a signal changes state per second)

# initialization of program state variables (determines state of system)
motorSerPort = None
motor1Pos = 0
motor2Pos = 0
position_initialized = False
offset_cm = 12.7  # origin offset (cm)
status_reset = None

# for drawing
grid_size = 5     # change this for how fine you want the tile scan to be (5 is  5x5, 10 is 10x10, etc) - also changed in GUI
tile_states = [[0 for col in range(grid_size)] for row in range(grid_size)]

# opens serial communication to the motors 
def connectMotors():
    global motorSerPort

    if motorSerPort is None or not motorSerPort.is_open:
        try:
            print("Opening serial port...")
            motorSerPort = serial.Serial(serial_port, baud_rate, timeout=1)

            time.sleep(2)  # give the controller time to initialize

            motorSerPort.write("F,A1M2,A2M2,R".encode())  # controller-specific initialization
            motorSerPort.write(f"C,S1M-{speed},R".encode())
            motorSerPort.write(f"C,S2M-{speed},R".encode())
            print("Motors connected successfully.")

        except serial.SerialException as e:
            motorSerPort = None
            print("ERROR: Could not connect to motors.")
            print(f"Details: {e}")


def home():
    command="C,"
    command+=f"S1M-{homing_speed},I1M-0,"# Move X back to limit switch
    command+=f"S2M-{homing_speed},I2M-0,"# Move y back

    command+="I2M25400,I1M25400,"# Move y into position then x
    command+="IA1M-0,IA2M-0,"# set 0 position
    command+="R"
    motorSerPort.write(command.encode())


    
# Read motor positions, update gui and global variables
def checkMotorLoop():
    global motor1Pos, motor2Pos, status


    motorSerPort.read_all()
    motorSerPort.write("C".encode())

    # check if the motor is busy
    motorSerPort.write("V".encode())
    global status
    status=motorSerPort.read(1).decode()
    if status=="R":                     # only read motor positions if not busy

        x,y=None,None

        try:
            motorSerPort.write('C,X,R'.encode())
            x=int(motorSerPort.read(10).decode()[0:-1])
            if x_slider.get()!=x/steps_per_unit and motor1Pos!=x/steps_per_unit:       # update gui
                x_slider.set(x/steps_per_unit)

            motor1Pos=x/steps_per_unit
        except Exception as e:
            print("error reading X")
            print(e)

        try:

            motorSerPort.write('C,Y,R'.encode())
            y=int(motorSerPort.read(10).decode()[0:-1])
            if y_slider.get()!=y/steps_per_unit and motor2Pos!=y/steps_per_unit:
                y_slider.set(y/steps_per_unit)

            motor2Pos=y/steps_per_unit
        except Exception as e:
            print("error reading Y")
            print(e)

    #check motors every 50ms
    root.after(50,checkMotorLoop)


# moves to a position and updates coordinates
def move(dx, dy):
    
    dx=dx*steps_per_unit
    dy=dy*steps_per_unit
    
    x_steps = int(dx)
    y_steps = int(dy)

    command="C,"
    if(dx!=0):
        command+="I1M"+str(int(x_steps))+","
    if(dy!=0):
        command+="I2M"+str(int(y_steps))+","

    command+="R"
    
    motorSerPort.write(command.encode())
    

def goToPos(x,y,order=("x","y")):

    x=x*steps_per_unit
    y=y*steps_per_unit

    x=round(x)
    y=round(y)

    
    command="C,"
    commandX="IA1M"+str(int(x))+","
    commandY="IA2M"+str(int(y))+","

    for i in order:
        if i=="x":command+=commandX
        if i=="y":command+=commandY

    command+="R"
    motorSerPort.write(command.encode())


# kills the system, stops all processes
def kill():
    global scan_killed
    scan_killed = True
    motorSerPort.write("C,K".encode())

# closes serials ports and destroys GUI
def quitApp():
    print("Exiting...")
    try:
        if motorSerPort is not None and motorSerPort.is_open:
            motorSerPort.write("C,K".encode())  # kill motion
            motorSerPort.flush()
            time.sleep(0.2)
            motorSerPort.close()
    except Exception as e:
        print("Serial close error:", e)

    root.quit()  


def goToFromSliders(event=None):
    goToPos(x_slider.get(), y_slider.get())


# threaded functions allow the GUI to still be usable while other processes are running
def threadedHome():
    threading.Thread(target=home).start()

def threadedOrigin():
    threading.Thread(target=lambda: goToPos(0, 0)).start()

def threadedAligned():
    threading.Thread(target=lambda: goToPos(tileAlignX, tileAlignY)).start()

# a function that updates the status of the GUI for user interface
def updateStatus(text, color="blue"):
    global status_reset
    
    status_label.config(text=f"Status: {text}", foreground=color)

    if status_reset is not None:
        root.after_cancel(status_reset)
        status_reset = None

    root.after(50,checkStatus)


# a function that directly checks the status of the motors and tells the user if they are in motion or not
def checkStatus():
    if status == "R":
        updateStatus("Motors are Idle", "green")
        
    else:
        updateStatus("Motors are not Idle", "red")



def open_window_Sr90():
    
    new_window = Toplevel(main)
    new_window.geometry("800x600")
    new_window.title("Sr90 Test Window Verification")

    # Variables for inputs
    config = tk.StringVar(value="single_tile")
    grid_size_btn = tk.IntVar()
    gain_var = tk.StringVar()
    data_directory = tk.StringVar()

    #######################################################################
    # Warning banner

    warning_label = tk.Label(new_window,text=
            ("⚠ Please ensure setup is as directed in manual, complete with Sr90, CAEN, Janus is installed, both SiPMs and Tiles are correctly aligned, and the dark box is closed. ⚠"), bg="yellow", fg="black", font=("Helvetica", 11, "bold"), wraplength=700, justify="left", padx=10, pady=10)
    warning_label.pack(fill="x", padx=10, pady=10)

    #######################################################################
    # Configuration frame

    config_frame = ttk.LabelFrame(new_window, text="Configuration",padding=10)
    config_frame.pack(fill="x", padx=20, pady=10)

    # Tile configuration buttons (I used radio buttons here because I found out about them for the first time lol)
    ttk.Label(config_frame, text="Number of Tiles:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
     
    ttk.Radiobutton(config_frame, text="Single Tile", variable=config, value="single_tile").grid(row=0, column=1, padx=10, pady=5)

    ttk.Radiobutton(config_frame, text="Full 8 Tiles", variable=config, value="full_8_tiles").grid(row=0, column=2, padx=10, pady=5)

    # Grid size for tiles
    ttk.Label(config_frame, text="Tile Division:").grid(row=1, column=0, padx=10, pady=10, sticky="w")

    ttk.Radiobutton(config_frame, text="2x2", variable=grid_size_btn, value=2).grid(row=1, column=1, padx=10, pady=5)

    ttk.Radiobutton(config_frame, text="3x3", variable=grid_size_btn, value=3).grid(row=1, column=2, padx=10, pady=5)

    ttk.Radiobutton(config_frame, text="4x4", variable=grid_size_btn, value=4).grid(row=1, column=3, padx=10, pady=5)

    ttk.Radiobutton(config_frame, text="5x5", variable=grid_size_btn, value=5).grid(row=1, column=4, padx=10, pady=5)
    
    # Gain entry
    ttk.Label(config_frame, text="Gain of SiPM:").grid(row=2, column=0, padx=10, pady=10, sticky="w")

    gain_entry = ttk.Entry(config_frame, textvariable=gain_var, width=15)
    gain_entry.grid(row=2, column=1, padx=10, pady=10, sticky="w")

    # Data directory selection
    ttk.Label(config_frame, text="Raw Data Folder:").grid(row=3, column=0, padx=10, pady=10, sticky="w")
    folder_label = ttk.Label(config_frame, text="No folder selected", wraplength=700)
    folder_label.grid(row=3, column=1, columnspan=3, padx=10, pady=10, sticky="w")

    def select_folder():
        folder = filedialog.askdirectory(parent=new_window)

        if folder:
            data_directory.set(folder)
            folder_label.config(text=folder)


    folder_button = ttk.Button(new_window, text="Select Data Folder", command=select_folder)

    folder_button.pack(pady=10)

    #######################################################################
    # Start button

    def start_run():

        global Sr90_config
        global Sr90_gain
        global Sr90_data_folder
        global grid_size
        global tile_states

        # make sure we get an actual input and then assign all global values for use in Sr90 code
        try:
            gain = float(gain_entry.get())
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid numerical SiPM gain.", parent=new_window)
            return

        folder = data_directory.get()

        if not folder:
            messagebox.showerror("Missing Folder", "Please select a data folder before starting.", parent=new_window)
            return

        configuration = config.get()

        if (config.get() == "single_tile"):
            Sr90_config = 1
            tile_states = [[0 for col in range(grid_size)] for row in range(grid_size)]
        elif (config.get() == "full_8_tiles"):
            Sr90_config = 8
            tile_states = [[[0 for col in range(grid_size)] for row in range(grid_size)] for tile in range(8)]

        Sr90_gain = gain

        Sr90_data_folder = folder

        grid_size = grid_size_btn.get()

        # Check the values just in case
        print("Configuration:", configuration)
        print("SiPM Gain:", gain)
        print(f"Grid Size: {grid_size} x {grid_size}")
        print(f"Folder path is: {Sr90_data_folder}")

        # Start the scan
        sr90_scan = Sr90Scan()
        sr90_scan.start()
        sr90_scan.triggerNextUpdate()
        
        # Close window for now
        new_window.destroy()


    start_button = tk.Button(new_window, text="START", bg="green", fg="white", font=("Helvetica", 14, "bold"), width=20, height=2, command=start_run)
    start_button.pack(pady=30)



    

############################################################################################################
############################################################################################################
## Here starts the Sr90 code!!! ##


# Manually trigger janus - directly taken from Grant's code non-modified
def runJanus():
    #p=sub.Popen(["echo","heavyions2024","|","sudo","-S","./JanusC"],stdout=sys.stdout,stdin=sub.PIPE,shell=False,cwd="/home/lfhcal24/Janus_5202_3.6.0_20240514_linux/bin/")

    
    p=sub.Popen(["sudo","./JanusC"],stdout=sys.stdout,stdin=sub.PIPE,shell=False,stderr=sub.DEVNULL,cwd="/home/lfhcal/Janus_5202_4.2.4_20251007_linux/bin/")             # CHANGE THIS BASED ON JANUS LOCATION

    
    #p.communicate(input="heavyions2024\n".encode())
    time.sleep(2)
    print("s")
    p.stdin.write("s".encode()+b"\n")
    p.stdin.flush()

    #How long to run janus -> check this time
    time.sleep(9000)

    
    print("q")
    p.stdin.write("q".encode())
    p.stdin.flush()


# Sr90 code largely written by Grant, modified to work with current setup  
class Sr90Scan:

    # def wait_for_detector_temp():
    # pattern = re.compile(r"Detector Temp = \s*([-+]?\d+(?:\.\d+)?)")

    # for line in sys.stdin:
    #     match = pattern.search(line)
    #     if match:
    #         temperature = float(match.group(1))
    #         return temperature


    def __init__(self):

        # Declare the setup
        self.config = Sr90_config    # either 1 or 8 tiles
        self.gain = Sr90_gain
        self.path = Sr90_data_folder
        self.grid = grid_size

        if (self.config == 0 or self.gain == 0):
            print("Error: no value inputted for configuration and/or gain")

        # keeping track of the detector temperature from Janus
        self.scanTemps = []

        # Tile size -> I am adding three here because for some reason the stage thinks it is 13cm long when it is actually about 16cm - check in future for reason
        self.tileWidth = tile_length + 3
        self.tileHeight = tile_length + 3

        # x,y coords of the  stage where both tiles are aligned -> check this 
        self.tileCenterX = tileAlignX
        self.tileCenterY = tileAlignY

        # matrix of positions in tile 
        self.tileXDivisions = grid_size
        self.tileYDivisions = grid_size

        # How long each step in the x/y direction is
        self.xStepDist=self.tileWidth/self.tileXDivisions
        self.yStepDist=self.tileHeight/self.tileYDivisions
        print(f"Step size is {self.xStepDist}, {self.yStepDist}")

        #Keep track of current step location
        self.currentStep=None
        self.currXIndex=None
        self.currYIndex=None

        # CHANGE THIS BASED ON JANUS SETTINGS 
        # How long the Janus scan will run for (in seconds)
        self.janusTime = 3600 


        # Keep track of delays and positional targets
        self.waitUntil = datetime.datetime.now()
        self.positionGoal=(None,None)


        # Whether or not to trigger the Janus application; False will still run the sequence but not trigger Janus
        self.runJanus=True


        self.janusProcess=None

    def start(self):
        self.currentStep="start"
        self.currXIndex=0
        self.currYIndex=0
    
    def kill(self):
        self.currentStep=""
        self.positionGoal=(None,None)
    
    def goToPos(self,x,y,order=("x","y")):
        x=round(x*2000)/2000
        y=round(y*2000)/2000

        self.positionGoal=(x,y)
        goToPos(x,y,order)

    # Keep calling this function to keep looping
    def triggerNextUpdate(self):
        root.after(250,lambda: self.updateLoop())

    def updateLoop(self):
        global motor1Pos, motor2Pos

        # Don't do anything if motor is busy
        motorSerPort.write("V".encode())
        status = motorSerPort.read(1).decode()      # I don't actually think we need since I made status global
        if status!="R":
            self.triggerNextUpdate()
            return

        # Don't do anything if we're not on a step
        if self.currentStep=="":
            self.triggerNextUpdate()
            return

        # If we haven't reached our target position don't do anything
        if (motor1Pos,motor2Pos) != self.positionGoal and self.positionGoal != (None,None):
            self.triggerNextUpdate()
            return
        
        # If we are waiting 
        if (datetime.datetime.now()<self.waitUntil):
            self.triggerNextUpdate()
            return

        # Step 1: Open Janus
        if self.currentStep=="start":
            self.goToPos(self.tileCenterX,self.tileCenterY)

            if (self.runJanus):
                self.janusProcess=sub.Popen(["sudo","./JanusC"],stdout=sys.stdout,stdin=sub.PIPE,shell=False,stderr=sub.DEVNULL,cwd="/home/lfhcal/Janus_5202_4.2.4_20251007_linux/bin/")        # CHANGE THIS BASED ON JANUS LOCATION
            
                self.waitUntil=datetime.datetime.now()+datetime.timedelta(seconds=2)
            self.currentStep="wait for janus to open"

            
        # Wait for Janus to run a certain amount of time
        elif self.currentStep=="wait for janus to open":
            self.currentStep="wait for janus"

            if(self.runJanus):
                self.janusProcess.stdin.write("h".encode()+b"\n")
                self.janusProcess.stdin.flush()
                print("h")
                time.sleep(1)

                self.janusProcess.stdin.write("H".encode()+b"\n")
                self.janusProcess.stdin.flush()
                print("H")
                time.sleep(1)

                self.janusProcess.stdin.write("H".encode()+b"\n")
                self.janusProcess.stdin.flush()
                print("H")
                time.sleep(1)

                self.janusProcess.stdin.write("q".encode()+b"\n")
                self.janusProcess.stdin.flush()
                print("q")
                time.sleep(1)


        # Go to scan position
        elif self.currentStep=="wait for janus" or self.currentStep=="increment":
            self.currentStep="go to scan"

            # center of tile
            x=self.tileCenterX
            y=self.tileCenterY

            #corner of tile
            x-=self.tileWidth/2
            y-=self.tileHeight/2

            #center of corner scan area
            x+=self.xStepDist/2
            y+=self.yStepDist/2

            x+=self.xStepDist*self.currXIndex
            y+=self.yStepDist*self.currYIndex

            self.goToPos(x,y)
            #print(f"{x},{y} position was sent")
            
        # Do the scan
        elif self.currentStep=="go to scan":
            self.currentStep="do scan"

            # Update the grid in GUI
            tile_states[self.currYIndex][self.currXIndex] = 1

            if self.runJanus:

                # First tell janus to open the menu back up before each scan so we can read the detector temp
                self.janusProcess.stdin.write("h".encode()+b"\n")
                self.janusProcess.stdin.flush()
                print("h")
                time.sleep(1)

                # This is where the detector temp should be displayed so try and read it here
                # Store the temperature if possible
                # if (self.runJanus):
                #     temp = self.wait_for_detector_temp()

                # if temp is not None:
                #      self.scanTemps.append(temp)

            
                self.janusProcess.stdin.write("q".encode()+b"\n")
                self.janusProcess.stdin.flush()
                print("q")
                time.sleep(1)
                
                print("s")
                self.janusProcess.stdin.write("s".encode()+b"\n")
                self.janusProcess.stdin.flush()

                # HOW MANY SECONDS OF TAKING STRONTIUM 90 DATA (important)
                self.waitUntil=datetime.datetime.now()+datetime.timedelta(seconds=self.janusTime)
            
        # Go to next scan position
        elif self.currentStep=="do scan":
            
            # Update the grid in GUI
            tile_states[self.currYIndex][self.currXIndex] = 2
            
            self.currentStep="increment"
            # increment scan location
            
            if(self.currXIndex%2==0):
                if self.currYIndex==self.tileYDivisions-1:
                    self.currXIndex+=1
                else:
                    self.currYIndex+=1
            else:
                if self.currYIndex==0:
                    self.currXIndex+=1
                else:
                    self.currYIndex-=1
            
            if(self.currXIndex>=self.tileXDivisions):
                self.currentStep=None

                if self.runJanus:
                    self.janusProcess.stdin.write("h".encode()+b"\n")
                    self.janusProcess.stdin.flush()
                    print("h")
                    time.sleep(1)

                    self.janusProcess.stdin.write("H".encode()+b"\n")
                    self.janusProcess.stdin.flush()
                    print("H")
                    time.sleep(1)

                    self.janusProcess.stdin.write("q".encode()+b"\n")
                    self.janusProcess.stdin.flush()
                    print("q")
                    time.sleep(1)

                    self.janusProcess.stdin.write("q".encode()+b"\n")
                    self.janusProcess.stdin.flush()
                    print("q")
                    print("y")
                    time.sleep(1)
                    print("Remember to turn off high voltage!!!!!!!")

                    print(f"\n\nRun is now complete, graphing with gain value of {self.gain}...")
                    GraphingLightYield.main(self.path, self.gain, self.grid)
            else:
                print("new x y",self.currXIndex,self.currYIndex)

            


        self.triggerNextUpdate()



# this function draws the image at the bottom based on the precision of squares needed. It also maintains the
# squares as either nothing (white - 0), in progress (orange - 1), or completed (green - 2)  
def draw_grid():
        
    tile_draw.delete("all")

    tile_size = 250 / grid_size

    Num_Tiles = Sr90_config 

    if (Num_Tiles == 1):
        # loops over tiles to constantly update their state
        for row in range(grid_size):
            for col in range(grid_size):

                x1 = col * tile_size
                # need an altered y direction to make it work
                draw_row = grid_size - 1 - row
                y1 = draw_row * tile_size

                x2 = x1 + tile_size
                y2 = y1 + tile_size

                state = tile_states[row][col]

                if state == 0:
                    color = "white"
                elif state == 1:
                    color = "orange"
                else:
                    color = "green"

                tile_draw.create_rectangle(x1, y1, x2, y2, fill=color,outline="black")

            
                # Draw dimple circle on top (currently calibrated to the square of 250x250)
                tile_draw.create_oval(95, 95, 155, 155, outline="black", width=2)


    #### !!!! Note that this is experimental and is not set up in the actual run/data taking !!!! Currently it will create the 2x4 tile grid but will
    # fail when it attempts to update because it isn't the correct tile state. Will fix by having a seperate run in the Sr90 code for the full 8 grid
    elif (Num_Tiles == 8):
        big_tile_w = 250 / 2
        big_tile_h = 250 / 4
        for tile in range(8):

            tile_col = tile % 2
            tile_row = tile // 2

            x_offset = tile_col * big_tile_w
            y_offset = tile_row * big_tile_h

            cell_w = big_tile_w / grid_size
            cell_h = big_tile_h / grid_size

            for row in range(grid_size):
                for col in range(grid_size):

                    draw_row = grid_size - 1 - row

                    x1 = x_offset + col * cell_w
                    y1 = y_offset + draw_row * cell_h

                    x2 = x1 + cell_w
                    y2 = y1 + cell_h
                    
                    state = tile_states[tile][row][col]

                    if state == 0:
                        color = "white"
                    elif state == 1:
                        color = "orange"
                    else:
                        color = "green"

                    tile_draw.create_rectangle(x1, y1, x2, y2, fill=color, outline="black")

                    cx = x_offset + big_tile_w/2
                    cy = y_offset + big_tile_h/2

                    r = min(big_tile_w, big_tile_h) * 0.12

                    tile_draw.create_oval(cx-r, cy-r, cx+r, cy+r, outline="black", width=2)


        
    root.after(50,draw_grid)



#################################################################################################################
# GUI


root = Tk()
root.title("Sr90 Motor Control GUI")
root.geometry("650x1000")
connectMotors()

#######################################################################
# Main for everything else to build off of

main = ttk.Frame(root, padding=15)
main.pack(fill="both", expand=True)

# make it stretch nicely
main.columnconfigure(0, weight=1)

status_label = Label(main, text="Status: Idle", font=("Helvetica", 12), foreground="white")
status_label.grid(row=15, column=0, columnspan=3, sticky="ew", pady=(0, 10))

#######################################################################
# Manual Control

Label(main,text="Manual Control",font=("Helvetica", 18, "bold")).grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))

manual_frame = ttk.LabelFrame(main, text="Manual Control", padding=10)
manual_frame.grid(row=1, column=0, sticky="ew", pady=10)

# X control row
Button(manual_frame, text="-x (left)", command=lambda: move(-1.56, 0)).grid(row=0, column=0, padx=5, pady=4)

x_slider = tk.Scale(manual_frame,from_=-offset_cm,to=offset_cm,length=200,orient=tk.HORIZONTAL,resolution=0.01)
x_slider.set(0)
x_slider.bind("<ButtonRelease-1>", goToFromSliders)
x_slider.grid(row=0, column=1, columnspan=2, padx=5, pady=4)

Button(manual_frame, text="+x (right)", command=lambda: move(1.56, 0)).grid(row=0, column=3, padx=5, pady=4)

# Y control row
Button(manual_frame, text="-y (backward)", command=lambda: move(0, -1.56)).grid(row=1, column=0, padx=5, pady=4)

y_slider = tk.Scale(manual_frame, from_=-offset_cm, to=offset_cm, length=200, orient=tk.HORIZONTAL, resolution=0.01)
y_slider.set(0)
y_slider.bind("<ButtonRelease-1>", goToFromSliders)
y_slider.grid(row=1, column=1, columnspan=2, padx=5, pady=4)

Button(manual_frame, text="+y (forward)", command=lambda: move(0, 1.56)).grid(row=1, column=3, padx=5, pady=4)




#######################################################################
# Options 
Label(main, text="Options", font=("Helvetica", 18, "bold")).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(20, 10))

# Options frame
options_frame = ttk.LabelFrame(main, text="Options", padding=10)
options_frame.grid(row=3, column=0, sticky="ew", pady=10)

options_frame.columnconfigure(0, weight=1)

Button(options_frame, text="Home (recalibrate)", command=threadedHome).grid(row=0, column=0, sticky="ew")

Button(options_frame, text="Origin (0,0)", command=threadedOrigin).grid(row=1, column=0, sticky="ew")




#######################################################################
# Janus/Sr90 Test
Label(main, text="Sr 90 Light Yield Test", font=("Helvetica", 18, "bold")).grid(row=4, column=0, columnspan=3, sticky="ew", pady=(20, 10))

# Sr90 Frame
janus_frame = ttk.LabelFrame(main, text="Sr90 Light Yield Test", padding=10)
janus_frame.grid(row=5, column=0, sticky="ew", pady=10)

janus_frame.columnconfigure(0, weight=1)

Button(janus_frame, text="Start Test", command=open_window_Sr90).grid(row=0, column=0, sticky="ew")

Button(janus_frame, text="Align Tiles", command=threadedAligned).grid(row=1, column=0, sticky="ew")




#######################################################################
# Kill and Quit

ttk.Separator(main, orient=HORIZONTAL).grid(row=6, column=0, columnspan=5, rowspan=1, pady=10, sticky='nesw')

E_frame = ttk.Frame(main, padding=10)
E_frame.grid(row=7, column=0, sticky="ew", pady=10)

E_frame.columnconfigure(0, weight=4)
E_frame.columnconfigure(1, weight=1)

Button(E_frame, text="Kill", bg="red", command=kill).grid(row=0, column=0, sticky="nsew", padx=10)

Button(E_frame, text="Quit", command=quitApp).grid(row=0, column=1, sticky="nsew", padx=5)




##########################################################################
# Drawing of the tile for user-interface

canvas_frame = ttk.Frame(main, padding=15)
canvas_frame.grid(row=12, column=0)

tile_draw = tk.Canvas(canvas_frame, width=250, height=250, bg="white")

tile_draw.grid(row=0, column=0) 







draw_grid()   # call the function to draw the image

checkMotorLoop()    # call the function to start checking the motor 

checkStatus()     # call the function to constantly tell the status of the motors/processes

root.mainloop()   # keep looping the GUI so it updates automatically
