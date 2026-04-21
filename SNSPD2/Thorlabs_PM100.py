import qcodes.utils.validators as vals
from qcodes import VisaInstrument

class Thorlabs_PM100(VisaInstrument):
    """
    This is the qcodes driver for the Thorlabs PM100D power detector.
    """

    def __init__(self, name, address, **kwargs):
        super().__init__(name, address, **kwargs)

        self.visa_handle.read_termination = '\r\n'

        self.timeout(1.0)

        #self.installed_options = self.ask('*OPT?').split(';')
        
        self.add_parameter('wavelength',
                            get_cmd='CORR:WAV?',
                            set_cmd='CORR:WAV {0:.3f}',
                            unit='nm',
                            get_parser=float
                            )
        self.add_parameter('power',
                            get_cmd='MEAS:POW?',
                            get_parser=float,
                            unit='W',
                            )
        self.add_parameter('calibration_date',
                            get_cmd='CALibration:STRing?')

        self.add_parameter('count_average',
                            get_cmd=':SENSe:AVERage:COUNt?',
                            set_cmd=':SENSe:AVERage:COUNt {}',
                            get_parser=int,
                            vals=vals.Ints(1,3000),
                            )
        self.add_parameter('power_range_auto',
                            get_cmd=':POWer:RANGe:AUTO?')

        self.add_parameter('sensor_type',
                            get_cmd=':SYST:SENSor:IDN?',
                            get_parser = lambda s: s.split(',')[0]
                        )
        self.add_parameter('sensor_serial_number',
                            get_cmd=':SYST:SENSor:IDN?',
                            get_parser = lambda s: s.split(',')[1]
                        )
        self.add_parameter('power_autorange',
                            get_cmd=':SENSe:POWer:RANGe:AUTO?',
                            )
        self.add_parameter('power_reference',
                            get_cmd=':POWer:REFerence?',
                            get_parser=float)
        self.add_parameter('sensor_temperature',
                            get_cmd=':MEASure:TEMPerature?',
                            get_parser=float,
                            unit='C',
                            )
        self.add_parameter('sensor_current',
                            get_cmd=':MEASure:CURRent?',
                            get_parser=float,
                            unit='A')
                            

class Thorlabs_PM100D(Thorlabs_PM100):
    def __init__(self, name, address, **kwargs):
        super().__init__(name, address, **kwargs)

        idn = self.get_idn()
        if idn['model'] != 'PM100D':
            raise Exception('Connected instrument is not a PM100D.')

        self.add_parameter('display_brightness',
                            get_cmd='DISPlay:BRIGhtness?',
                            get_parser=float,
                            )
        self.add_parameter('display_contrast',
                            get_cmd='DISPlay:CONTrast?',
                            get_parser=float,
                            )

class Thorlabs_PM100USB(Thorlabs_PM100):
    def __init__(self, name, address, **kwargs):
        super().__init__(name, address, **kwargs)

        idn = self.get_idn()
        #if idn['model'] != 'PM100USB':
            #raise Exception('Connected instrument is not a PM100USB.')
class Thorlabs_PM16(Thorlabs_PM100):
    def __init__(self, name, address, **kwargs):
        super().__init__(name, address, **kwargs)

        idn = self.get_idn()
        if idn['model'] != 'PM16':
            raise Exception('Connected instrument is not a PM16.')
class Thorlabs_S120(Thorlabs_PM100):
    def __init__(self, name, address, **kwargs):
        super().__init__(name, address, **kwargs)

        idn = self.get_idn()

