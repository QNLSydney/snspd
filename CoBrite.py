from qcodes.validators import Numbers
from qcodes import VisaInstrument
from qcodes.parameters import create_on_off_val_mapping
from functools import partial

class CoBrite(VisaInstrument):
    """
    Qcodes driver for the IDPhotonics CoBrite laser.
    """
    def __init__(self, name, address, reset=False, **kwargs):
        super().__init__(name, address, **kwargs)

        self.visa_handle.baud_rate = 115200
        self.visa_handle.read_termination = ';'
        self.visa_handle.write_termination = '\r'

        if not (self.ask(':SYSTEM:ECHO 0') == ''):
            raise Exception('Unexpected response.')
        
        response = self.ask(':SOURCE:WAVELENGTH:LIMIT?')
        self.wavelength_limits = [float(v) for v in response.split(',')]

        response = self.ask(':SOURCE:FREQUENCY:LIMIT?')
        self.frequency_limits = [float(v) for v in response.split(',')]        

        response = self.ask(':SOURCE:POWER:LIMIT?')
        self.power_limits = [float(v) for v in response.split(',')]

        self.add_parameter('wavelength',
            get_cmd=':SOURCE:WAVELENGTH?',
            set_cmd = partial(self.set_command, command=':SOURCE:WAVELENGTH'),
            get_parser=float,
            vals=Numbers(self.wavelength_limits[0], self.wavelength_limits[1]),
            unit='nm',
        )

        self.add_parameter('frequency',
            get_cmd=':SOURCE:FREQUENCY?',
            set_cmd = partial(self.set_command, command=':SOURCE:FREQUENCY'),
            get_parser=float,
            vals=Numbers(self.frequency_limits[0], self.frequency_limits[1]),
            unit='THz',
        )        
        #self.add_parameter('frequency',
        #    get_cmd=':SOURCE:FREQUENCY?',
        #    get_parser=float,
        #    vals=Numbers(self.frequency_limits[0], self.frequency_limits[1]),
        #    unit='THz',
        #)        
        self.add_parameter('power',
            get_cmd=':SOURCE:POWER?',
            set_cmd = partial(self.set_command, command = ':SOURCE:POWER'),
            get_parser=float,
            vals=Numbers(self.power_limits[0], self.power_limits[1]),
            unit='dBm',
        )
        #self.add_parameter('power',
        #    get_cmd=':SOURCE:POWER?',
        #    get_parser=float,
        #    vals=Numbers(self.power_limits[0], self.power_limits[1]),
        #    unit='dBm',
        #)        
        self.add_parameter('output_state',
            get_cmd=':SOURCE:STATE?',
            set_cmd=partial(self.set_command,command=':SOURCE:STATE'),
            val_mapping = create_on_off_val_mapping(on_val='1', off_val='0'),
        )
        #self.add_parameter('output_state',
        #    get_cmd=':SOURCE:STATE?',
        #    get_parser=int,
        #)

        self.connect_message()

    def get_idn(self):
        """Get the *IDN? response and decode it."""
        idn_str = self.ask('*IDN?')
        if not idn_str.startswith('IDP-CBDX1'):
            raise Exception('Wrong response to *IDN? : ' + idn_str)

        idn_list = idn_str.split(',')
        return {'vendor'   : 'IDPhotonics',
                'model'    : idn_list[0],
                'serial'   : idn_list[1].lstrip('SN: '),
                'firmware' : idn_list[2],
                'hardware' : idn_list[3]}
    def set_command(self, value:str, command:str):
        response = self.ask(command + ' {0}'.format(value))
        if response == '':
            return
        else: 
            raise Exception('Unexpected easteregg to {0}: {1}'.format(command, response))

    def get_monitor(self):
        response = [float(v) for v in laser.ask(':SOURCE:MONITOR?').split(',')]
        return response
