import yaml


class snspd:
    def __init__(self, config=None):
        self.device_1_name = 'Line 1 R7C6'
        self.device_2_name = 'Line 2 Old Device'
        self.att_screw_name = 'VOA50PM'
        self.att_blue_name = 'V1550PA'
        self.bs10 = 0.08819209378534265
        self.bs90 = 0.9118079062146573
        # have oscilloscope settings for each measurement set? 
        self.h_time_counts = 100e-3
        self.h_pos_counts = 0 
        self.v_scale_counts = 150e-3 
        self.att_screw_calibration_id = 165
        # self.att_blue_calibration_avg_id = 441 # from IDs 167-239 
        self.att_blue_calibration_avg_id = 459 # updated to include calibration times
        self.system_dark_counts_id = 455
        self.att_info_id = 457 # data containing votlage an corresponding total attenuation, number of photons 
        # self.counts_vs_attenuation = 463
        self.counts_vs_attenuation_id = 464

        # # Open your yaml file
        # with open('config.yaml', 'r') as file:
        #     data = yaml.safe_load(file)

        # print(data)
