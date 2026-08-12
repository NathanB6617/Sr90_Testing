#####################################################################################################
## Name: GraphingLightYield.py                                                                     ## 
## Author: Nathan Burns                                                                            ##
## Date(s): Summer 2026                                                                            ##
## Purpose: This code is to be used in tandem with the MotorControlGUISr90 code to create a        ## 
## graphical representation of the light yield(s) of the tile and its grid. It aims to convert the ##
## raw ADC signals to PE via a gain provided in the original code, then graph each PE data on the  ##
## corresponding spot in a diagram of the tile.                                                    ##
#####################################################################################################

import ROOT
import math
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import re


# need this to get the files to be in the right order - otherwise it sorts based on other things and is annoying
def run_number(file_path):
    match = re.search(r'Run(\d+)', file_path.name)

    if match:
        return int(match.group(1))

    return -1


# reads the data. Self-explanatory
def readData(file_path):
    LG_vals = []
    HG_vals = []

    with open(file_path, "r") as f:

        # Skip the first 9 info lines
        for _ in range(9):
            next(f)

        for line in f:

            cols = line.split()

            # Skip malformed rows
            if len(cols) < 4:
                continue

            # we only care about channel 0 - channel 32 is the trigger
            channel_num = int(cols[1])
            if channel_num != 0:
                continue

            LG_vals.append(int(cols[2]))
            HG_vals.append(int(cols[3]))

    return LG_vals, HG_vals

# loop over the vectors and transform them into PE distributions by multiplying by the gain
def ADCtoPE(HG_vals, gain):
    
    HG_PE = []

    for val in HG_vals:
        HG_PE.append(val/gain)


    return HG_PE




def MPVData(HG_vals, name):

    # create a histogram to store it
    hist = ROOT.TH1F(f"hist_{id(HG_vals)}", "hist", 250, 0, 250)

    # fill 
    for x in HG_vals:
        hist.Fill(x)

    # use the file to get the MPV
    result = ROOT.GetMPV(hist, str(name))
    mpv = result[0]
    mpvErr = result[1]
    Chi2 = result[2]
    NDf = result[3]
    print(f"MPV value is {mpv} ± {mpvErr}\n")

    param = Chi2/NDf
    if (param >= 3):
        print(f"\n\n\nWARNING: Chi2/NDf value too large ({param}), langauss could not fit well\n\n\n")

    return mpv, mpvErr


def MPVRawData(HG_vals, name):

    # create a histogram to store it
    hist = ROOT.TH1F(f"hist_{id(HG_vals)}", "hist", 1000, 0, 250)

    # fill 
    for x in HG_vals:
        hist.Fill(x)

    # use the file to get the MPV
    result = ROOT.GetMPV(hist, str(name))
    mpv_raw = result[0]
    mpvErr = result[1]
    Chi2 = result[2]
    NDf = result[3]
    print(f"MPV value is {mpv_raw} ± {mpvErr} in ADC\n")

    param = Chi2/NDf
    if (param >= 3):
        print(f"\n\n\nWARNING: Chi2/NDf value too large ({param}), langauss could not fit well\n\n\n")

    return mpv_raw


def MPVtoPE(mpv_raw, gain):
    
    mpv = mpv_raw/gain

    return mpv



def build_tile_grid(values, grid_size):

    grid = [[0 for _ in range(grid_size)]
            for _ in range(grid_size)]

    idx = 0

    for col in range(grid_size):

        # Even columns: top to bottom
        if col % 2 == 0:

            for row in range(grid_size):
                grid[row][col] = values[idx]
                idx += 1

        # Odd columns: top to bottom
        else:

            for row in reversed(range(grid_size)):
                grid[row][col] = values[idx]
                idx += 1

    return grid


def tileGraphData(mpv_vals, mpvErr_vals, grid_size):

    grid = build_tile_grid(mpv_vals, grid_size)
    err_grid = np.array(build_tile_grid(mpvErr_vals, grid_size))

    grid = np.array(grid)

    plt.figure(figsize=(8,8))

    plt.imshow(grid, cmap="viridis", origin="lower")

    for row in range(grid_size):
        for col in range(grid_size):
            plt.text(
                col,
                row,
                f"{grid[row, col]:.2f} ± {err_grid[row, col]:.2f}",
                ha="center",
                va="center",
                color="white",
                fontsize=9
            )

    plt.colorbar(label="MPV value")

    plt.title("Tile Light Efficiency (PE)")

    # plt.savefig("Light_Yield_Scintillating_Tile")   # I think I will figure out a way to filter these to save where I want, but for now just save manually after running. 
    plt.show()



def main(path, gain, grid_size):
    path = Path(path)
    all_mpv_vals = []
    all_mpvErr_vals = []
    
    # call ROOT to open the file to fit the data
    ROOT.gROOT.ProcessLine('.L LandauGauss.C+')

    # loop over all txt files in the folder 
    for file_path in sorted(path.glob("*.txt"), key=run_number):

        print(f"Reading {file_path.name}")

        # read the data
        LG_vals, HG_vals = readData(file_path)

        # convert the data to PE (we only care about the high gain data)
        HG_PE = ADCtoPE(HG_vals, gain)

        # find the most probable value by fitting to a langauss
        mpv_val, mpvErr = MPVData(HG_PE, file_path.name)

        #!!!!!!!!Note that if you want to do this version with raw data you need to change languass.C accordingly
        # otherwise your fits won't have the right range
        #mpv_raw = MPVRawData(HG_vals, file_path.name)

        #mpv_val = MPVtoPE(mpv_raw, gain)
        
        all_mpv_vals.append(mpv_val)
        all_mpvErr_vals.append(mpvErr)

    # graph the result on a tile
    tileGraphData(all_mpv_vals, all_mpvErr_vals, grid_size)




if __name__ == "__main__":
    # change these values if you want to call manually from the terminal
    main("/home/lfhcal/Nathan/Sr90_Light_Yield_Testing/Run1", 76.2374, 5)
