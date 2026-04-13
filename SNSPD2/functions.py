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



def quick_check(bs10, bs90, pmeter10, pmeter90, attenuator_name, station=None):
    '''Input: measured transmission of beam splitter and power meter instruments
    '''
    if station is not None: 
        # Update experiment snapshot
        _ = station.snapshot(update=True) # <- updates parameters in station 
    
    meas = Measurement()
    meas.register_custom_parameter("times", label="Samples (approx. s)")
    meas.register_custom_parameter("power10", label="W")
    meas.register_custom_parameter("power90", label="W")
    meas.register_custom_parameter("attenuation", label="dB")

    with meas.run() as datasaver:
        print(datasaver.run_id)

        datasaver.dataset.add_metadata("attenuator_name", attenuator_name)

        power10 = pmeter10.power()
        power90 = pmeter90.power()
        attenuation = 10*np.log10((bs10/bs90*power90)/power10)
        time.sleep(2)

        datasaver.add_result(("power10", power10),
                ("power90", power90),
                ("attenuation", attenuation))

    return power10, power90, attenuation

def calibrate(bs10, bs90, pmeter10, pmeter90, t: int, attenuator_name, station=None):
    '''Input: measured transmission of beam splitter arms, power meter instruments, 
    t: time for which to calibrate (s)
    '''
    if station is not None: 
        # Update experiment snapshot
        _ = station.snapshot(update=True) # <- updates parameters in station 

    
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
            attenuation = 10*np.log10((bs10/bs90*power90)/power10) 

            time.sleep(0.5)
    
            datasaver.add_result(("times",i/2),
                             ("power10", power10),
                            ("power90", power90),
                            ("attenuation", attenuation))

        end = time.perf_counter()
        print(f'Finished in {end-start}s')

def osc_set_standard(MS, v_trigger=0, v_scale=50e-3, h_time=100e-3, h_pos=0):
    '''Input: optional argument for time on horizontal axis of oscilloscope
        Optional argument for vertical scale of oscilloscope (10 divisions, set in V/div) 
    '''
    MS.horizontal_mode('MANual') # set manual mode to allow parameters to be set
    MS.horizontal_mode_manual_configure('RECORDLength')
    MS.horizontal_samplerate(625e6)
    h_scale = h_time/MS.horizontal_divisions()
    MS.horizontal_scale(h_scale)
    MS.horizontal_position(h_pos)

    
    MS.channels[0].vertical_scale(v_scale)
    MS.channels[0].termination(50)
    MS.channels[0].bandwidth(1e9)
    MS.channels[0].vertical_offset(0)
    MS.channels[0].vertical_position(0)
    MS.channels[0].vterm_bias(0)
    MS.channels[0].scale_ratio(1) # <- just set this as it is 
    MS.channels[0].invert('OFF')
    MS.trigger_channels[0].ch1_trigger_level(v_trigger)

def osc_check_standard(MS):
    '''Input: optional argument for time on horizontal axis of oscilloscope
        Optional argument for vertical scale of oscilloscope (10 divisions, set in V/div) 
    '''
    print(MS.horizontal_mode()) # set manual mode to allow parameters to be set
    print(MS.horizontal_mode_manual_configure())
    print(MS.horizontal_samplerate())
    print(MS.horizontal_divisions())
    print(MS.horizontal_scale())
    print(MS.horizontal_position())

    
    print(MS.channels[0].vertical_scale())
    print(MS.channels[0].termination())
    print(MS.channels[0].bandwidth())
    print(MS.channels[0].vertical_offset())
    print(MS.channels[0].vertical_position())
    print(MS.channels[0].vterm_bias())
    print(MS.channels[0].scale_ratio()) 
    print(MS.channels[0].invert())
    print(MS.trigger_channels[0].ch1_trigger_level())

def capture_trace(MS, dmm, yoko, p_att, station=None):
    ''' Parameters 
    '''
    if station is not None: 
        _ = station.snapshot(update=True) # <- updates parameters in station 
    
    meas = Measurement()
    meas.register_custom_parameter("trace", label="trace")
    meas.register_custom_parameter("time_axis", label="time_axis")
    meas.register_custom_parameter("h_samples", label="h_samples")
    meas.register_custom_parameter("h_samplerate", label="h_samplerate")
    meas.register_custom_parameter("h_position_perc", label="h_position_perc")
    meas.register_parameter(dmm.volt)
    meas.register_parameter(yoko.current) # minimise number of things required in a global namespace 
    meas.register_custom_parameter("v_attenuator", label="v_attenuator")
    
    
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
                    # (yoko.current, yoko.current()), 
                    ("h_samplerate", h_samplerate), 
                    ("h_samples", h_samples),
                    ("h_position_perc", h_position_perc),
                    (dmm.volt, dmm.volt()),
                    ('v_attenuator', float(p_att.ask('VOLT?'))))

def capture_trace_simple(MS, dmm, v_attenuator, station=None):
    ''' Parameters 
    '''
    if station is not None: 
        _ = station.snapshot(update=True) # <- updates parameters in station 
    
    meas = Measurement()
    meas.register_custom_parameter("trace", label="trace")
    meas.register_custom_parameter("time_axis", label="time_axis")
    meas.register_custom_parameter("h_samples", label="h_samples")
    meas.register_custom_parameter("h_samplerate", label="h_samplerate")
    meas.register_custom_parameter("h_position_perc", label="h_position_perc")
    meas.register_custom_parameter("v_attenuator", label="v_attenuator")
    meas.register_parameter(dmm.volt)

    
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
                    ("h_samplerate", h_samplerate), 
                    ("h_samples", h_samples),
                    ("h_position_perc", h_position_perc),
                    ('v_attenuator', v_attenuator),
                    (dmm.volt, dmm.volt()))


