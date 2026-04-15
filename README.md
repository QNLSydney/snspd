SNSPD experiments

To do 
* Add temperature to critical current sweep 
* Add tqdm and expected run time to codebase
* Could make the current sweep bidirectional 
* Code should set the wavelength of the laser
* photon number calculation wavelength/frequency should come from laser
* adjust counts function and plotting routine to not get the voltage applied to attenuator value from passing in the instrument, but from the station
* reconcile counting functons and which parameters should be set externally and which internally 
* retrieve deleted Counts vs attenuation measurement run file from GIthub
* for meas. 4-3 draw on diagram the applied attenuator voltage and laser settings, put all things being controlled on the diagram 
* from Measurement 4-5: create a better way to import new thresholds rather than commenting out the function: maybe read from a config file. This would work well if the functions were incorporated into the main class. 
* Oscillosocpe counting parameters (thresholds, vertical scale) need to be able to be re-set for different devices
* dark counts current is unnecessary becasue counts vs current doesn't set the laser