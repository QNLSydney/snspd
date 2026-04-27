import yaml
import time
from time import sleep, monotonic
import datetime
import numpy as np
import matplotlib.pyplot as plt
import sys
import pyvisa
import qcodes as qc
from qcodes.dataset import Measurement
from qcodes.dataset import do0d
from qcodes.dataset.experiment_container import new_experiment, load_experiment_by_name
from qcodes.dataset.plotting import plot_by_id
from qcodes.dataset.data_set import load_by_id, load_by_counter
from qcodes import initialise_or_create_database_at, new_data_set, new_experiment
import scipy
import scipy.constants as spc 


class snspd:
    def __init__(self, config=None):

        if config is not None: 
            with open(config, 'r') as f: # open in read mode 
                attrs = yaml.safe_load(f)

                for key, value in attrs.items(): # items method extracts key value pairs in a dictionary 
                    setattr(self, key, value) # set attribute in class, with name key and with value



        # # Parameters pertaining to instruments 
        # self.att_screw_name = 'VOA50PM'
        # self.att_blue_name = 'V1550PA'
        # self.bs10 = 0.08819209378534265
        # self.bs90 = 0.9118079062146573
        # self.fourK_amp_gain_centre = 45
        # self.fourK_amp_gain_error = 5
        # self.RT_amp_gain_centre = 21.74 # dB 
        # self.RT_amp_gain_error = 3.02 # dB 
        # self.connection1 = 'single fibre'
        # self.connection2 = 'ferrule to ferrule'


        # # Create config for parameters that pertain to devices 
        # self.h_time_counts = 100e-3
        # self.h_pos_counts = 0 
        # self.v_scale_counts = 150e-3 
        # self.device_1_name = 'Line 1 R7C6'
        # self.device_2_name = 'Line 2 Old Device'

        # # Parameters pertaining to a particular measurement run - maybe this can be a separate class 
        # self.att_screw_calibration_id = 165
        # # self.att_blue_calibration_avg_id = 441 # from IDs 167-239 
        # self.att_blue_calibration_avg_id = 459 # updated to include calibration times
        # self.system_dark_counts_id = 455
        # self.att_info_id = 457 # data containing votlage an corresponding total attenuation, number of photons 
        # # self.counts_vs_attenuation = 463
        # self.counts_vs_attenuation_id = 464

    def set_thresholds(self): 
        # goal: get this to read in from yaml file
        pass
    
    def laser_get_standard(self, laser):
        print(f'Power: {laser.power()}')
        print(f'Frequency coarse: {laser.frequency_coarse()*1e-12}THz')
        print(f'Wavelength (calculated) is {(spc.c/laser.frequency_coarse())*1e9}nm')
    
    def make_title(self, title, ID, extra=None):
        timestamp = load_by_id(ID).run_timestamp()
        s = f'{title}\nID {ID} {timestamp}'
        if extra is not None:
            s += f'\n{extra}'
        return s