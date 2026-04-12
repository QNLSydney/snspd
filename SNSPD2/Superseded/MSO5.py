from qcodes import VisaInstrument, validators as vals
from qcodes.utils.validators import Numbers, Ints, Enum, MultiType, Anything
from qcodes.instrument.channel import InstrumentChannel, ChannelList, InstrumentModule
from qcodes import Instrument
from qcodes.instrument.base import InstrumentBase

from functools import partial
from numpy import array


class MSO5Channel(InstrumentChannel):
    def __init__(self, parent, name, channel):
        super().__init__(parent, name)
    
        self.add_parameter('vertical_scale',
                            get_cmd='CH{0:d}:SCAle?'.format(channel),
                            get_parser=float,
                            unit='V',
                            )
        self.add_parameter('vertical_offset',
                            get_cmd='CH{0:d}:OFFSet?'.format(channel),
                            get_parser=float,
                            unit='V',
                            )
        self.add_parameter('bandwidth',
                            get_cmd='CH{0:d}:BANdwidth?'.format(channel),
                            get_parser=float,
                            unit='Hz')
        self.add_parameter('coupling',
                            get_cmd='CH{0:d}:COUPling?'.format(channel),
                            )
        self.add_parameter('probe_setting',
                            get_cmd='CH{0:d}:PRObe:SET?')

class MSO5trigger_channel(InstrumentChannel):
    def __init__(self, parent, name, channel):
        super().__init__(parent, name)
    
        self.add_parameter('edge_source',
                            get_cmd='TRIGger:{0}:EDGE:SOURce?'.format(channel),
                            set_cmd='TRIGger:{0}:EDGE:SOURce {1}'.format(
                                channel, "{}"),
                            )
        self.add_parameter('edge_coupling',
                            get_cmd='TRIGger:{0}:EDGE:COUPling?'.format(channel),
                            set_cmd='TRIGger:{0}:EDGE:COUPling {1}'.format(
                                channel, "{}"),
                            vals=vals.Enum('DC','HFRej','LFRej','NOISErej'),
                            docstring='Coupling for the edge trigger.',
                            )
        self.add_parameter('edge_slope',
                            get_cmd='TRIGger:{0}:EDGE:SLOpe?'.format(channel),
                            )
        for i in range(1, len(parent.channels)+1):
            self.add_parameter('ch{0}_trigger_level'.format(i),
                            get_cmd='TRIGger:{0}:LEVel:CH{1}?'.format(
                                channel, i),
                            get_parser=float,
                            )

class MSO5waveform(InstrumentModule):
    def __init__(self, parent, name, **kwargs):
        self._parent = parent
        super().__init__(parent, name, **kwargs)

#        print(parent.name)
#
#        print(self._parent.name)
#
        self.add_parameter('y_multiplication',
                            get_cmd=('WFMOutpre:YMUlt?'),
                            get_parser=float) 
        self.add_parameter('y_offset',
                            get_cmd=('WFMOutpre:YMUlt?'),
                            get_parser=float) 
        self.add_parameter('trigger_point',
                            get_cmd=('WFMOutpre:PT_Off?'),
                            get_parser=int)
        self.add_parameter('xzero',
                            get_cmd=('WFMOutpre:XZEro?'),
                            get_parser=float)

