import random
import logging
import uproot
import numpy as np
from scipy import interpolate
from NuRadioReco.modules.base.module import register_run
from NuRadioReco.utilities import units
logger = logging.getLogger('noiseImporter')

# layout to read the ARIANNA data for unknown formatting uproot does not guess right
ARIANNA_uproot_interpretation = {
        # TTimeStamp objects in root are 2 ints
        # * first is time in sec since 01/01/1970,
        # * second one is nanoseconds
        # will return a jagged array of shape n_events x [t_s, t_ns]
        "time": uproot.interpretation.jagged.AsJagged(
            uproot.interpretation.numerical.AsDtype('>i4'), header_bytes=6),
        # Interpretation of the trigger mask.
        # - Bit 0: Thermal trigger
        # - Bit 1: Forced trigger
        # - Bit 2: External trigger (not used with current DAQ)
        # - Bit 3: L1 Trigger satisfied: the L1 trigger cuts away events with
        #          a large fraction of power in a single frequency.
        #          true = event PASSES, false = event would be cut by this L1
        #          (may be in data via scaledown)
        # - Bit 4: 0 <not used>
        # - Bit 5: whether event is written thanks to L1 scaledown
        # - Bit 6: whether throwing away events based on L1 triggers
        # - Bit 7: flag events that took too long to get data from dCards to MB
        # NB: No idea why the number of header_bytes in the root files is so odd.
        "trigger": uproot.interpretation.jagged.AsJagged(
            uproot.interpretation.numerical.AsDtype("uint8"), header_bytes=7)
        }

# arianna tigger map
ARIANNA_TRIGGER = {
        "thermal" : 2**0,
        "forced"  : 2**1,
        "external": 2**2,
        "l1":       2**3,
        # not_used: 2**4,
        "l1_scaledown":     2**5,
        "l1_enabled" :      2**6,
        "exceeding_buffer": 2**7
        }

