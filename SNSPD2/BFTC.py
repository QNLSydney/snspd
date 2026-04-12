import json
from msilib import sequence
import requests
import base64
import time
import warnings
import datetime

class BFTC_HEATER:
    def __init__(self, parent, heater_nr):
        self.parent = parent
        self.heater_nr = heater_nr

        data = self.info()
        self.name = data['name']
    
    def _post(self, endpoint, data):
        return self.parent._post(endpoint, data)
    
    def info(self):
        endpoint = "heater"
        data = {'heater_nr': self.heater_nr}
        data = self._post(endpoint, data)
        return data
    
    
    def pid_settings(self, PID=None):
        pid_dict = self.info()['control_algorithm_settings']
        if PID is None:
            return (pid_dict["proportional"], pid_dict["integral"], pid_dict["derivative"])
        
        if PID[0] is not None:
            pid_dict["proportional"] = PID[0]
        if PID[1] is not None:
            pid_dict["integral"] = PID[1]
        if PID[2] is not None:
            pid_dict["derivative"] = PID[2]

        endpoint = "heater/update"
        data = {'heater_nr': self.heater_nr,
                'control_algorithm_settings': pid_dict}
        self._post(endpoint, data)
        
    
    def power(self, power = None):
        if power is None:
            data = self.info()
            return data['power']
    
        endpoint = "heater/update"
        data = {'heater_nr': self.heater_nr,
                'power': power}
        data = self._post(endpoint, data)
        return data['power']
    
    def max_power(self, power = None):
        if power is None:
            data = self.info()
            return data['max_power']
    
        endpoint = "heater/update"
        data = {'heater_nr': self.heater_nr,
                'max_power': power}
        data = self._post(endpoint, data)
        return data['max_power']
    
    def setpoint(self, setpoint = None):
        if setpoint is None:
            data = self.info()
            return data['setpoint']
    
        endpoint = "heater/update"
        data = {'heater_nr': self.heater_nr,
                'setpoint': setpoint}
        data = self._post(endpoint, data)
        return data['setpoint']
    
    def pid_mode(self, pid_mode = None):
        if pid_mode is None:
            data = self.info()
            return data['pid_mode']
        if pid_mode not in [0,1]:
            raise ValueError("Valid input: 0 or 1 (for 'Manual' or 'PID')")
    
        endpoint = "heater/update"
        data = {'heater_nr': self.heater_nr,
                'pid_mode': pid_mode}
        data = self._post(endpoint, data)
        return data['pid_mode']
    
    def active(self, active = None):
        if active is None:
            data = self.info()
            return data['active']
        if active not in [True, False]:
            raise ValueError("Valid input: True or False (for 'ON' or 'OFF')")
    
        endpoint = "heater/update"
        data = {'heater_nr': self.heater_nr,
                'active': active}
        data = self._post(endpoint, data)
        return data['active']
    
    def on(self):
        self.active(True)

    def off(self):
        self.active(False)
        

class BFTC_CHANNEL:
    def __init__(self, parent, channel_nr):
        self.parent = parent
        self.channel_nr = channel_nr

        data = self.info()
        self.name = data['name']
    
    def _post(self, endpoint, data):
        return self.parent._post(endpoint, data)
    
    def info(self):
        endpoint = "channel"
        data = {'channel_nr': self.channel_nr}
        data = self._post(endpoint, data)
        return data
    
    def measure(self):
        date = datetime.datetime.utcnow()
        start_date = date - datetime.timedelta(minutes=5)
        stop_date = date + datetime.timedelta(minutes=5)

        endpoint = "channel/historical-data"
        data = {'channel_nr': self.channel_nr,
                'start_time': start_date.strftime('%Y-%m-%d %H:%M:%S'),
                'stop_time': stop_date.strftime('%Y-%m-%d %H:%M:%S'),
                'fields': ['temperature']}
        data = self._post(endpoint, data)
        return data["measurements"]
    


class BFTC:
    def __init__(self, address):
        self.address = address
        self._sequence = 0
        self.heaters = {}
        for i in range(4):
            heater = BFTC_HEATER(self, i+1)
            self.heaters[heater.name] = heater

        self.channels = {}
        for i in range(8):
            channel = BFTC_CHANNEL(self, i+1)
            if channel.name == '':
                del channel
                continue
            self.channels[channel.name] = channel
    
    def _sequence_number(self):
        self._sequence +=1
        return self._sequence
    
    def _post(self, endpoint, data):
        url = "http://{}/{}".format(self.address, endpoint)

        data['sender'] = 'Python'
        data['hash'] =  str(self._sequence_number())
      
        req = requests.post(url, json=data)
        data = req.json()
        if data['status'] == 'ERROR':
            warnings.warn(data['error_msg'], RuntimeWarning)
        return data


    def set_heater_channel_assignment(self, channel_nr, heater_nr):
        endpoint = "channel/heater/update"
        data = {'channel_nr': channel_nr,
                'heater_nr': heater_nr}
        data = self._post(endpoint, data)
        return data
    