# Maybe put a plot timestamp on the function
# def
#     if timestamp is not None: 
#         title_string += 

def photon_number(bs10, bs90, power90, total_attenuation, wavelength=1550e-9):

    # if total_attenuation.any() < 0: 
    #     raise ValueError("total_attenuation should be greater than 0")
    #     return 
    
    Plaser =  power90/bs90
    Pin = Plaser*bs10
    Pdevice = Pin*(10**(-total_attenuation/10))
    f = spc.c/wavelength 
    Ephoton = spc.h*f
    Nphotons = Pdevice/Ephoton

    return Nphotons

def set_thresholds(current):

    # Thresholds from ID 12 
    if current > 13e-6:
        threshold1 = -330e-3 # in volts
        threshold2 = -50e-3 # in volt


    elif current > 11e-6:
        threshold1 = -276e-3 # in volts
        threshold2 = -50e-3 # in volt


    elif current > 9e-6:
        threshold1 = -237e-3 # in volts
        threshold2 = -50e-3 # in volt


    elif current > 7e-6:
        threshold1 = -177e-3 # in volts
        threshold2 = -50e-3 # in volt


    else:
        threshold1 = -126e-3 # in volts
        threshold2 = -50e-3 # in volt
    
    return threshold1, threshold2


def snspd_dark_counts(MS, dmm, yoko, device_name, n_captures, interval, currents, station=None):
    '''
    interval is specified in seconds
    '''

    if station is not None: 
        # Update experiment snapshot
        _ = station.snapshot(update=True) # <- updates parameters in station 

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
    meas.register_custom_parameter("CR1", label="cps")
    meas.register_custom_parameter("CR2", label="cps")
    meas.register_custom_parameter("n_captures")


    with meas.run() as datasaver:
        print(datasaver.run_id)
        
        # save device name 
        datasaver.dataset.add_metadata("device", device_name)
        
        # Extract the amount of time in one trace 
        h_time = MS.horizontal_scale()*MS.horizontal_divisions()
        
        time.sleep(2)


        for current in currents: # <- sweep voltage applied to attenuator
            
            # Set current 
            yoko.current(current)

            if MS.channels[0].clipping(): 
                print('Error: Clipping')

            threshold1, threshold2 = set_thresholds(current)

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
                                ("CR2", CR2))


def snspd_counts_vs_attenuation(MS, dmm, yoko, p_att, device_name, n_captures, interval, current, v_attenuator, station=None):
    '''
    interval is specified in seconds
    '''

    if station is not None: 
        # Update experiment snapshot
        _ = station.snapshot(update=True) # <- updates parameters in station 
        print('update station')

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
    meas.register_custom_parameter("CR1", label="cps")
    meas.register_custom_parameter("CR2", label="cps")
    meas.register_custom_parameter("n_captures")
    meas.register_custom_parameter("v_attenuator", label="V")



    with meas.run() as datasaver:
        print(datasaver.run_id)
        
        # save device name 
        datasaver.dataset.add_metadata("device", device_name)
        
        # Set attenuator to max value
        p_att.write(f'VOLT {v_attenuator[-1]}')
        time.sleep(5)
        
    
    
        # Set current
        yoko.current(current)
        time.sleep(1)
        print(f'Current is {yoko.current()}')

        if MS.channels[0].clipping(): 
            print('Error: Clipping')

        # Extract the amount of time in one trace 
        h_time = MS.horizontal_scale()*MS.horizontal_divisions()

        for v in v_attenuator[::-1]: # <- sweep voltage applied to attenuator
            
            p_att.write(f'VOLT {v}')
            time.sleep(1)
            print(f'Starting V={p_att.ask('VOLT?')}')
            
            # Set thresholds based on current 
            threshold1, threshold2 = set_thresholds(current)

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


def make_title(title, ID, extra=None):
    timestamp = load_by_id(ID).run_timestamp()
    s = f'{title}\nID {ID} {timestamp}'
    if extra is not None:
        s += f'\n{extra}'
    return s

def current_sweep(yoko, dmm, station=None):
    pass


'''To do: write a function for the averaging code 
'''
# meas = Measurement()
# meas.register_custom_parameter("ID_range", label="")
# meas.register_custom_parameter("v_attenuator", label="V")
# meas.register_custom_parameter("avg_attenuation", label="W")
# meas.register_custom_parameter("avg_power90", label="W")
# meas.register_custom_parameter("avg_power10", label="W")
# meas.register_custom_parameter("calibration_time", label="s")

# ID_range = np.arange(167, 240)
# v_range = np.arange(3.4, 7.05, 0.05)

# with meas.run() as datasaver: 
#     print(datasaver.run_id)
    
#     datasaver.dataset.add_metadata("attenuator_name", params.att_blue_name)
#     for i, ID in enumerate(ID_range): 
    
#         data = load_by_id(ID).get_parameter_data()
#         avg_attenuation = np.average(data['attenuation']['attenuation'])
#         avg_power90 = np.average(data['power90']['power90'])
#         avg_power10 = np.average(data['power10']['power10'])
#         calibration_time = data['times']['times'][-1]
        
#         datasaver.add_result(("ID_range", ID), 
#                              ("v_attenuator", v_range[i]),
#                              ("avg_attenuation", avg_attenuation),
#                             ("avg_power10", avg_power10),
#                             ("avg_power90", avg_power90),
#                              ("calibration_time", calibration_time),
#                             )
                                 