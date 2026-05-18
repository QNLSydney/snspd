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

# TODO: fix all the write string errors

class snspd:
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
        self.pm100d = self.station.load_instrument("pm100d", revive_instance=True) 
        self.pms120 = self.station.load_instrument("pms120", revive_instance=True)
        self.tc = self.station.load_instrument("fridge", revive_instance=True)
        self.p_att = self.station.load_instrument("dmm_keithley", revive_instance=True)
    
    def update_station(self, station=False):
        # Pass station = False to skip updating station 
        if station is not False: 
            # Update experiment snapshot
            _ = self.station.snapshot(update=True) # <- updates parameters in station 
            print('update station')


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

    def MSO5_set_standard_counts(self, MS=None):
        '''Input: optional argument for time on horizontal axis of oscilloscope
            Optional argument for vertical scale of oscilloscope (10 divisions, set in V/div) 
        '''
        MS = self.osc if MS is None else MS

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
    
    def MSO5_set_standard_trace(self, MS=None, device=None):
        '''Input: optional argument for time on horizontal axis of oscilloscope
            Optional argument for vertical scale of oscilloscope (10 divisions, set in V/div) 
        '''
        MS = self.osc if MS is None else MS

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


    def load_id_from_database(self, database, exp_name, sample_name, ID):
        initialise_or_create_database_at(database)

        try:
            exp = qc.load_experiment_by_name(exp_name, sample=sample_name)
        except ValueError:
            print('No such experiment')
        
        return load_by_id(ID)
    
    def critical_current(self, currents, device_name, dmm=None, yoko=None, tc=None, station=None):
        '''
        interval is specified in seconds
        '''
        # Read from station internally unless an instrument is passed 
        yoko = self.yoko if yoko is None else yoko
        dmm = self.dmm if dmm is None else dmm 
        tc = self.tc if tc is None else tc 


        # Update station
        self.update_station(station)

        # Establish measurement
        meas = Measurement()
        meas.register_parameter(yoko.current)
        meas.register_parameter(dmm.volt, setpoints=(yoko.current,))
        meas.register_custom_parameter("MC_temp", label="K")

        # Set first current
        # TODO: add ramp to first current in list and could add reverse sweep  
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

    def photon_number(self, power90, total_attenuation, v_attenuator, wavelength):

        # if total_attenuation.any() < 0: 
        #     raise ValueError("total_attenuation should be greater than 0")
        #     return 

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
    
        
    def MSO5_counts_vs_current(self, device, n_captures, interval=1, osc=None, dmm=None, yoko=None, currents=None, thresholds=None, station=None):
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
        

        # Unpack parameters for device 
        device_name = device['name']
        
        if currents is None:
            currents = device['currents']
        if thresholds is None: 
            thresholds = device['thresholds']

        print('Set standard oscilloscope parameters for counts')
        self.MSO5_set_standard_counts(osc)
        time.sleep(2)

        # Update experiment snapshot 
        self.update_station(station)

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
        meas.register_custom_parameter("CR1", label="cps", setpoints=(yoko.current,))
        meas.register_custom_parameter("CR2", label="cps", setpoints=(yoko.current,))
        meas.register_custom_parameter("n_captures")
        meas.register_custom_parameter("wavelength", label="m")
        meas.register_custom_parameter("v_attenuator", label="V")


        with meas.run() as datasaver:
            print(datasaver.run_id)
            
            # save device name 
            datasaver.dataset.add_metadata("device", device_name)
            
            # Extract the amount of time in one trace 
            h_time = osc.horizontal_scale()*osc.horizontal_divisions()
            
            time.sleep(2)


            for current in currents: # <- sweep voltage applied to attenuator
                
                # Set current 
                yoko.current(current)

                if osc.channels[0].clipping(): 
                    print('Error: Clipping')

                threshold1, threshold2 = self.set_thresholds(current, thresholds)


                # Set thresholds  
                osc.write(f'SEARCH:SEARCH1:TRIGger:A:EDGE:THReshold {threshold1}')
                osc.write(f'SEARCH:SEARCH2:TRIGger:A:EDGE:THReshold {threshold2}')

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
                                    ("threshold1", threshold1), 
                                    ("threshold2", threshold2), 
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
                                    ('wavelength', spc.c/self.laser.frequency_coarse()))

    def capture_trace(self, MS, dmm, yoko, p_att, station=None):
        ''' Parameters 
        '''

        # Set parameters for trace capture using set standard functon 
        self.MSO5_set_standard_trace(MS)
        print('Oscilloscope set for trace capture')
        time.sleep(2)

        # Update experiment snapshot 
        self.update_station(station)
        
        meas = Measurement()
        meas.register_custom_parameter("time_axis", label="time_axis")
        meas.register_custom_parameter("trace", label="trace", setpoints=("time_axis", ))
        meas.register_custom_parameter("h_samples", label="h_samples")
        meas.register_custom_parameter("h_samplerate", label="h_samplerate")
        meas.register_custom_parameter("h_position_perc", label="h_position_perc")
        meas.register_parameter(dmm.volt)
        meas.register_parameter(yoko.current) # minimise number of things required in a global namespace 
        meas.register_custom_parameter("v_attenuator", label="v_attenuator")
        
        #TODO: should set trigger level depending on currents - thresholds
        # 
        
        with meas.run() as datasaver:
            print(datasaver.run_id)
        
            waveform = MS.waveform_data()
            print(MS.ask('WFMOutpre?'))
            h_samples = int(MS.ask('HORizontal:MODe:RECOrdlength?'))
            h_samplerate = float(MS.ask('HORizontal:MODe:SAMPLERate?'))
            h_position_perc = float(MS.ask('HORizontal:POSition?')) # percentage of trace 
            h_centre = h_samples*h_position_perc/100
            time_axis = (np.arange(0, h_samples, 1) - h_centre)/h_samplerate
        
            datasaver.add_result(("trace", waveform),
                        ("time_axis", time_axis),
                        (yoko.current, yoko.current()), 
                        ("h_samplerate", h_samplerate), 
                        ("h_samples", h_samples),
                        ("h_position_perc", h_position_perc),
                        (dmm.volt, dmm.volt()),
                        ('v_attenuator', float(p_att.ask('VOLT?'))))

    def MSO5_counts_vs_attenuation(self, MS, dmm, yoko, p_att, device, v_att_range, n_captures, interval=1, current=None, thresholds=None,  station=None):
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

        print('Set standard oscilloscope parameters for counts')
        self.MSO5_set_standard_counts(MS)
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
                
                # Set thresholds based on current 
                threshold1, threshold2 = self.set_thresholds(current, thresholds)

                # Set thresholds  
                MS.write(f'SEARCH:SEARCH1:TRIGger:A:EDGE:THReshold {threshold1}')
                MS.write(f'SEARCH:SEARCH2:TRIGger:A:EDGE:THReshold {threshold2}')

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
                                    ("threshold1", threshold1), 
                                    ("threshold2", threshold2), 
                                    ("total_counts1", total_counts1), 
                                    ("total_counts2", total_counts2), 
                                    ("counts1", counts1), 
                                    ("counts2", counts2), 
                                    ("meas_time", meas_time), 
                                    ("interval", interval), 
                                    ("n_captures", n_captures),
                                    ("CR1", CR1), 
                                    ("CR2", CR2), 
                                    ("v_attenuator", v))

    def set_thresholds(self, current, thresholds):

        '''Note: currents represent lower limits
        '''
        for key in thresholds.keys():
            # check if test current magnitude is greater than each threshold 
            if np.abs(current) >= np.abs(float(thresholds[key]['current'])):
                threshold1 = float(thresholds[key]['threshold1']) # in volts
                threshold2 = float(thresholds[key]['threshold2']) # in volt
                return threshold1, threshold2
    
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
        self.MSO5_set_standard_counts(MS)
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



        with meas.run() as datasaver:
            print(datasaver.run_id)
            
            # save device name 
            datasaver.dataset.add_metadata("device", device_name)

            if MS.channels[0].clipping(): 
                print('Error: Clipping')


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
                time.sleep(10)


                # Extract the amount of time in one trace 
                h_time = MS.horizontal_scale()*MS.horizontal_divisions()
        
                
                # Set thresholds based on current 
                threshold1, threshold2 = self.set_thresholds(yoko.current(), thresholds)

                # Set thresholds  
                MS.write(f'SEARCH:SEARCH1:TRIGger:A:EDGE:THReshold {threshold1}')
                MS.write(f'SEARCH:SEARCH2:TRIGger:A:EDGE:THReshold {threshold2}')

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
                                    ("threshold1", threshold1), 
                                    ("threshold2", threshold2), 
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
                                    ('wavelength', wav))

    def match(self, test, val_array, tol=None): 
        #TODO: add functionality to allow for descendign values!! 
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
        return idx, val_out
    
    def make_title(self, title, ID, extra=None):
        timestamp = load_by_id(ID).run_timestamp()
        s = f'{title}\nID {ID} {timestamp}'
        if extra is not None:
            s += f'\n{extra}'
        return s
