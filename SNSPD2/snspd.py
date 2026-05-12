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

# TODO: fix all the write string errors

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
    
    def update_station(self, station=None):
        if station is not None: 
            # Update experiment snapshot
            _ = station.snapshot(update=True) # <- updates parameters in station 
            print('update station')
    
    def laser_get_standard(self, laser):
        print(f'Power: {laser.power()}')
        print(f'Frequency coarse: {laser.frequency_coarse()*1e-12}THz')
        print(f'Wavelength (calculated) is {(spc.c/laser.frequency_coarse())*1e9}nm')

    def laser_set_standard(self, laser, wavelength, power):
        laser.power(power)
        laser.frequency_coarse(spc.c/wavelength)

    def pmeter_set_standard(self, pmeter, wavelength):
        # TODO: extract name from station for print?
        pmeter.wavelength(1550e-9)
        print(f'Powermeter wavelength is {pmeter.wavelength()}') 

    def quick_check(self, pmeter10, pmeter90, attenuator_name='', station=None):
        '''Input: measured transmission of beam splitter and power meter instruments
        '''
        # Update experiment snapshot 
        self.update_station(station)

        meas = Measurement()
        meas.register_custom_parameter("power10", label="W")
        meas.register_custom_parameter("power90", label="W")
        meas.register_custom_parameter("attenuation", label="dB")

        with meas.run() as datasaver:
            print(datasaver.run_id)

            datasaver.dataset.add_metadata("attenuator_name", attenuator_name)
            power10 = pmeter10.power()
            power90 = pmeter90.power()
            try: 

                attenuation = 10*np.log10((self.bs10/self.bs90*power90)/power10)
                
                datasaver.add_result(("power10", power10),
                    ("power90", power90),
                    ("attenuation", attenuation))
                
                print(f'power10: {power10}, power90: {power90}, attenuation: {attenuation}')
            except AttributeError: 
                # If beam splitter values are not yet defined don't include attenuation 
                datasaver.add_result(("power10", power10),
                    ("power90", power90))
                print('Could not calculate attenuation, missing beam splitter values')
                print(f'power10: {power10}, power90: {power90}')

            time.sleep(2)

    
    def calibrate(self, t: int, pmeter10, pmeter90, attenuator_name, station=None):
        '''Input: measured transmission of beam splitter arms, power meter instruments, 
        t: time for which to calibrate (s)
        '''

        # Update experiment snapshot 
        self.update_station(station)

        # Initialize measurement 
        meas = Measurement()
        meas.register_custom_parameter("times", label="Samples (approx. s)")
        meas.register_custom_parameter("power10", label="W")
        meas.register_custom_parameter("power90", label="W")
        meas.register_custom_parameter("attenuation", label="dB")

        with meas.run() as datasaver:
            print(datasaver.run_id)

            datasaver.dataset.add_metadata("attenuator_name", attenuator_name)

            start = time.perf_counter()
            
            for i in range(t*2 + 1):
                
                power10 = pmeter10.power()
                power90 = pmeter90.power() 
                attenuation = 10*np.log10((self.bs10/self.bs90*power90)/power10)

                time.sleep(0.5)
        
                datasaver.add_result(("times",i/2),
                                ("power10", power10),
                                ("power90", power90),
                                ("attenuation", attenuation))

            end = time.perf_counter()
            print(f'Finished in {end-start}s')


    def calibrate_electronic(self, t: int, pmeter10, pmeter90, attenuator_name, p_att, station=None):
        '''Input: measured transmission of beam splitter arms, power meter instruments, 
        t: time for which to calibrate (s)
        '''
        # TODO: extract from station rather than by passing in the attenuator? Or update p_att driver to allow for station snapshot to be used
        # Update experiment snapshot 
        self.update_station(station)

        # Initialize measurement 
        meas = Measurement()
        meas.register_custom_parameter("times", label="Samples (approx. s)")
        meas.register_custom_parameter("power10", label="W")
        meas.register_custom_parameter("power90", label="W")
        meas.register_custom_parameter("attenuation", label="dB")
        meas.register_custom_parameter("v_attenuator", label="v_attenuator")

        with meas.run() as datasaver:
            print(datasaver.run_id)

            datasaver.dataset.add_metadata("attenuator_name", attenuator_name)

            start = time.perf_counter()
            
            for i in range(t*2 + 1):
                
                power10 = pmeter10.power()
                power90 = pmeter90.power() 
                attenuation = 10*np.log10((self.bs10/self.bs90*power90)/power10)

                time.sleep(0.5)
        
                datasaver.add_result(("times",i/2),
                                ("power10", power10),
                                ("power90", power90),
                                ("attenuation", attenuation),
                                ('v_attenuator', float(p_att.ask('VOLT?'))))

            end = time.perf_counter()
            print(f'Finished in {end-start}s')

            # Augment to handle case of only one powermeter connected 
    def beam_splitter_calc(self, power10, power90): 
        bs10 = power10/(power10+power90)
        bs90 = power90/(power10+power90)
        return bs10, bs90

    def osc_set_standard_counts(self, MS):
        '''Input: optional argument for time on horizontal axis of oscilloscope
            Optional argument for vertical scale of oscilloscope (10 divisions, set in V/div) 
        '''
        MS.horizontal_mode('MANual') # set manual mode to allow parameters to be set
        MS.horizontal_mode_manual_configure('RECORDLength')
        MS.horizontal_samplerate(625e6)
        h_scale = float(self.counts_h_time)/float(MS.horizontal_divisions())
        MS.horizontal_scale(h_scale)
        MS.horizontal_position(self.counts_h_pos)

        
        MS.channels[0].vertical_scale(self.counts_v_scale)
        MS.channels[0].termination(50)
        MS.channels[0].bandwidth(1e9)
        MS.channels[0].vertical_offset(0)
        MS.channels[0].vertical_position(0)
        MS.channels[0].vterm_bias(0)
        MS.channels[0].scale_ratio(1) # <- just set this as it is 
        MS.channels[0].invert('OFF')
        MS.trigger_channels[0].ch1_trigger_level(self.counts_v_trigger)


    def load_id_from_database(self, database, exp_name, sample_name, ID):
        initialise_or_create_database_at(database)

        try:
            exp = qc.load_experiment_by_name(exp_name, sample=sample_name)
        except ValueError:
            print('No such experiment')
        
        return load_by_id(ID)
    
    def critical_current(self, dmm, yoko, tc, currents, device_name, station=None):
        '''
        interval is specified in seconds
        '''

        # Update station
        self.update_station(station)

        # Establish measurement
        meas = Measurement()
        meas.register_parameter(dmm.volt)
        meas.register_parameter(yoko.current)
        meas.register_custom_parameter("MC_temp", label="K")

        # Set first current 
        yoko.current(currents[0])
       

        with meas.run() as datasaver:
            print(datasaver.run_id)
            
            # save device name 
            datasaver.dataset.add_metadata("device", device_name)


            for cur in currents: # <- sweep wavelength of laser 

                # set current 
                yoko.current(cur)
                time.sleep(1)
                print(f'Starting current {yoko.current()}')

                
                # Save data 
                datasaver.add_result((yoko.current, yoko.current()),
                                    (dmm.volt, dmm.volt()),
                                    ("MC_temp", tc.MC_temp()))
                
                time.sleep(10)

    def photon_number(self, power90, total_attenuation, wavelength):

        # if total_attenuation.any() < 0: 
        #     raise ValueError("total_attenuation should be greater than 0")
        #     return 
        
        Plaser =  power90/self.bs90
        Pin = Plaser*self.bs10
        Pdevice = Pin*(10**(-total_attenuation/10))
        f = spc.c/wavelength 
        Ephoton = spc.h*f
        Nphotons = Pdevice/Ephoton

        return Nphotons
    
    def avg_from_calibration(self, ID, key):
        return np.average(load_by_id(ID).get_parameter_data()[key][key])