import yaml


class snspd:
    def __init__(self, config=None):
        # Parameters pertaining to instruments 
        self.att_screw_name = 'VOA50PM'
        self.att_blue_name = 'V1550PA'
        self.bs10 = 0.08819209378534265
        self.bs90 = 0.9118079062146573


        # Create config for parame50e-3ters that pertain to devices 
        self.h_time_counts = 100e-3
        self.h_pos_counts = 0 
        self.v_scale_counts = 150e-3 
        self.device_1_name = 'Line 1 R7C6'
        self.device_2_name = 'Line 2 Old Device'

        # # Open your yaml file
        # with open('config.yaml', 'r') as file:
        #     data = yaml.safe_load(file)

        # print(data)
    
    def set_thresholds(self): 
        # goal: get this to read in from yaml file
        pass
