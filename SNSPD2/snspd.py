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
from qcodes.station import Station
from scipy.signal import find_peaks
import numpy as np
import pandas as pd
from plotting import snspd_plotting
import tqdm

# TODO: fix all the write string errors

class snspd():
    def __init__(self, config=None, station_config=None):

        if config is not None: 
            with open(config, 'r') as f: # open in read mode 
                attrs = yaml.safe_load(f)

                for key, value in attrs.items(): # items method extracts key value pairs in a dictionary 
                    setattr(self, key, value) # set attribute in class, with name key and with value
        self.station = Station(config_file=station_config)

    def initialize_station(self):
        # TODO: there must be a way to loop through the instruments instead of hard coding all of them
        self.dmm = self.station.load_instrument("dmm", revive_instance=True)
        self.yoko = self.station.load_instrument("yoko", revive_instance=True)
        self.laser = self.station.load_instrument("laser", revive_instance=True)
        self.osc = self.station.load_instrument("osc", revive_instance=True)
        # self.pm100d = self.station.load_instrument("pm100d", revive_instance=True) 
        self.pms120 = self.station.load_instrument("pms120", revive_instance=True)
        self.tc = self.station.load_instrument("fridge", revive_instance=True)
        self.p_att = self.station.load_instrument("dmm_keithley", revive_instance=True)
    
    def update_station(self, station=False):
        # Pass station = False to skip updating station 
        if station is not False: 
            # Update experiment snapshot
            _ = self.station.snapshot(update=True) # <- updates parameters in station 
            print('update station')

    def list_instruments(self): 
        rm = pyvisa.ResourceManager()
        print(rm.list_resources())

    def laser_get_standard(self, laser=None):
        laser = self.laser if laser is None else laser 
        print(f'Power: {laser.power()}')
        print(f'Frequency coarse: {laser.frequency_coarse()*1e-12}THz')
        print(f'Wavelength (calculated) is {(spc.c/laser.frequency_coarse())*1e9}nm')

    def laser_set_standard(self, laser, wavelength, power):
        # laser = self.laser if laser is None else laser 
        laser.power(power)
        laser.frequency_coarse(spc.c/wavelength)

    def pmeter_set_standard(self, pmeter, wavelength):
        # TODO: extract name from station for print?
        pmeter.wavelength(wavelength)
        print(f'Powermeter wavelength is {pmeter.wavelength()}') 

    # TODO: add a function that echoes the laser state to some GUI 

    def optics_set_standard(self, laser, pmeter90, p_att, wavelength, laser_power, v_attenuator):
        self.laser_set_standard(laser, wavelength=wavelength, power=laser_power)
        self.laser_get_standard(laser)
        self.pmeter_set_standard(pmeter=pmeter90, wavelength=wavelength)
        p_att.write(f'VOLT{v_attenuator}')
        # TODO: set code to turn attenuator power ON


    def quick_check(self, pmeter10, pmeter90, attenuator=None, station=None):
        '''Input: measured transmission of beam splitter and power meter instruments
        '''
        # Update experiment snapshot 
        self.update_station(station)

        meas = Measurement()
        meas.register_custom_parameter("power10", label="W")
        meas.register_custom_parameter("power90", label="W")
        meas.register_custom_parameter("attenuation", label="dB")

        attenuator_name = attenuator['name'] # <- added this to make consistent rule that you pass in the device you are measuring

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

    # Augment to handle case of only one powermeter connected 
    def beam_splitter_calc(self, power10, power90): 
        bs10 = power10/(power10+power90)
        bs90 = power90/(power10+power90)
        return bs10, bs90
    
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


    def MSO5_set_standard_counts(self, device, MS=None):
        '''Input: optional argument for time on horizontal axis of oscilloscope
            Optional argument for vertical scale of oscilloscope (10 divisions, set in V/div) 
        '''
        MS = self.osc if MS is None else MS

        device_count_settings = device['counts_axes']

        MS.horizontal_mode('MANual') # set manual mode to allow parameters to be set
        MS.horizontal_mode_manual_configure('RECORDLength')
        MS.horizontal_samplerate(625e6)
        h_scale = float(device_count_settings['counts_h_time'])/float(MS.horizontal_divisions())
        MS.horizontal_scale(h_scale)
        MS.horizontal_position(device_count_settings['counts_h_pos'])

        MS.channels[0].vertical_scale(device_count_settings['counts_v_scale'])
        MS.channels[0].termination(50)
        MS.channels[0].bandwidth(1e9)
        MS.channels[0].vertical_offset(0)
        MS.channels[0].vertical_position(0)
        MS.channels[0].vterm_bias(0)
        MS.channels[0].scale_ratio(1) # <- just set this as it is 
        MS.channels[0].invert('OFF')
        MS.trigger_channels[0].ch1_trigger_level(device_count_settings['counts_v_trigger'])
    
    def MSO5_set_standard_trace(self, MS=None, device=None):
        '''Input: optional argument for time on horizontal axis of oscilloscope
            Optional argument for vertical scale of oscilloscope (10 divisions, set in V/div) 
        '''
        MS = self.osc if MS is None else MS

        # TODO: add in a check that the number is a multiple of 0.006

        if device is not None: 
            pass
        # TODO: add functionality to set device-specific parameters or generic parameters
        else: 
            MS.horizontal_mode('MANual') # set manual mode to allow parameters to be set
            MS.horizontal_mode_manual_configure('RECORDLength')
            MS.horizontal_samplerate(625e6)
            h_scale = float(self.trace_h_time)/float(MS.horizontal_divisions())
            MS.horizontal_scale(h_scale)
            MS.horizontal_position(self.trace_h_pos)

            
            MS.channels[0].vertical_scale(self.trace_v_scale)
            MS.channels[0].termination(50)
            MS.channels[0].bandwidth(1e9)
            MS.channels[0].vertical_offset(0)
            MS.channels[0].vertical_position(0)
            MS.channels[0].vterm_bias(0)
            MS.channels[0].scale_ratio(1) # <- just set this as it is 
            MS.channels[0].invert('OFF')
            MS.trigger_channels[0].ch1_trigger_level(self.trace_v_trigger)

    # Run count 
    def osc_count(self, osc):
        # return counts1, counts2, total_counts1, total_counts2, CR1, CR2
        pass 

    def load_id_from_database(self, database, exp_name, sample_name, ID):
        initialise_or_create_database_at(database)

        try:
            exp = qc.load_experiment_by_name(exp_name, sample=sample_name)
        except ValueError:
            print('No such experiment')
        
        return load_by_id(ID)
    
    def unlatch(self,yoko,t=60):
        self.ramp_yoko_current(yoko, target=0,step=0.5e-6)
        yoko.current(0)
        print(f'Unlatch wait time {t}')
        time.sleep(t)

    
    def critical_current(self, device, dmm=None, yoko=None, tc=None, currents=None, unlatch=True, station=None):
        '''
        interval is specified in seconds
        unlatch: bool, if true the function will include unlatch code
        '''
        # Read from station internally unless an instrument is passed 
        yoko = self.yoko if yoko is None else yoko
        dmm = self.dmm if dmm is None else dmm 
        tc = self.tc if tc is None else tc 
        currents = device['currents'] if currents is None else currents

        device_name = device['name']

        # Update station
        self.update_station(station)

        # Establish measurement
        meas = Measurement()
        meas.register_parameter(yoko.current)
        meas.register_parameter(dmm.volt, setpoints=(yoko.current,))
        meas.register_custom_parameter("MC_temp", label="K")

        # Ramp to zero and wait 
        if unlatch:
            self.unlatch(yoko)

        # Set first current 
        self.ramp_yoko_current(yoko, target=currents[0], step=0.5e-6) 
        yoko.current(currents[0])
       

        with meas.run() as datasaver:
            print(datasaver.run_id)
            
            # save device name 
            datasaver.dataset.add_metadata("device", device_name)


            for cur in tqdm.tqdm(currents): # <- sweep wavelength of laser 

                # set current 
                yoko.current(cur)
                time.sleep(1)
                print(f'Starting current {yoko.current()}')

                
                # Save data 
                datasaver.add_result((yoko.current, yoko.current()),
                                    (dmm.volt, dmm.volt()),
                                    ("MC_temp", tc.MC_temp()))
                
                time.sleep(10)
        
        # Ramp to zero and wait 
        if unlatch:
            self.unlatch(yoko)

    def photon_number(self, power90, total_attenuation, v_attenuator, wavelength):

        if total_attenuation.any() < 0: 
            raise Exception("total_attenuation should be greater than 0")

        # Establish measurement
        meas = Measurement()
        meas.register_custom_parameter("total_attenuation", label="dB")
        meas.register_custom_parameter("wavelength", label="m")
        meas.register_custom_parameter("Nphotons")
        meas.register_custom_parameter("v_attenuator", label="V")
        meas.register_custom_parameter("power90", label="W")
        
        with meas.run() as datasaver:
            print(datasaver.run_id)

            Plaser =  power90/self.bs90
            Pin = Plaser*self.bs10
            Pdevice = Pin*(10**(-total_attenuation/10))
            f = spc.c/wavelength 
            Ephoton = spc.h*f
            Nphotons = Pdevice/Ephoton

            datasaver.add_result(("total_attenuation", total_attenuation),
                                ("Nphotons", Nphotons),
                                ("wavelength", wavelength), 
                                ("power90", power90), 
                                ("v_attenuator", v_attenuator))

        return Nphotons
    
    def avg_from_calibration(self, ID, key):
        '''Calibration data is taken over a time interval, take averages of results for photon number
        calculation '''
        return np.average(load_by_id(ID).get_parameter_data()[key][key])
    
        
    def MSO5_counts_vs_current(self, device, n_captures=10, interval=1, osc=None, dmm=None, yoko=None, pmeter90=None, currents=None, unlatch=True, idx_list=None, station=None):
        '''
        interval is specified in seconds. FOr MSO5 must be minimum 1s
        '''
        if interval <1: 
            raise Exception('interval must be greater than or equal to 1s')
        # This was based on 

        # TODO: include exception for if the wrong oscilloscope is used in this function
        # idn = osc.get_idn()
        # if idn['model'] != 'MSO5':
        #         raise Exception('Connected oscilloscope is not a Tektronix MSO5.')

        yoko = self.yoko if yoko is None else yoko
        dmm = self.dmm if dmm is None else dmm 
        osc = self.osc if osc is None else osc
        pmeter90 = self.pms120 if pmeter90 is None else pmeter90 

        # Unpack parameters for device 
        device_name = device['name']
        threshold1 = device['count_calibration']['threshold1']
        threshold2 = device['count_calibration']['threshold2']
        v_scale = device['count_calibration']['v_scale']
        trigger = device['count_calibration']['trigger']
        
        if currents is None:
            currents = device['currents']

        # Check that lengths match 
        for param in ['threshold1', 'threshold2', 'v_scale']:
            if len(device['count_calibration'][param]) is not len(currents):
                raise Exception(f'{param} is not the same length as list of currents')


        print('Set standard oscilloscope parameters for counts')
        self.MSO5_set_standard_counts(device, osc)
        time.sleep(2)

        # Update experiment snapshot 
        self.update_station(station)

        # Ramp to zero and wait 
        if unlatch:
            self.unlatch(yoko)

        meas = Measurement()
        meas.register_parameter(dmm.volt)
        meas.register_parameter(yoko.current)
        meas.register_custom_parameter("wavelength", label="m")
        meas.register_custom_parameter("v_attenuator", label="V")
        meas.register_custom_parameter("threshold1", label="V")
        meas.register_custom_parameter("threshold2", label="V")
        meas.register_custom_parameter("total_counts1", label="counts")
        meas.register_custom_parameter("total_counts2", label="counts")
        meas.register_custom_parameter("counts1")
        meas.register_custom_parameter("counts2")
        meas.register_custom_parameter("trace_time", label="s")
        meas.register_custom_parameter("meas_time", label="s")
        meas.register_custom_parameter("interval", label="s")
        meas.register_custom_parameter("CR1", label="cps", setpoints=(yoko.current,))
        meas.register_custom_parameter("CR2", label="cps", setpoints=(yoko.current,))
        meas.register_custom_parameter("n_captures")
        meas.register_custom_parameter("power90", label="W")
        meas.register_custom_parameter("trigger", label="V")
        meas.register_custom_parameter('v_scale', label='V')

        # TODO: should I save the temperature? 
        
        with meas.run() as datasaver:
            print(datasaver.run_id)
            
            # save device name 
            datasaver.dataset.add_metadata("device", device_name)
            
            # Extract the amount of time in one trace 
            h_time = osc.horizontal_scale()*osc.horizontal_divisions()
            
            time.sleep(2)

            idx_list = range(len(currents)) if idx_list is None else idx_list

            for idx in tqdm.tqdm(idx_list):
                
                # Set current 
                yoko.current(currents[idx])
                time.sleep(2)

                # Set thresholds on oscilloscope   
                osc.write(f'SEARCH:SEARCH1:TRIGger:A:EDGE:THReshold {threshold1[idx]}')
                osc.write(f'SEARCH:SEARCH2:TRIGger:A:EDGE:THReshold {threshold2[idx]}')

                # Set corresponding vertical scaling 
                osc.channels[0].vertical_scale(v_scale[idx])

                print(osc.channels[0].vertical_scale())

                # Set trigger
                osc.trigger_channels[0].ch1_trigger_level(trigger)

                time.sleep(5)

                if osc.channels[0].clipping(): 
                    raise Exception('Error: Clipping') 

                time.sleep(5)

                # Run count 
                osc.write("SEARCH:SEARCH1:STATE 0")
                osc.write("SEARCH:SEARCH1:STATE 1")
                osc.write("SEARCH:SEARCH2:STATE 0")
                osc.write("SEARCH:SEARCH2:STATE 1")

                start = time.perf_counter()
                print(f'This acquisition will take {n_captures*interval}s')
                print(datetime.datetime.now().hour,  datetime.datetime.now().minute)

                counts1= []
                counts2= []

                
                for i in range(n_captures):
                    time.sleep(interval)

                    # Extract counts 
                    count1 = int(osc.ask("SEARCH:SEARCH1:TOTal?"))
                    count2 = int(osc.ask("SEARCH:SEARCH2:TOTal?"))

                    counts1.append(count1)
                    counts2.append(count2)

                    
                # calculate total counts 
                total_counts1 = sum(counts1)
                total_counts2 = sum(counts2)
                
                # total time in measurement 
                meas_time = n_captures*h_time
                
                # dark count rate calculation
                CR1 = total_counts1/meas_time
                CR2 = total_counts2/meas_time
                
                # Save data 
                datasaver.add_result((yoko.current, yoko.current()),
                                    (dmm.volt, dmm.volt()),
                                    ("threshold1",  float(osc.ask(f'SEARCH:SEARCH1:TRIGger:A:EDGE:THReshold?'))), 
                                    ("threshold2",  float(osc.ask(f'SEARCH:SEARCH2:TRIGger:A:EDGE:THReshold?'))), 
                                    ("total_counts1", total_counts1), 
                                    ("total_counts2", total_counts2), 
                                    ("counts1", counts1), 
                                    ("counts2", counts2), 
                                    ("meas_time", meas_time), 
                                    ("interval", interval), 
                                    ("n_captures", n_captures),
                                    ("CR1", CR1), 
                                    ("CR2", CR2),
                                    ('v_attenuator', float(self.p_att.ask('VOLT?'))),
                                    ('wavelength', spc.c/self.laser.frequency_coarse()), 
                                    ("power90", pmeter90.power()),
                                    ('trigger', osc.trigger_channels[0].ch1_trigger_level()),
                                    ("v_scale", float(osc.channels[0].vertical_scale())))
        # Unlatch at the end
        self.unlatch(yoko)
    
    def capture_trace(self, MS, trigger, v_scale, wait=120, station=None):
        ''' Parameters 
        '''
        # TODO: should arrange this like the segmented capture like in an xarray, with metadata
        # for each segment of data

        if not int(MS.ask('ACQUIRE:STATE?')): 
            raise Exception('Acquisition state is not 1')
    
        # Change to Single Trigger 
        MS.write('ACQUIRE:STOPAFTER SEQUENCE')
        MS.write('ACQUIRE:STATE ON')
        # MS.write('*OPC?')

        # Set parameters for trace capture using set standard functon 
        self.MSO5_set_standard_trace(MS)
        print('Oscilloscope set for trace capture')
        time.sleep(2)

        # Adjust trigger for trace capture
        MS.trigger_channels[0].ch1_trigger_level(trigger)
        print(v_scale)
        MS.channels[0].vertical_scale(v_scale)

        # Update experiment snapshot 
        self.update_station(station)


        start = time.perf_counter()
        while int(MS.ask('ACQUIRE:STATE?')): # state should return 0 if acquisition is stopped and a trace is captured
            time.sleep(2)
            if time.perf_counter()-start > wait: # if waiting for more than some value
                break
        
        print(f'Acquisition took {time.perf_counter()-start:.2f} seconds')
    
        try: 
            waveform = MS.waveform_data()
        except pyvisa.errors.VisaIOError:
            MS.write('ACQUIRE:STOPAFTER RUNSTOP')
            MS.write('ACQUIRE:STATE ON')
            time.sleep(5)

        waveform = MS.waveform_data()
        print(MS.ask('WFMOutpre?'))
        h_samples = int(MS.ask('HORizontal:MODe:RECOrdlength?'))
        h_samplerate = float(MS.ask('HORizontal:MODe:SAMPLERate?'))
        h_position_perc = float(MS.ask('HORizontal:POSition?')) # percentage of trace 
        h_centre = h_samples*h_position_perc/100
        time_axis = (np.arange(0, h_samples, 1) - h_centre)/h_samplerate
        trigger = MS.trigger_channels[0].ch1_trigger_level()
        v_scale = float(MS.channels[0].vertical_scale())
        peaks, _ = find_peaks(waveform, height=float(trigger), distance=len(waveform))
        v_peak = waveform[peaks]       
               
        time.sleep(5)
        
        # Revert to runstop 
        MS.write('ACQUIRE:STOPAFTER RUNSTOP')
        MS.write('ACQUIRE:STATE ON')

        return waveform, h_samples, h_samplerate, h_position_perc, h_centre, time_axis, trigger, v_scale, v_peak

    def single_trace_capture(self, device, MS, dmm, yoko, p_att, trigger, v_scale, wait=120, station=None):
        ''' Parameters 
        '''
        # TODO: should arrange this like the segmented capture like in an xarray, with metadata
        # for each segment of data


        # Set parameters for trace capture using set standard functon 
        self.MSO5_set_standard_trace(MS)
        print('Oscilloscope set for trace capture')
        time.sleep(2)

        # Adjust trigger for trace capture
        MS.trigger_channels[0].ch1_trigger_level(trigger)
        MS.channels[0].vertical_scale(v_scale)

        # Update experiment snapshot 
        self.update_station(station)
        
        meas = Measurement()
        meas.register_custom_parameter("time_axis", label="time_axis")
        meas.register_custom_parameter("trace", label="trace", setpoints=("time_axis", ))
        meas.register_custom_parameter("h_samples", label="samples")
        meas.register_custom_parameter("h_centre", label="samples")
        meas.register_custom_parameter("h_samplerate", label="samples/sec")
        meas.register_custom_parameter("h_position_perc", label="samples")
        meas.register_parameter(dmm.volt)
        meas.register_parameter(yoko.current) # minimise number of things required in a global namespace 
        meas.register_custom_parameter("v_attenuator", label="V")
        meas.register_custom_parameter('trigger', label='V')
        meas.register_custom_parameter('v_scale', label='V')
        meas.register_custom_parameter('v_peak', label='V')

        
        with meas.run() as datasaver:
            print(datasaver.run_id)

            datasaver.dataset.add_metadata("device", device['name'])
            print(v_scale)
            waveform, h_samples, h_samplerate, h_position_perc, h_centre, time_axis, trigger, v_scale, v_peak = self.capture_trace(MS, trigger, v_scale, wait)

            datasaver.add_result(("trace", waveform),
                        ("time_axis", time_axis),
                        (yoko.current, yoko.current()), 
                        ("h_samplerate", h_samplerate), 
                        ("h_samples", h_samples),
                        ("h_position_perc", h_position_perc),
                        ("h_centre", h_centre),
                        (dmm.volt, dmm.volt()),
                        ('v_attenuator', float(p_att.ask('VOLT?'))),
                        ('trigger',  MS.trigger_channels[0].ch1_trigger_level()),
                        ("v_scale", float(MS.channels[0].vertical_scale())),
                        ('v_peak', v_peak))
                        # ("laser_status", str(self.laser.enable())))
                        # TODO: should uncomment that and make it work ^

    def trace_vs_current(self, device, MS, dmm, yoko, trigger, v_scale, wait=120, currents=None, unlatch=True, station=None):
        ''' Parameters 
        '''
        # TODO: should arrange this like the segmented capture like in an xarray, with metadata
        # for each segment of data

        currents = device['currents'] if currents is None else currents

        # TODO: clean up these if statements 

        # Build lists for trace capture 
        if type(trigger) is list: 
            if len(trigger) is not len(currents):
                raise Exception('We don\'t have one trigger value per current')
            trigger_list = trigger
            print('list is trigger')
        else: 
            trigger_list = np.ones_like(currents)*trigger
            print('single trigger value')

        if type(v_scale) is list: 
            if len(v_scale) is not len(currents):
                raise Exception('We don\'t have one v_scale value per current')
            v_scale_list = v_scale
        else: 
            v_scale_list = np.ones_like(currents)*v_scale
            print('single vscale value')
            
        # Update experiment snapshot 
        self.update_station(station)
        
        meas = Measurement()
        meas.register_custom_parameter("time_axis", label="time_axis")
        meas.register_custom_parameter("trace", label="trace", setpoints=("time_axis", ))
        meas.register_custom_parameter("h_samples", label="samples")
        meas.register_custom_parameter("h_centre", label="samples")
        meas.register_custom_parameter("h_samplerate", label="samples/sec")
        meas.register_custom_parameter("h_position_perc", label="samples")
        meas.register_parameter(dmm.volt)
        meas.register_parameter(yoko.current) # minimise number of things required in a global namespace 
        meas.register_custom_parameter("v_attenuator", label="V")
        meas.register_custom_parameter('trigger', label='V')
        meas.register_custom_parameter('v_scale', label='V')
        meas.register_custom_parameter('v_peak', label='V')

        # Ramp to zero and wait 
        if unlatch:
            self.unlatch(yoko)
        
        # Ramp to start current 
        self.ramp_yoko_current(yoko, target=currents[0], step=0.5e-6)
        yoko.current(currents[0])

        with meas.run() as datasaver:
            print(datasaver.run_id)

            for idx in tqdm.tqdm(range(len(currents))): 
                yoko.current(currents[idx])
                # Adjust trigger for trace capture

                datasaver.dataset.add_metadata("device", device['name'])

                waveform, h_samples, h_samplerate, h_position_perc, h_centre, time_axis, trigger, v_scale, v_peak = self.capture_trace(MS, trigger=trigger_list[idx], wait=wait, v_scale=v_scale_list[idx])

                datasaver.add_result(("trace", [waveform]),
                            ("time_axis", [time_axis]),
                            (yoko.current, yoko.current()), 
                            ("h_samplerate", h_samplerate), 
                            ("h_samples", h_samples),
                            ("h_position_perc", h_position_perc),
                            ("h_centre", h_centre),
                            (dmm.volt, dmm.volt()),
                            ('v_attenuator', 3),
                            # ('v_attenuator', float(p_att.ask('VOLT?'))),
                            ('trigger',  trigger),
                            ("v_scale", v_scale),
                            ('v_peak', v_peak))
                            # ("laser_status", str(self.laser.enable())))
                            # TODO: should uncomment that and make it work ^
        
        # Ramp to zero and wait 
        if unlatch:
            self.unlatch(yoko)   

    def MSO5_counts_vs_attenuation(self, MS, dmm, yoko, p_att, pmeter90, device, v_att_range, n_captures=10, interval=1, current=None, thresholds=None,  station=None):
        '''
        interval is specified in seconds. FOr MSO5 must be minimum 1s
        '''
        if interval <1: 
            raise Exception('interval must be greater than or equal to 1s')
        # This was based on 

        # TODO: include exception for if the wrong oscilloscope is used in this function
        # idn = osc.get_idn()
        # if idn['model'] != 'MSO5':
        #         raise Exception('Connected oscilloscope is not a Tektronix MSO5.')

        # Unpack parameters for device 
        device_name = device['name']
        
        if thresholds is None: 
            thresholds = device['thresholds']
        
        pmeter90 = self.pms120 if pmeter90 is None else pmeter90

        print('Set standard oscilloscope parameters for counts')
        self.MSO5_set_standard_counts(device, MS)
        time.sleep(2)

        # Update station
        self.update_station(station)

        # Establish measurement
        meas = Measurement()
        meas.register_parameter(dmm.volt)
        meas.register_parameter(yoko.current)
        meas.register_custom_parameter("threshold1", label="V")
        meas.register_custom_parameter("threshold2", label="V")
        meas.register_custom_parameter("total_counts1", label="counts")
        meas.register_custom_parameter("total_counts2", label="counts")
        meas.register_custom_parameter("counts1")
        meas.register_custom_parameter("counts2")
        meas.register_custom_parameter("trace_time", label="s")
        meas.register_custom_parameter("meas_time", label="s")
        meas.register_custom_parameter("interval", label="s")
        meas.register_custom_parameter("v_attenuator", label="V")
        meas.register_custom_parameter("CR1", label="cps", setpoints=("v_attenuator",))
        meas.register_custom_parameter("CR2", label="cps", setpoints=("v_attenuator",))
        meas.register_custom_parameter("n_captures")
        meas.register_custom_parameter("wavelength", label="m")
        meas.register_custom_parameter("pmeter90", label="W")
        meas.register_custom_parameter('v_scale', label='V')
        

        with meas.run() as datasaver:
            print(datasaver.run_id)
            
            # save device name 
            datasaver.dataset.add_metadata("device", device_name)
            
            # Set attenuator to max value
            p_att.write(f'VOLT {v_att_range[-1]}')
            time.sleep(5)
            
        
        
            # Set current
            yoko.current(current)
            time.sleep(1)
            print(f'Current is {yoko.current()}')

            if MS.channels[0].clipping(): 
                print('Error: Clipping')

            # Extract the amount of time in one trace 
            h_time = MS.horizontal_scale()*MS.horizontal_divisions()

            for v in v_att_range[::-1]: # <- sweep voltage applied to attenuator
                
                p_att.write(f'VOLT {v}')
                time.sleep(1)
                print(f'Starting V={p_att.ask('VOLT?')}')
                
                ### ADDED NEW THRESHOLDS with scaling ###
                # Setting thresholds 
                threshold1, threshold2, v_scale = self.set_thresholds(MS, yoko, thresholds)

                # Set thresholds on oscilloscope   
                MS.write(f'SEARCH:SEARCH1:TRIGger:A:EDGE:THReshold {threshold1}')
                MS.write(f'SEARCH:SEARCH2:TRIGger:A:EDGE:THReshold {threshold2}')

                # Set corresponding vertical scaling 
                MS.channels[0].vertical_scale(v_scale)

                print(MS.channels[0].vertical_scale( ))

                ######

                time.sleep(5)

                # Run count 
                MS.write("SEARCH:SEARCH1:STATE 0")
                MS.write("SEARCH:SEARCH1:STATE 1")
                MS.write("SEARCH:SEARCH2:STATE 0")
                MS.write("SEARCH:SEARCH2:STATE 1")

                start = time.perf_counter()
                print(f'This acquisition will take {n_captures*interval}s')
                print(datetime.datetime.now().hour,  datetime.datetime.now().minute)

                counts1= []
                counts2= []

                
                for i in range(n_captures):
                    time.sleep(interval)

                    # Extract counts 
                    count1 = int(MS.ask("SEARCH:SEARCH1:TOTal?"))
                    count2 = int(MS.ask("SEARCH:SEARCH2:TOTal?"))

                    counts1.append(count1)
                    counts2.append(count2)

                    
                # calculate total counts 
                total_counts1 = sum(counts1)
                total_counts2 = sum(counts2)
                
                # total time in measurement 
                meas_time = n_captures*h_time
                
                # dark count rate calculation
                CR1 = total_counts1/meas_time
                CR2 = total_counts2/meas_time
                
                # Save data 
                datasaver.add_result((yoko.current, yoko.current()),
                                    (dmm.volt, dmm.volt()),
                                    ("threshold1", float(MS.ask(f'SEARCH:SEARCH1:TRIGger:A:EDGE:THReshold?'))), 
                                    ("threshold2", float(MS.ask(f'SEARCH:SEARCH2:TRIGger:A:EDGE:THReshold?'))), 
                                    ("total_counts1", total_counts1), 
                                    ("total_counts2", total_counts2), 
                                    ("counts1", counts1), 
                                    ("counts2", counts2), 
                                    ("meas_time", meas_time), 
                                    ("interval", interval), 
                                    ("n_captures", n_captures),
                                    ("CR1", CR1), 
                                    ("CR2", CR2), 
                                    ("v_attenuator", v),
                                    ('wavelength', spc.c/self.laser.frequency_coarse()), 
                                    ("pmeter90", pmeter90.power()),
                                    ("v_scale", float(MS.channels[0].vertical_scale())))


    def set_thresholds(self, yoko, device, read_current=True, current=None):
        '''Function extracts threshold1, threshold2 and vertical scale depending on yokogawa current
        '''
        currents = device['currents']
        threshold1 = device['threshold1']
        threshold2 = device['threshold2']
        v_scale = device['v_scale']

        # TODO: check that the lengths are the same!!!! Otherwise indexing won't be right 
        if read_current:
            current = yoko.current()
            time.sleep(2)
        else: 
            if current is None: 
                raise Exception('If not reading from yoko, current value must be passed')

        # match current to instrument, would have to extract index 
        idx, _ = self.match(test=current, val_array=currents) 
        # ^ function automatically sets tolerance to be half of the difference between the first two values in array


        return threshold1[idx], threshold2[idx], v_scale[idx]
        

    
    def ramp_yoko_current(self, yoko, target, step):
        if step <=0: 
            raise Exception('This function requires positive step')
        print(f'Ramping to {target}')
        start = yoko.current()
        step = step if target > start else -step
        currents = np.arange(start, target+step, step)
        for curr in currents: 
            yoko.current(curr)
            time.sleep(1)
    
    def counts_vs_wavelength(self, MS, dmm, yoko, p_att, laser, pmeter90, device, n_captures, interval, wavelength_range, thresholds=None, station=None):
        '''
        interval is specified in seconds
        '''

        if interval <1: 
            raise Exception('interval must be greater than or equal to 1s')
        # This was based on 

        # TODO: include exception for if the wrong oscilloscope is used in this function
        # idn = osc.get_idn()
        # if idn['model'] != 'MSO5':
        #         raise Exception('Connected oscilloscope is not a Tektronix MSO5.')

        # Unpack parameters for device 
        device_name = device['name']
        
        if thresholds is None: 
            thresholds = device['thresholds']

        print('Set standard oscilloscope parameters for counts')
        self.MSO5_set_standard_counts(device=device, MS=MS)
        time.sleep(2)

        # Update station
        self.update_station(station)


        # Establish measurement
        meas = Measurement()
        meas.register_parameter(dmm.volt)
        meas.register_parameter(yoko.current)
        meas.register_custom_parameter("threshold1", label="V")
        meas.register_custom_parameter("threshold2", label="V")
        meas.register_custom_parameter("total_counts1", label="counts")
        meas.register_custom_parameter("total_counts2", label="counts")
        meas.register_custom_parameter("counts1")
        meas.register_custom_parameter("counts2")
        meas.register_custom_parameter("meas_time", label="s")
        meas.register_custom_parameter("interval", label="s")
        meas.register_custom_parameter("n_captures", label="s")
        meas.register_custom_parameter("CR1", label="cps")
        meas.register_custom_parameter("CR2", label="cps")
        meas.register_custom_parameter("v_attenuator", label="V")
        meas.register_custom_parameter("wavelength", label="nm")
        meas.register_custom_parameter("pmeter90", label="W")
        meas.register_custom_parameter('v_scale', label='V')



        with meas.run() as datasaver:
            print(datasaver.run_id)
            
            # save device name 
            datasaver.dataset.add_metadata("device", device_name)

            if MS.channels[0].clipping(): 
                raise Exception('Error: Clipping')


            for wav in wavelength_range: # <- sweep wavelength of laser 


                # Start with laser off 
                ############################ TURN LASER OFF ############################ 
                laser.enable(False)
                print(f'Laser enable status: {laser.enable()}')

                print(wav)

                # Set wavelength of laser and powermeters
                self.laser_set_standard(laser, wavelength=wav, power=7)
                self.laser_get_standard(laser)
                self.pmeter_set_standard(pmeter=pmeter90, wavelength=wav)

                # ############################ TURN LASER ON ############################ 
                laser.enable(True)
                print(f'Laser enable status: {laser.enable()}')
                time.sleep(20) 


                # Extract the amount of time in one trace 
                h_time = MS.horizontal_scale()*MS.horizontal_divisions()
        
                
                ### ADDED NEW THRESHOLDS with scaling ###
                # Setting thresholds 
                threshold1, threshold2, v_scale = self.set_thresholds(MS, yoko, thresholds)

                # Set thresholds on oscilloscope   
                MS.write(f'SEARCH:SEARCH1:TRIGger:A:EDGE:THReshold {threshold1}')
                MS.write(f'SEARCH:SEARCH2:TRIGger:A:EDGE:THReshold {threshold2}')

                # Set corresponding vertical scaling 
                MS.channels[0].vertical_scale(v_scale)

                print(MS.channels[0].vertical_scale( ))

                ######

                time.sleep(5)

                # Run count 
                MS.write("SEARCH:SEARCH1:STATE 0")
                MS.write("SEARCH:SEARCH1:STATE 1")
                MS.write("SEARCH:SEARCH2:STATE 0")
                MS.write("SEARCH:SEARCH2:STATE 1")

                start = time.perf_counter()
                print(f'This acquisition will take {n_captures*interval}s')
                print(datetime.datetime.now().hour,  datetime.datetime.now().minute)

                counts1= []
                counts2= []

                
                for i in range(n_captures):
                    time.sleep(interval)

                    # Extract counts 
                    count1 = int(MS.ask("SEARCH:SEARCH1:TOTal?"))
                    count2 = int(MS.ask("SEARCH:SEARCH2:TOTal?"))

                    counts1.append(count1)
                    counts2.append(count2)

                    
                # calculate total counts 
                total_counts1 = sum(counts1)
                total_counts2 = sum(counts2)
                
                # total time in measurement 
                meas_time = n_captures*h_time
                
                # dark count rate calculation
                CR1 = total_counts1/meas_time
                CR2 = total_counts2/meas_time
            
                
                # Save data 
                datasaver.add_result((yoko.current, yoko.current()),
                                    (dmm.volt, dmm.volt()),
                                    ("threshold1",  float(MS.ask(f'SEARCH:SEARCH1:TRIGger:A:EDGE:THReshold?'))), 
                                    ("threshold2", float(MS.ask(f'SEARCH:SEARCH2:TRIGger:A:EDGE:THReshold?'))), 
                                    ("total_counts1", total_counts1), 
                                    ("total_counts2", total_counts2), 
                                    ("counts1", counts1), 
                                    ("counts2", counts2), 
                                    ("meas_time", meas_time), 
                                    ("interval", interval), 
                                    ("n_captures", n_captures),
                                    ("CR1", CR1), 
                                    ("CR2", CR2), 
                                    ("v_attenuator", float(p_att.ask('VOLT?'))), 
                                    ('wavelength', wav),
                                    ("pmeter90", pmeter90.power()),
                                    ("v_scale", float(MS.channels[0].vertical_scale())))
            

    def match(self, test, val_array, tol=None): 
        #TODO: add functionality to allow for descendign values!! 
        """Test is to get the value 
        """
        flag=False
        if test <0: 
            flag=True
        test_pos = np.abs(test)
        val_array = np.abs(val_array)
        if tol is None: 
            # Set tolerance of index search based on steps between currents 
            tol = np.diff(val_array)[0]/2
        
        val = val_array[(val_array > (test_pos-tol)) & (val_array < (test_pos+tol))]
        idx = np.where((val_array > (test_pos-tol)) & (val_array < (test_pos + tol)))
        
        val_out = -val if flag else val
        print(f'Check match:{test} (test) = {val_out}?')
        return int(idx[0][0]), val_out
    
    def make_title(self, title, ID, extra=None):
        timestamp = load_by_id(ID).run_timestamp()
        device_name = load_by_id(ID).metadata['device']
        s = f'{title} {device_name}\nID {ID} {timestamp}'
        if extra is not None:
            s += f'\n{extra}'
        return s

    def plot_critical_current(self, ID, ratio=False, extra=None): 
        data = load_by_id(ID).get_parameter_data()
        current = data['dmm_volt']['yoko_current']
        voltage = data['dmm_volt']['dmm_volt']
        temp = data['MC_temp']['MC_temp']

        s_extra = f'Avg. Tmxc: {np.average(temp)*1e3:.2f}mK'
        if extra is not None:
            s_extra += f'\n{extra}'

        plt.plot(current, voltage, '.')
        title = self.make_title(title=f'Voltage vs Current', ID=ID, extra=s_extra)
        plt.title(title)
        plt.xlabel('Current (A)')
        plt.ylabel('Voltage (V)')

        return 
    
    # TODO: once there is a way to save traces without using multiple IDs change the way data is read in here 
    def generate_dataframe(self, IDrange, mult1, mult2, min_threshold2, min_threshold1, min_peak_voltage):
        # TODO: the way this needs IDs in the right order is not very useful!! 
        data_dict = {}
        for ID in IDrange: 
            data = load_by_id(ID).get_parameter_data()
            trace = data['trace']['trace']
            current = data['yoko_current']['yoko_current'][0]
            trigger = data['trigger']['trigger'][0]
            peaks, properties = find_peaks(trace, height=float(trigger), distance=len(trace))
            key = f'{current*1e6:.2f}'

            peak_voltage = 0 if len(peaks)<1 else trace[peaks][0]

            # Set vertical scale based on minimum peak voltage or actual peak voltage
            v_scale = min_peak_voltage/2 if peak_voltage < min_peak_voltage else peak_voltage/2
            test_peak_voltage = min_peak_voltage if peak_voltage < min_peak_voltage else peak_voltage

            threshold1 = mult1*peak_voltage

            threshold2 = mult2*peak_voltage

            if threshold1 < min_threshold1: 
                threshold1 = min_threshold1
            
            if threshold2 < min_threshold2: 
                threshold2 = min_threshold2 
            
            try: 
                v_scale_measured = data['v_scale']['v_scale'][0]
            except KeyError: 
                v_scale_measured = None
            try: 
                data_dict[key]
                print(f'duplicate current {key} ID {ID}')
            except: 
                data_dict[key] = {'current': current, 
                                'trigger': trigger,
                                'v_scale_measured': v_scale_measured,
                                'peak_voltage': peak_voltage,
                                'test_peak_voltage': test_peak_voltage,
                                'threshold1': threshold1,
                                'threshold2': threshold2, # does it matter if these are not a multiple of the minimum v_scale_measured?
                                'v_scale': v_scale,
                                'ID': int(ID),
                                }
        return pd.DataFrame(data=data_dict)


    def args(self,function):
        import inspect
        print(inspect.signature(function))
    
    def pulse_test_calibration(self, IDrange, mult1, mult2, min_threshold2, min_threshold1, min_peak_voltage, device, osc, awg, cps, n_captures=10, interval=1, trigger=0, station=None):
        # TODO: Should integrate the pulse test with the data generation. 
        
        '''
        interval is specified in seconds. FOr MSO5 must be minimum 1s
        '''

        # Generate data 
        data = self.generate_dataframe(IDrange, mult1, mult2, min_threshold2, min_threshold1, min_peak_voltage)

        if interval <1: 
            raise Exception('interval must be greater than or equal to 1s')
        
        print('Set standard oscilloscope parameters for counts')
        self.MSO5_set_standard_counts(device, osc)
        time.sleep(2)
        
        # Update experiment snapshot 
        self.update_station(station)
        
        meas = Measurement()
        meas.register_custom_parameter("current", label="A")
        meas.register_custom_parameter("threshold1", label="V")
        meas.register_custom_parameter("threshold2", label="V")
        meas.register_custom_parameter("total_counts1", label="counts")
        meas.register_custom_parameter("total_counts2", label="counts")
        meas.register_custom_parameter("counts1")
        meas.register_custom_parameter("counts2")
        meas.register_custom_parameter("trace_time", label="s")
        meas.register_custom_parameter("meas_time", label="s")
        meas.register_custom_parameter("interval", label="s")
        meas.register_custom_parameter("CR1", label="cps", setpoints=('current',))
        meas.register_custom_parameter("CR2", label="cps", setpoints=('current',))
        meas.register_custom_parameter("n_captures")
        meas.register_custom_parameter('v_scale_set', label='V') # <- added for testing purposes 
        meas.register_custom_parameter('v_scale', label='V')
        meas.register_custom_parameter('frequency', label='Hz')
        meas.register_custom_parameter('amplitude', label='Vpp')
        meas.register_custom_parameter('trigger', label='V')
        
        
        with meas.run() as datasaver:
            print(datasaver.run_id)
            
            # save device name 
            datasaver.dataset.add_metadata("device", device['name'])
            
            # Extract the amount of time in one trace 
            h_time = osc.horizontal_scale()*osc.horizontal_divisions()
            
            time.sleep(2)
        
            for key in data.keys(): 
                current = data[key]['current']
                threshold1 = data[key]['threshold1']
                threshold2 = data[key]['threshold2']
                v_scale = data[key]['v_scale']
                test_peak_voltage = data[key]['test_peak_voltage']
                

                # minimum rise, fall and width parameters 
                rise = 8.4e-9
                fall = 8.4e-9
                width = 16e-9

                # Set AWG parameters 
                awg.write('SOURCE1:VOLT:UNIT Vpp')
                awg.write(f'SOURCE1:VOLT:OFFSET {test_peak_voltage/2}')
                awg.write(f'FUNC PULS')
                awg.write(f'FUNC:PULS:TRAN:LEAD {rise}')
                awg.write(f'FUNC:PULS:TRAN:TRA {fall}')
                awg.write(f'FUNC:PULS:WIDT {width}')
                awg.write(f'FREQ {cps}')
                awg.write(f'VOLT {test_peak_voltage}')
                awg.write('OUTP ON')

                #TODO: consistent naming of the oscilloscope!!!!
                
                # Set thresholds and vertical scale 
                osc.write(f'SEARCH:SEARCH1:TRIGger:A:EDGE:THReshold {threshold1}')
                osc.write(f'SEARCH:SEARCH2:TRIGger:A:EDGE:THReshold {threshold2}')
                osc.channels[0].vertical_scale(v_scale)
                osc.trigger_channels[0].ch1_trigger_level(trigger) 
        
                time.sleep(5)
        
                if osc.channels[0].clipping(): 
                    raise Exception('Error: Clipping') 
        
                time.sleep(5)
        
                osc.write("SEARCH:SEARCH1:STATE 0")
                osc.write("SEARCH:SEARCH1:STATE 1")
                osc.write("SEARCH:SEARCH2:STATE 0")
                osc.write("SEARCH:SEARCH2:STATE 1")
        
                start = time.perf_counter()
                print(f'This acquisition will take {n_captures*interval}s')
                print(datetime.datetime.now().hour,  datetime.datetime.now().minute)
        
                counts1= []
                counts2= []
        
                
                for i in range(n_captures):
                    time.sleep(interval)
        
                    # Extract counts 
                    count1 = int(osc.ask("SEARCH:SEARCH1:TOTal?"))
                    count2 = int(osc.ask("SEARCH:SEARCH2:TOTal?"))
        
                    counts1.append(count1)
                    counts2.append(count2)
        
                    
                # calculate total counts 
                total_counts1 = sum(counts1)
                total_counts2 = sum(counts2)
                
                # total time in measurement 
                meas_time = n_captures*h_time
                
                # dark count rate calculation
                CR1 = total_counts1/meas_time
                CR2 = total_counts2/meas_time
                
                # Save data 
                datasaver.add_result(('current', current),
                                    ("threshold1",  float(osc.ask(f'SEARCH:SEARCH1:TRIGger:A:EDGE:THReshold?'))), 
                                    ("threshold2",  float(osc.ask(f'SEARCH:SEARCH2:TRIGger:A:EDGE:THReshold?'))), 
                                    ("total_counts1", total_counts1), 
                                    ("total_counts2", total_counts2), 
                                    ("counts1", counts1), 
                                    ("counts2", counts2), 
                                    ("meas_time", meas_time), 
                                    ("interval", interval), 
                                    ("n_captures", n_captures),
                                    ("CR1", CR1), 
                                    ("CR2", CR2),
                                    ('trigger', osc.trigger_channels[0].ch1_trigger_level()),
                                    ('v_scale_set', v_scale),
                                    ("v_scale", float(osc.channels[0].vertical_scale())),
                                    ("frequency", float(awg.query('FREQ?'))),
                                    ("amplitude", float(awg.query('VOLT?'))))
    
    def critical_current_setv(self, device, Rb, dmm=None, yoko=None, voltages=None, station=None):
        # Note: tc was removed from this function because of an IT issue
    
        import tqdm

        if yoko.source_mode() != 'VOLT': 
            raise Exception('Yoko is not in voltage mode')
        
        # Read from station internally unless an instrument is passed 
        yoko = self.yoko if yoko is None else yoko
        dmm = self.dmm if dmm is None else dmm 
        # tc = params.tc if tc is None else tc 

        # Update station
        self.update_station(station)

        # Establish measurement
        meas = Measurement()
        meas.register_parameter(yoko.voltage)
        meas.register_parameter(dmm.volt, setpoints=(yoko.voltage,))
        # meas.register_custom_parameter("MC_temp", label="K")
        meas.register_custom_parameter("Rbias", label="Ohms")

        # Set first current 
        if yoko.voltage() != voltages[0]: 
            raise Exception('Ramp to first voltage value')
       

        with meas.run() as datasaver:
            print(datasaver.run_id)
            
            # save device name 
            datasaver.dataset.add_metadata("device", device['name'])


            for v in tqdm.tqdm(voltages): 

                # set current 
                yoko.voltage(v)
                time.sleep(1)
                print(f'Starting voltage {yoko.voltage()}')

                # Save data 
                datasaver.add_result((yoko.voltage, yoko.voltage()),
                                    (dmm.volt, dmm.volt()),
                                    # ("MC_temp", tc.MC_temp()),
                                    ("Rbias", Rb))
                
                time.sleep(10)
        
        # Ramp to zero and wait 
        print('Unlatch, ramp to zero and wait') 
        for v in voltages[::-1]: 
            yoko.voltage(v)
            time.sleep(1)
        time.sleep(30)
        
    def trace_vs_voltage(self, device, Rbias, voltages, MS, dmm, yoko, p_att, trigger, v_scale, wait=120, station=None):
        ''' Parameters 
        '''
        import tqdm
        # for each segment of data
        if yoko.source_mode() != 'VOLT': 
            raise Exception('Yoko is not in voltage mode')
            
        # Set first current 
        if yoko.voltage() != voltages[0]: 
            raise Exception('Ramp to first voltage value')

        # Update experiment snapshot 
        self.update_station(station)
        
        meas = Measurement()
        meas.register_custom_parameter("time_axis", label="time_axis")
        meas.register_custom_parameter("trace", label="trace", setpoints=("time_axis", ))
        meas.register_custom_parameter("h_samples", label="samples")
        meas.register_custom_parameter("h_centre", label="samples")
        meas.register_custom_parameter("h_samplerate", label="samples/sec")
        meas.register_custom_parameter("h_position_perc", label="samples")
        meas.register_parameter(dmm.volt)
        meas.register_parameter(yoko.voltage) # minimise number of things required in a global namespace 
        meas.register_custom_parameter("v_attenuator", label="V")
        meas.register_custom_parameter('trigger', label='V')
        meas.register_custom_parameter('v_scale', label='V')
        meas.register_custom_parameter('v_peak', label='V')
        meas.register_custom_parameter('Rbias', label='Ohms')
        
        with meas.run() as datasaver:
            print(datasaver.run_id)

            for (idx, v) in tqdm.tqdm(enumerate(voltages)): 
                yoko.voltage(v)
                
                datasaver.dataset.add_metadata("device", device['name'])
                
                waveform, h_samples, h_samplerate, h_position_perc, h_centre, time_axis, trigger, v_scale, v_peak = self.capture_trace(MS, trigger, v_scale, wait)

                datasaver.add_result(("trace", waveform),
                            ("time_axis", time_axis),
                            (yoko.voltage, yoko.voltage()), 
                            ("h_samplerate", h_samplerate), 
                            ("h_samples", h_samples),
                            ("h_position_perc", h_position_perc),
                            ("h_centre", h_centre),
                            (dmm.volt, dmm.volt()),
                            ('v_attenuator', float(p_att.ask('VOLT?'))),
                            ('trigger',  MS.trigger_channels[0].ch1_trigger_level()),
                            ("v_scale", float(MS.channels[0].vertical_scale())),
                            ('v_peak', v_peak),
                            ('Rbias', Rbias))
            
        # Ramp to zero and wait 
        print('Unlatch, ramp to zero and wait') 
        for v in voltages[::-1]: 
            yoko.voltage(v)
            time.sleep(1)
        time.sleep(30)

    def plot_critical_current(self, ID, ratio=False, extra=None): 
        data = load_by_id(ID).get_parameter_data()
        current = data['dmm_volt']['yoko_current']
        voltage = data['dmm_volt']['dmm_volt']
        temp = data['MC_temp']['MC_temp']

        s_extra = f'Avg. Tmxc: {np.average(temp)*1e3:.2f}mK'
        if extra is not None:
            s_extra += f'\n{extra}'

        plt.plot(current, voltage)
        title = self.make_title(title=f'Voltage vs Current', ID=ID, extra=s_extra)
        plt.title(title)
        plt.xlabel('Current (A)')
        plt.ylabel('Voltage (V)')
    
    # TODO: for calibration and trace plots, use enumerate!  for (idx, val) in enumerate():

    def plot_count_calibration(self, IDrange, mult1, mult2, min_threshold2, min_threshold1, min_peak_voltage):
            from ipywidgets import interact, fixed, IntSlider
            from scipy.signal import find_peaks
            data = self.generate_dataframe(IDrange, mult1, mult2, min_threshold2, min_threshold1, min_peak_voltage)
            IDs = np.array(data.loc['ID'])
        
            def plot_traces(idx, data, ):
                ID = np.array(data.loc['ID'])[idx]
                threshold1 = np.array(data.loc['threshold1'])[idx]
                threshold2 = np.array(data.loc['threshold2'])[idx]
                peak_voltage = np.array(data.loc['peak_voltage'])[idx]
                v_scale = np.array(data.loc['v_scale'])[idx]
                
                data = load_by_id(ID).get_parameter_data()
                trace = data['trace']['trace']
                taxis = data['trace']['time_axis']
                current = data['yoko_current']['yoko_current']
                trigger = data['trigger']['trigger'][0]
                plt.plot(taxis, trace)
                peaks, _ = find_peaks(trace, height=float(trigger), distance=len(trace))
                plt.plot(taxis, np.ones_like(taxis)*float(trigger), label=f'Trigger in sweep {trigger*1e3}mV')
                plt.plot(taxis, np.ones_like(taxis)*threshold1, label=f'Threshold1 {mult1*100}% {threshold1*1e3}mV')
                plt.plot(taxis, np.ones_like(taxis)*threshold2, label=f'Threshold2 {mult2*100}% {threshold2*1e3} mV')
                plt.plot(taxis[peaks],trace[peaks], 'ro', label=f'Peak {trace[peaks]*1e3}mV')
                plt.title(f'ID: {ID} Current: {current[0]*1e6}uA\nVertical Scale: {v_scale}')
                plt.legend()
                plt.ylabel('Voltage (V)')
                plt.xlabel('Time (s)')
                    
            interact(plot_traces, idx=IntSlider(min=0, max=len(IDs), step=1, value=0,
                                            continuous_update=False), data=fixed(data))

    def set_axes_labels(self, ax, flag: str):
        if str is 'trace':
            ax.set_xlabel('Time (s)')
            ax.set_ylabel('Voltage (V)')

    def plot_trace_interactive(self, ID):
        data = load_by_id(ID).get_parameter_data()
        ax, fig = plt.subplots()
        ax.plot()
        data = load_by_id(ID).get_parameter_data()
        trace = data['trace']['trace']
        taxis = data['trace']['time_axis']
        current = data['yoko_current']['yoko_current']
        trigger = data['trigger']['trigger'][0]
        plt.plot(taxis, trace)



# def plot_dataset(

# https://microsoft.github.io/Qcodes/_modules/qcodes/dataset/plotting.html

# alldata: NamedData = _get_data_from_ds(dataset)

# # What has happened to the data when it gets to _set_data_axes_labels 

# _set_data_axes_labels(ax, data) <- modifies label associated with axis I think? 

# _make_label_for_data_axis(data, 0) <- whien this is passed, it must have already determined which parts of the dataset are the setpoints/bits you plot



# What is this Sequence[DSPPlotData] shit??? 
# def _make_label_for_data_axis(data: Sequence[DSPlotData], axis_index: int) -> str:
#     label = _get_label_of_data(data[axis_index])
#     unit = data[axis_index]["unit"]
#     return _make_axis_label(label, unit)

# def _get_label_of_data(data_dict: DSPlotData) -> str:
#     return data_dict["label"] if data_dict["label"] != "" else data_dict["name"]

