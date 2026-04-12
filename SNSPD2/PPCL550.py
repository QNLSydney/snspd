import warnings
from pyvisa import constants as vi_const
from qcodes import (VisaInstrument, validators as vals)
from qcodes.utils.helpers import create_on_off_val_mapping

NOP_DOCSTRING = """
The NOP register provides a way to access the module's status, returning 
pending operation status, and the current value of the error field. This 
register may be read upon receiving an execution error for an immediately 
preceding command.  It can also be polled to determine the status of pending 
operations.

Bits 15:8 - Pending Operation Flags
A series of eight flag bits indicating which operations, if any, are still 
pending. Each operation that becomes pending is assigned one of these four 
bit positions. The module can be periodically polled (by reading the NOP 
register) to determine which operations have completed. A value of 0x0 
indicates that there are no currently pending operations.

Bit 7:5 Always 0x00 (Reserved)

Bit 4 - MRDY - Module Ready
When 1 indicates that the module is ready for its output to be enabled
When 0 indicates that the module is not ready for its output to be enabled.

Bits 3:0 - Error field - Error condition for last completed command

0x00 OK  Ok, no errors
0x01 RNI The addressed register is not implemented
0x02 RNW Register not write-able; register cannot be written (read only)
0x03 RVE Register value range error; writing register contents causes value range error; contents unchanged
0x04 CIP Command ignored due to pending operation
0x05 CII Command ignored while module is initializing, warming up, or contains an invalid configuration.
0x06 ERE Extended address range error (address invalid)
0x07 ERO Extended address is read only
0x08 EXF Execution general failure
0x09 CIE Command ignored while module's optical output is enabled (carrying traffic)
0x0A IVC Invalid configuration, command ignored
0x0B 0x0E Reserved for future expansion
0x0F VSE Vendor specific error (see vendor specific documentation for more information)

Examples:
    16 : Module Ready and no operation pending
    Value larger than 16: Module ready for light output, but operation still
        pending
"""

LOW_NOISE_DOCSTRING = """
The standard operating mode for the laser is the dither-mode. In this mode all 
the control loops are running and creating noise 
(especially in the 1-10,000Hz range). By disabling these controlloops, either 
completely or partially, a lower noise behavior can be achieved.

In the whisper mode, essentially all control loops are disabled, to the extent 
possible. This results in the removal of the 888Hz tone (and its overtones) 
and this significantly reduced the AM and FM noise in the below 100Hz range. 
If in any way possible, we recommend to once in a while switch back to the 
dither mode for the laser to relock. Such a switch-back could be done in less 
than 10 seconds.
"""

#def nop_parser(nop_value:int) -> dict:
#    """Parse the value of the NOP register to a readable message."""
#    nop_dict = {
#        'module ready' : bin(nop_value)[-5] == '1',
#        '
#    }
#
#    if nop_value == 16:
#        return 'module ready'
#    elif nop_value

def checksum(byte0, byte1, byte2, byte3) -> int:
    """
    Calculates the communication checksum

    Notes:
        Page 29 of the OIF-ITLA-MSA document
    """
    bip8=(byte0&0x0f)^byte1^byte2^byte3
    bip4=((bip8&0xf0)>>4)^(bip8&0x0f)
    return bip4