class noiseImporter:
    """
    Imports recorded noise from ARIANNA station.
    The recorded noise needs to match the station geometry and sampling
    as chosen with channelResampler and channelLengthAdjuster

    For different stations, new noise files need to be used.
    Collect forced triggers from any type of station to use for analysis.
    A seizable fraction of data is recommended for accuracy.

    The noise will be random.
    This module therefore might produce non-reproducible results on a single event basis,
    if run several times.
    """

    def begin(self, noise_files, read_temperatures=False, read_power=False):
        data = []
        trigger = []
        posix_times = []
        run = []
        station_id = []
        temperature = []
        power_voltage = []
        dtms = []
        # loop over input files to extract needed data
        for noise_file in noise_files:
            logger.info("reading data for file {noise_file}", noise_file=noise_file)
            with uproot.open(noise_file) as nf_uproot:
                nt_uproot = nf_uproot["CalibTree"]
                logger.debug("reading data")
                if nt_uproot.num_entries < 1000:
                    data.append(np.array(nt_uproot["AmpOutData."]["AmpOutData.fData"].array()))
                else:
                    bunches = list(np.arange(0, nt_uproot.num_entries, 1000))
                    bunches.append(nt_uproot.num_entries)
                    first = bunches[:-1]
                    last = bunches[1:]
                    for i in range(len(first)):
                        logger.info("reading data bunch {} of {}".format(i+1, len(first)))
                        data.append(np.array(nt_uproot["AmpOutData."]["AmpOutData.fData"].array(entry_start=first[i], entry_stop=last[i])) * units.mV)
                # trigger jagged array only consists of single number, so drop the array [:,0]
                logger.debug("reading trigger info")
                trigger.append(np.array(nt_uproot['EventHeader.']['EventHeader.fTrgInfo'].array(interpretation = ARIANNA_uproot_interpretation['trigger']))[:,0])
                # consists of posix time [s] and [ns]
                logger.debug("reading times")
                event_times_file = np.array(nt_uproot['EventHeader.']['EventHeader.fTime'].array(interpretation = ARIANNA_uproot_interpretation['time']))[:,0]
                posix_times.append(event_times_file)
                # read the temperature
                if read_temperatures:
                    logger.debug("reading temperature")                
                    (temp_times, interpolated_temperatures) = self._read_temperature_curve(nf_uproot, event_times_file)
                    temperature.append(interpolated_temperatures)
                # read the run number
                run.append(np.array(nt_uproot['EventMetadata./EventMetadata.fRun'].array()))
                # read the station id
                station_id.append(np.array(nt_uproot['EventMetadata./EventMetadata.fStnId'].array()))
                # read DTms value
                dtms.append(np.array(nt_uproot['EventHeader./EventHeader.fDTms'].array()))
                if read_power:
                    # read station voltages
                    (temp_times, interpolated_voltages) = self._read_power_curve(nf_uproot, event_times_file)
                    power_voltage.append(interpolated_voltages)

        self.data = np.concatenate(data)
        self.posix_time = np.concatenate(posix_times)
        self.datetime = np.array([np.datetime64(int(t), 's') for t in self.posix_time])
        self.trigger = np.concatenate(trigger)
        if read_temperature:
            self.temperature = np.concatenate(temperature)
        if read_power:
            self.power = np.concatenate(power_voltage)
        self.station_id = np.concatenate(station_id)
        self.dtms = np.concatenate(dtms)
        self.run_number = np.concatenate(run)
        self.nevts = len(self.data)

    def _read_temperature_curve(self, nf, interpolation_times=None):
        """
        Imports the temperature vs. posix time from a noise file (nf)

        The temperature is not taken per event, so the posix_time and temperature value is returned
        if interpolation_times is specified, interpolate to these posix time stamps
        """
        # get the correct tree
        nt = nf["TemperatureTree"]
        time = nt['Temperature./Temperature.fTime'].array(interpretation = ARIANNA_uproot_interpretation['time'])[:,0]
        data = nt['Temperature./Temperature.fTemp'].array()

        if interpolation_times is None:
            # return just the plain data
            return (time, data)
        else:
            # generate an interpolator for the requested times
            interpolator = interpolate.interp1d(time, data, bounds_error=False, fill_value=(data[0],data[-1]))
            return (interpolation_times, interpolator(interpolation_times))

    def _read_power_curve(self, nf, val="V1", interpolation_times = None):
        """
        Imports the voltage vs. posix time from a noise file (nf)

        # Todo: not sure if V1 and V2 refer to two batteries...
        The voltage is not taken per event, so the posix_time and voltage value is returned
        if interpolation_times is specified, interpolate to these posix time stamps
        """
        # get the correct tree
        nt = nf["VoltageTree"]
        time = nt['PowerReading./PowerReading.fTime'].array(
                interpretation = ARIANNA_uproot_interpretation['time'])[:,0]
        data = np.array(nt['PowerReading./PowerReading.fave'+val].array()) * units.mV

        if interpolation_times is None:
            # return just the plain data
            return (time, data)

        # generate an interpolator for the requested times
        interpolator = interpolate.interp1d(time,
                data, bounds_error=False, fill_value=(data[0],data[-1]))
        return (interpolation_times, interpolator(interpolation_times))

    @register_run()
    def run(self, evt, station, det):
        # loop over stations in simulation
        for channel in station.iter_channels():
            channel_id = channel.get_id()

            # pick a noise waveform
            noise_event = random.randint(0, self.nevts)
            nchans = np.shape(self.data)[1]

            # check if simulated channel exists in input file
            # otherwise pick a smaller channel number
            if channel_id > nchans-1:
                orig_channel_id = channel_id
                channel_id %= nchans
                logger.warning(
                    "Channel {ch_orig} not in file ({n_chan} channels): Using channel {ch_new}",
                    ch_orig = orig_channel_id, n_chan = nchans, ch_new = channel_id)

            noise_samples = np.shape(self.data)[-1]

            trace = channel.get_trace()
            if noise_samples != trace.shape[0]:
                logger.warning("Mismatch: Noise has {0} and simulation {1} samples.\n\
                        Not adding noise!".format(noise_samples, trace.shape[0]))
            else:
                noise_trace = np.array(self.data[noise_event][channel_id]) * units.mV
                noise_trace += trace

                channel.set_trace(noise_trace, channel.get_sampling_rate())

    def end(self):
        """ end method """
        pass