class MSO5(VisaInstrument):
    """
    Driver for the Tektronix MSO5 series oscilloscope.
       
    Notes:
        The arbitrary function generator is an option.

    """
    def __init__(self, name, address, channels_n, reset=False, **kwargs):
        super().__init__(name, address, terminator='\n', **kwargs)

        model = self.get_idn()
        self.installed_options = self.ask('*OPT?').split(';')
        # AFG 
        self.add_parameter('afg_amplitude',
                            label='Arbitrary Function Generator amplitude',
                            get_cmd='AFG:AMPL?',
                            set_cmd='AFG:AMPL {0:.3f}',
                            get_parser=float,
                            unit='V',
                            vals=Numbers(min_value=0.0, max_value=3.0),
                            )
        self.add_parameter('afg_frequency',
                            label='Arbitrary Function Generator frequency',
                            get_cmd='AFG:FREQ?',
                            set_cmd='AFG:FREQ {0:.4E}',
                            get_parser=float,
                            unit='Hz',
                            )
        self.add_parameter('instrument_time',
                            get_cmd='TIMe?',
                            )

        # Trigger parameters
        self.add_parameter('trigger_mode',
                            get_cmd='TRIGger:A:MODe?',
                            set_cmd='TRIGger:A:Mode {0}',
                            vals=vals.Enum('AUTO', 'NORM'),
                            )

        self.add_parameter('trigger_frequency_counter_state',
                            get_cmd='DVM:TRIGger:FREQuency:COUNTer?',
                            )
        self.add_parameter('trigger_frequency_counter',
                            get_cmd='DVM:MEASU:FREQ?',
                            unit='Hz',
                            get_parser=float,
                            )
        self.add_parameter('data_rate',
                            get_cmd='HORIZONTAL:MODE:SAMPLERATE?',
                            get_parser=float,
                            )
        self.add_parameter('acquire_state',
                            get_cmd='ACQuire:STATE?',
                            set_cmd='ACQuire:STATE {}',
                            )
        self.add_parameter('acquire_stopafter',
                            get_cmd='ACQuire:STOPAfter?',
                            set_cmd='ACQuire:STOPAfter {}',
                            vals=vals.Enum('RUNSTop, SEQuence'),
                            )

        self.add_parameter('timebase',
                            label='timebase',
                            docstring='horizontal scale per division',
                            get_cmd='HORIZONTAL:SCALE?',
                            set_cmd='HORIZONTAL:SCALE {0:.4E}',
                            get_parser=float,
                            unit='s')
                            
        self.add_parameter('event',
                            get_cmd='EVENT?',
                            get_parser=int)

        self.add_parameter('data_source',
                            docstring='location of waveform data',
                            get_cmd='DATa:SOURce?',
                            set_cmd='DATa:SOURce {}',
                            vals=vals.Enum('CH 1', 'CH 2', 'CH 3', 'CH 4')
                            )
        self.add_parameter('data_encoding',
                            get_cmd='DATa:ENCdg?')
        self.add_parameter('data_width',
                            get_cmd='DATA:WIDTH?',
                            set_cmd='DATA:WIDTH {}',
                            get_parser=int,
                            )

        self.add_parameter('waveform_byte_number',
                            get_cmd='WFMOutpre:BYT_Nr?',
                            set_cmd='WFMOutpre:BYT_Nr {0}',
                            vals=vals.Enum(1,2,8),
                            docstring='binary field data width. Programmer manual page 2-892')
        self.add_parameter('waveform_points',
                           get_cmd='WFMOutpre:NR_Pt?',
                           get_parser= lambda s: int(float(s)),
                                )
        self.add_parameter('horizontal_mode',
                           get_cmd='HORizontal:MODE?')
        self.add_parameter('horizontal_mode_record_length',
                           get_cmd='HORizontal:MODE:RECOrdlength?')
        self.add_parameter('horizontal_mode_sample_rate',
                           get_cmd='HORizontal:MODE:SAMPLERate?',
                           get_parser=float,
                        )
        self.add_parameter('horizontal_delay',
                            get_cmd='HORizontal:DELay:TIMe?',
                            set_cmd='HORizontal:DELay:TIMe {0:.3f}E',
                            get_parser=float,
                            unit='s',
                            )
        self.add_parameter(name="search_total", 
                           label= "search crossings",
                           get_cmd="SEARCH:SEARCH1:TOTal?",

 

                           unit="counts",)

        channels = ChannelList(self, "Channels", MSO5Channel,
                        snapshotable=False)
        trigger_channels = ChannelList(self, "trigger_channels", MSO5trigger_channel,
                        snapshotable=False)
        
        for channel_number in range(1, channels_n+1):
            channel = MSO5Channel(self, "ch{}".format(channel_number), 
                        channel_number) 
            channels.append(channel)

        channels.lock()
        self.add_submodule('channels', channels)

        for tc in ['A','B']:
            trigger_channel = MSO5trigger_channel(self, "{}".format(tc), tc)
            trigger_channels.append(trigger_channel)
                

        trigger_channels.lock()
        self.add_submodule('trigger_channels', trigger_channels)

        waveform = MSO5waveform(self, name='waveform')
        self.add_submodule('waveform', waveform)

        self.add_function('auto_counter', call_cmd='COUN:AUTO')

    def waveform_data(self, raw=False):
        """Read the waveform data.

        """
        data_width = self.data_width()
        if data_width == 1:
            datatype = 'b'
        elif data_width == 2:
            datatype = 'h'

        raw_data = self.visa_handle.query_binary_values('CURVE?',
            datatype=datatype,
            is_big_endian=False)

        y_multiplication = float(self.ask('WFMOUtpre:YMUlt?'))
        y_offset = float(self.ask('WFMOUtpre:YOFf?'))
        return array(raw_data) * y_multiplication + y_offset
    
   
 