class PPCL550(VisaInstrument):
    """
    QCoDeS driver for the PPCL550 laser

    Only a subset of all commands has been integrated in this driver
    """

    def __init__(self, name, address, **kwargs):
        super().__init__(name, address, **kwargs)

        # Stops random newline characters from halting the read
        self.visa_handle.end_input = vi_const.SerialTermination.none

        if self.get_idn()['model'] != 'PPCL550':
            raise Exception('Connected instrument is not a PPCL550.')

        self._min_freq = self._get_value(0x52)*1e12 + self._get_value(0x53)*1e8
        self._max_freq = self._get_value(0x54)*1e12 + self._get_value(0x55)*1e8

        self.add_parameter('nop',
                           get_cmd=lambda: self._get_value(0x00),
                           label='NOP / status',
                           docstring=NOP_DOCSTRING,
#                            get_parser=nop_parser,
        )

        self.add_parameter('channel',
                           get_cmd=lambda: self._get_value(0x30),
                           set_cmd=lambda x: self._set_value(0x30, x),
                           set_parser=int,
                           label='Output channel',
                           docstring=('Choose output channel.'+
                            ' Set to 1 to ensure laser coming on at FCF')
        )

        self.add_parameter('power',
                           get_cmd=lambda: self._get_value(0x31),
                           set_cmd=lambda x: self._set_value(0x31, x),
                           set_parser=int,
                           label='Optical power',
                           vals=vals.Numbers(7,18),
                           scale=100,
                           unit='dBm',
                           docstring=('Sets the optical output power set '+
                            'point in [7-18] dBm. The desired power is not' +
                            ' necessarily achieved when the command returns.')
        )
        self.add_parameter('temperature',
                           get_cmd=lambda: self._get_value(0x43)/100.0,
                           unit='C',
                           docstring='Primary control temperature',
        )
        self.add_parameter('diode_temperature',
                            get_cmd=lambda: int.from_bytes(
                                self._get_aea(0x58)[:2], byteorder='big')/100.0,
                            unit='C',
        )
        self.add_parameter('case_temperature',
                            get_cmd=lambda: int.from_bytes(
                                self._get_aea(0x58)[2:], byteorder='big')/100.0,
                            unit='C',
                            )
        self.add_parameter('FThermTh',
                            get_cmd=lambda: self._get_value(0x26)/100.0,
                            docstring='Maximum thermal deviation for fatal alarm.',
                           unit='C',
                            )
        self.add_parameter('WThermTh',
                            get_cmd=lambda: self._get_value(0x26)/100.0,
                            docstring='Maximum frequency deviation for fatal alarm.',
                           unit='C',
                            )
        self.add_parameter('enable',
                           get_cmd=lambda: self._get_value(0x32),
                           set_cmd=lambda x: self._set_value(0x32, x),
                           set_parser=int,
                           label='Enable output',
                           val_mapping=create_on_off_val_mapping(on_val=8, off_val=0)
        )

        self.add_parameter('_FCF1',
                           snapshot_exclude=True,
                           get_cmd=lambda: self._get_value(0x35),
                           set_cmd=lambda x: self._set_value(0x35, x),
                           set_parser=int,
                           label='First channel\'s frequency (THz)',
                           scale=1e-12,
                           unit='Hz',
                           docstring='Do not use directly. Use `frequency_coarse` instead'
        )

        self.add_parameter('_FCF2',
                           snapshot_exclude=True,
                           get_cmd=lambda: self._get_value(0x36),
                           set_cmd=lambda x: self._set_value(0x36, x),
                           set_parser=int,
                           label='First channel\'s frequency (GHz)',
                           scale=10e-9,
                           unit='Hz',
                           docstring='Do not use directly. Use `frequency_coarse` instead'
        )

        self.add_parameter('frequency_coarse',
                           get_cmd=(lambda: self._FCF1() + self._FCF2()),
                           set_cmd=self._set_fcf,
                           set_parser=int,
                           label='Coarse Frequency',
                           vals=vals.Numbers(self._min_freq, self._max_freq),
                           unit='Hz',
                           docstring=('Set the frequency of the first channel.'
                            + ' Only modify when laser is turned off.'+
                            ' Must be a multiple of 10 GHz.')
        )

        self.add_parameter('frequency_fine',
                           get_cmd=lambda: self._get_value(0x62, signed=True),
                           set_cmd=lambda x: self._set_value(0x62, x, signed=True),
                           set_parser=int,
                           label='Fine Tune Frequency',
                           vals=vals.Numbers(-30e9,30e9),
                           scale=1e-6,
                           unit='Hz',
                           docstring='Set the fine tune frequency of the laser [-30 - 30 GHz]')

        self.add_parameter('low_noise',
                           get_cmd=lambda: self._get_value(0x90),
                           set_cmd=lambda x: self._set_value(0x90, x),
                           label='Operate in low-noise mode',
                           val_mapping=create_on_off_val_mapping(on_val=2, off_val=0),
                           docstring=LOW_NOISE_DOCSTRING)

        self.connect_message()



    def _get_register(self, register) -> bytes:
        """
        Get the contents of the specified register
        """
        message = bytes([checksum(0, register, 0, 0) << 4, register, 0x00, 0x00])
        self.visa_handle.write_raw(message)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            response = self.visa_handle.visalib.read(
                self.visa_handle.session, 4)
        if response[0][1] != register:
            raise Exception(f'Unexpected response: {response[0]}')
        status = response[0][0] % 4
        # 0 : OK
        # 1 : XE (execution error)
        # 2 : AEA
        # 3 : CP, Command not complete
        if status == 1:
            raise Exception(
                f'Register {register} read resulted in execution error')

        return response[0][2:]

    def _get_value(self, register, signed=False) -> int:
        """
        Only get the value part of a register
        Uses _get_register to obtain _get_value
        """
        reg   = self._get_register(register)
        if signed:
            value = int.from_bytes(reg, byteorder='big', signed=True)
        else:
            value = int.from_bytes(reg, byteorder='big', signed=False)
        return value

    def _set_value(self, register, value, signed=False):
        """
        Sets `register` to `value`. Use `signed=True` for values that need a signed integer.
        """
        if signed:
            (byte2, byte3) = value.to_bytes(2, byteorder='big', signed=True)
        else:
            (byte2, byte3) = value.to_bytes(2, byteorder='big', signed=False)
        message = bytes([(checksum(1, register, byte2, byte3) << 4) + 1,
                         register, byte2, byte3])
        self.visa_handle.write_raw(message)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            response = self.visa_handle.visalib.read(
                self.visa_handle.session, 4)
        if response[0][1] != register:
            raise Exception(f'Unexpected response: {response[0]}')
        status = response[0][0] % 4
        # 0 : OK
        # 1 : XE (execution error)
        # 2 : AEA
        # 3 : CP, Command not complete
        if status == 1:
            raise Exception(
                f'Register {register} write resulted in execution error')

    def _get_aea(self, register) -> str:
        """
        Retrieve through the AEA mechanism

        Notes:
            AEA stands for automatic extended addressing
        """
        byte_n = int(self._get_value(register)) % 256
        aea_values = b''
        for _ in range(byte_n // 2):
            response = self._get_register(11)
#            AEA += ''.join(chr(x) for x in response)
            aea_values += response

        return aea_values

    def get_idn(self):
        """
        Replaces the qcodes get_idn function
        """
        vendor   = self._get_aea(0x02).decode("utf-8").strip('\x00')
        model    = self._get_aea(0x03).decode("utf-8").strip('\x00')
        serial   = self._get_aea(0x04).decode("utf-8").strip('\x00')
        firmware = self._get_aea(0x06).decode("utf-8").strip('\x00')
        idn = dict([('vendor', vendor),
                    ('model', model),
                    ('serial', serial),
                    ('firmware', firmware)])
        return idn

    def _set_fcf(self, frequency):
        """
        Wrapper to set FCF1 (THz register) and FCF2 (GHz*10 register) at once.

        Note:
            FCF stands for first channel frequency.
        """
        if self.enable():
            raise Exception('Value can not be changed while laser output is enabled')
        ghz_value = frequency % 1e12
        thz_value = frequency - ghz_value
        self._FCF1(thz_value)
        self._FCF2(ghz_value)
