import numpy as np
import os
import time
from pysmurf.base import SmurfBase
from scipy import optimize
import scipy.signal as signal


class SmurfTuneMixin(SmurfBase):
    '''
    This contains all the tuning scripts
    '''

    def find_freq(self, band, subband=np.arange(13,115), drive_power=10,
        n_read=2, make_plot=False, save_plot=True):
        '''
        Finds the resonances in a band (and specified subbands)

        Args:
        -----
        band (int) : The band to search

        Optional Args:
        --------------
        subband (int) : An int array for the subbands
        drive_power (int) : The drive amplitude
        n_read (int) : The number sweeps to do per subband
        make_plot (bool) : make the plot frequency sweep. Default False.
        save_plot (bool) : save the plot. Default True.
        save_name (string) : What to name the plot. default find_freq.png
        '''
        f, resp = self.full_band_ampl_sweep(band, subband, drive_power, n_read)

        timestamp = int(time.time())  # ignore fractional seconds

        # Save data
        save_name = '{}_amp_sweep_{}.txt'
        np.savetxt(os.path.join(self.output_dir, 
            save_name.format(timestamp, 'freq')), f)
        np.savetxt(os.path.join(self.output_dir, 
            save_name.format(timestamp, 'resp')), resp)

        # Place in dictionary - dictionary declared in smurf_control
        self.freq_resp[band]['subband'] = subband
        self.freq_resp[band]['f'] = f
        self.freq_resp[band]['resp'] = resp
        if 'timestamp' in self.freq_resp[band]:
            self.freq_resp[band]['timestamp'] = \
                np.append(self.freq_resp[band]['timestamp'], timestamp)
        else:
            self.freq_resp[band]['timestamp'] = np.array([timestamp])

        # Find resonances
        res_freq = self.find_all_peak(self.freq_resp[band]['f'],
            self.freq_resp[band]['resp'], subband)
        self.freq_resp[band]['resonance'] = res_freq

        # Save resonances
        np.savetxt(os.path.join(self.output_dir,
            save_name.format(timestamp, 'resonance')), 
            self.freq_resp[band]['resonance'])

        # Call plotting
        if make_plot:
            self.plot_find_freq(self.freq_resp[band]['f'], 
                self.freq_resp[band]['resp'], save_plot=save_plot, 
                save_name=save_name.replace('.txt', '.png').format(timestamp,
                    band))

        return f, resp

    def plot_find_freq(self, f=None, resp=None, subband=None, filename=None, 
        save_plot=True, save_name='amp_sweep.png'):
        '''
        Plots the response of the frequency sweep. Must input f and resp, or
        give a path to a text file containing the data for offline plotting.

        To do:
        Add ability to use timestamp and multiple plots

        Optional Args:
        --------------
        save_plot (bool) : save the plot. Default True.
        save_name (string) : What to name the plot. default find_freq.png
        '''
        if subband is None:
            subband = np.arange(128)
        subband = np.asarray(subband)

        if (f is None or resp is None) and filename is None:
            self.log('No input data or file given. Nothing to plot.')
            return
        else:
            if filename is not None:
                f = np.loadtxt(filename)
                resp = np.genfromtxt(filename.replace('_freq', '_resp'))

            import matplotlib.pyplot as plt
            cm = plt.cm.get_cmap('viridis')
            fig = plt.figure(figsize=(10,4))

            for i, sb in enumerate(subband):
                color = cm(float(i)/len(subband)/2. + .5*(i%2))
                plt.plot(f[sb,:], np.abs(resp[sb,:]), '.', markersize=4, 
                    color=color)
            plt.title("findfreq response")
            plt.xlabel("Frequency offset (MHz)")
            plt.ylabel("Normalized Amplitude")

            if save_plot:
                plt.savefig(os.path.join(self.plot_dir, save_name),
                    bbox_inches='tight')


    def full_band_ampl_sweep(self, band, subband, drive, N_read):
        """sweep a full band in amplitude, for finding frequencies. This is the
        old, slower method that is replaced by full_band_resp.

        args:
        -----
            band (int) = bandNo (500MHz band)
            subband (int) = which subbands to sweep
            drive (int) = drive power (defaults to 10)
            n_read (int) = numbers of times to sweep, defaults to 2

        returns:
        --------
            freq (list, n_freq x 1) = frequencies swept
            resp (array, n_freq x 2) = complex response
        """
        self.log('This is an older version. Now use full_band_resp()', 
            self.LOG_USER)

        digitizer_freq = self.get_digitizer_frequency_mhz(band)  # in MHz
        n_subbands = self.get_number_sub_bands(band)
        n_channels = self.get_number_channels(band)
        band_center = self.get_band_center_mhz(band)  # in MHz

        subband_width = 2 * digitizer_freq / n_subbands

        scan_freq = np.arange(-3, 3.1, 0.1)  # take out this hardcode

        resp = np.zeros((n_subbands, np.shape(scan_freq)[0]), dtype=complex)
        freq = np.zeros((n_subbands, np.shape(scan_freq)[0]))

        subband_nos, subband_centers = self.get_subband_centers(band)

        self.log('Working on band {:d}'.format(band), self.LOG_INFO)
        for sb in subband:
            self.log('sweeping subband no: {}'.format(sb), self.LOG_INFO)
            f, r = self.fast_eta_scan(band, sb, scan_freq, N_read, 
                drive)
            resp[sb,:] = r
            freq[sb,:] = f
            freq[sb,:] = scan_freq + \
                subband_centers[subband_nos.index(sb)]
        return freq, resp

    def full_band_resp(self, band, n_samples=2**19, make_plot=False, 
        save_data=False):
        """
        
        """
        self.set_noise_select(band, 1, wait_done=True, write_log=True)
        adc = self.read_adc_data(band, n_samples, hw_trigger=True)
        time.sleep(.5)  # Need to wait, otherwise dac call interferes with adc
        # adc = self.read_adc_data(band, n_samples, hw_trigger=True)
        # time.sleep(.5)  # Need to wait, otherwise dac call interferes with adc

        dac = self.read_dac_data(band, n_samples, hw_trigger=True)
        time.sleep(.5)
        # dac = self.read_dac_data(band, n_samples, hw_trigger=True)
        # time.sleep(.5)
        self.set_noise_select(band, 0, wait_done=True, write_log=True)

        if band == 2:
            dac = np.conj(dac)

        # To do : Implement cross correlation to get shift

        f, p_dac = signal.welch(dac, fs=614.4E6, nperseg=n_samples/2)
        f, p_adc = signal.welch(adc, fs=614.4E6, nperseg=n_samples/2)
        f, p_cross = signal.csd(dac, adc, fs=614.4E6, nperseg=n_samples/2)

        resp = p_cross / p_dac

        if make_plot:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(3, figsize=(5,8), sharex=True)
            f_plot = f / 1.0E6
            ax[0].semilogy(f_plot, p_dac)
            ax[0].set_ylabel('DAC')
            ax[1].semilogy(f_plot, p_adc)
            ax[1].set_ylabel('ADC')
            ax[2].semilogy(f_plot, np.abs(p_cross))
            ax[2].set_ylabel('Cross')
            ax[2].set_xlabel('Frequency [MHz]')

            plt.tight_layout()

            fig, ax = plt.subplots(1)
            ax.plot(f_plot, np.log10(np.abs(resp)))
            ax.set_xlim(-250, 250)
            # ax.plot(f_plot, np.real(resp))
            # ax.plot(f_plot, np.imag(resp))

        if save_data:
            save_name = self.get_timestamp() + '_{}_full_band_resp.txt'
            np.savetxt(os.path.join(self.output_dir, save_name.format('freq')), 
                f)
            np.savetxt(os.path.join(self.output_dir, save_name.format('real')), 
                np.real(resp))
            np.savetxt(os.path.join(self.output_dir, save_name.format('imag')), 
                np.imag(resp))
            

        return f, resp

    def peak_finder(self, x, y, threshold):
        """finds peaks in x,y data with some threshhold

        Not currently being used
        """
        in_peak = 0

        peakstruct_max = []
        peakstruct_nabove = []
        peakstruct_freq = []

        for idx in range(len(y)):
            freq = x[idx]
            amp = y[idx]

            if in_peak == 0:
                pk_max = 0
                pk_freq = 0
                pk_nabove = 0

            if amp > threshold:
                if in_peak == 0: # start a new peak
                    n_peaks = n_peaks + 1

                in_peak = 1
                pk_nabove = pk_nabove + 1

                if amp > pk_max: # keep moving until find the top
                    pk_max = amp
                    pk_freq = freq

                if idx == len(y) or y[idx + 1] < threshhold:
                    peakstruct_max.append(pk_max)
                    peakstruct_nabove.append(pk_nabove)
                    peakstruct_freq.append(pk_freq)
                    in_peak = 0
        return peakstruct_max, peakstruct_nabove, peakstruct_freq

    def find_peak(self, freq, resp, make_plot=False, save_plot=True, 
        save_name=None):
        """find the peaks within a given subband

        Args:
        -----
        freq (vector): should be a single row of the broader freq array
        response (complex vector): complex response for just this subband

        Optional Args:
        --------------


        Returns:
        -------_
        resonances (list of floats) found in this subband
        """

        [gradient_locations1] = np.where(np.diff(np.unwrap(np.angle(resp))) 
            < -0.1)
        [gradient_locations2] = np.where(np.diff(np.abs(resp)) > 0.005)
        gradient_locations = list(set(gradient_locations1) & 
            (set(gradient_locations2) | set(gradient_locations2 - 1) |
                set(gradient_locations2 + 1)))


        if make_plot:
            self.plot_find_peak(freq, resp_input, peak_ind, save_plot=save_plot,
                save_name=save_name)

        # return freq[peak_ind]
        return gradient_locations

    def plot_find_peak(self, freq, resp, peak_ind, save_plot=True, 
        save_name=None):
        """
        """
        import matplotlib.pyplot as plt

        Idat = np.real(resp)
        Qdat = np.imag(resp)
        phase = np.unwrap(np.arctan2(Qdat, Idat))
        
        fig, ax = plt.subplots(2, sharex=True, figsize=(6,4))
        ax[0].plot(freq, np.abs(resp), label='amp', color='b')
        ax[0].plot(freq, Idat, label='I', color='r', linestyle=':', alpha=.5)
        ax[0].plot(freq, Qdat, label='Q', color='g', linestyle=':', alpha=.5)
        ax[0].legend(loc='lower right')
        ax[1].plot(freq, phase, color='b')
        ax[1].set_ylim((-np.pi, np.pi))

        if len(peak_ind):  # empty array returns False
            ax[0].plot(freq[peak_ind], np.abs(resp[peak_ind]), 'x', color='k')
            ax[1].plot(freq[peak_ind], phase[peak_ind], 'x', color='k')
        else:
            self.log('No peak_ind values.', self.LOG_USER)

        fig.suptitle("Peak Finding")
        ax[1].set_xlabel("Frequency offset from Subband Center (MHz)")
        ax[0].set_ylabel("Response")
        ax[1].set_ylabel("Phase [rad]")

        if save_plot:
            if save_name is None:
                self.log('Using default name for saving: find_peak.png \n' +
                    'Highly recommended that you input a non-default name')
                save_name = 'find_peak.png'
            else:
                self.log('Plotting saved to {}'.format(save_name))
            plt.savefig(os.path.join(self.plot_dir, save_name),
                bbox_inches='tight')
            plt.close()

    def find_all_peak(self, freq, resp, subband, normalize=False, 
        n_samp_drop=1, threshold=.5, margin_factor=1., phase_min_cut=1, 
        phase_max_cut=1):
        """
        find the peaks within each subband requested from a fullbandamplsweep

        Args:
        -----
        freq (array):  (n_subbands x n_freq_swept) array of frequencies swept
        response (complex array): n_subbands x n_freq_swept array of complex 
            response
        subbands (list of ints): subbands that we care to search in

        Optional Args:
        --------------
        normalize (bool) : 
        n_samp_drop (int) :
        threshold (float) :
        margin_factor (float):
        phase_min_cut (int) :
        phase_max_cut (int) :
        """
        peaks = np.array([])
        subbands = np.array([])

        for sb in subband:
            peak = self.find_peak(freq[sb,:], resp[sb,:], 
                normalize=normalize, n_samp_drop=n_samp_drop, 
                threshold=threshold, margin_factor=margin_factor,
                phase_min_cut=phase_min_cut, phase_max_cut=phase_max_cut,
                make_plot=True, save_plot=True,
                save_name='find_peak_subband{:03}.png'.format(int(sb)))

            if peak is not None:
                peaks = np.append(peaks, peak)
                subbands = np.append(subbands, 
                    np.ones_like(peak, dtype=int)*sb)

        res = np.vstack((peaks, subbands))
        return res

    def fast_eta_scan(self, band, subband, freq, n_read, drive, 
        make_plot=False):
        """copy of fastEtaScan.m from Matlab. Sweeps quickly across a range of
        freq and gets I, Q response

        Args:
         band (int): which 500MHz band to scan
         subband (int): which subband to scan
         freq (n_freq x 1 array): frequencies to scan relative to subband 
            center
         n_read (int): number of times to scan
         drive (int): tone power

        Optional Args:
        make_plot (bool): Make eta plots

        Outputs:
         resp (n_freq x 2 array): real, imag response as a function of 
            frequency
         freq (n_freq x n_read array): frequencies scanned, relative to 
            subband center
        """
        n_subbands = self.get_number_sub_bands(band)
        n_channels = self.get_number_channels(band)

        channel_order = self.get_channel_order(None) # fix this later

        channels_per_subband = int(n_channels / n_subbands)
        first_channel_per_subband = channel_order[0::channels_per_subband]
        subchan = first_channel_per_subband[subband]

        self.set_eta_scan_freq(band, freq)
        self.set_eta_scan_amplitude(band, drive)
        self.set_eta_scan_channel(band, subchan)
        self.set_eta_scan_dwell(band, 0)

        self.set_run_eta_scan(band, 1)

        I = self.get_eta_scan_results_real(band, count=len(freq))
        Q = self.get_eta_scan_results_imag(band, count=len(freq))

        self.band_off(band)

        response = np.zeros((len(freq), ), dtype=complex)

        for index in range(len(freq)):
            Ielem = I[index]
            Qelem = Q[index]
            if Ielem > 2**23:
                Ielem = Ielem - 2**24
            if Qelem > 2**23:
                Qelem = Qelem - 2**24
            
            Ielem = Ielem / 2**23
            Qelem = Qelem / 2**23

            response[index] = Ielem + 1j*Qelem

        if make_plot:
            import matplotlib.pyplot as plt
            # To do : make plotting

        return freq, response

    def setup_notches(self, band, resonance=None, drive=10, sweep_width=.3, 
        sweep_df=.005):
        """

        Args:
        -----
        band (int) : The 500 MHz band to setup.

        Optional Args:
        --------------
        resonance (float array) : A 2 dimensional array with resonance 
            frequencies and the subband they are in. If given, this will take 
            precedent over the one in self.freq_resp.
        drive (int) : The power to drive the resonators. Default 10.
        sweep_width (float) : The range to scan around the input resonance in
            units of MHz. Default .3
        sweep_df (float) : The sweep step size in MHz. Default .005

        Returns:
        --------

        """

        # Check if any resonances are stored
        if 'resonance' not in self.freq_resp[band] and resonance is None:
            self.log('No resonances stored in band {}'.format(band) +
                '. Run find_freq first.', self.LOG_ERROR)
            return

        if resonance is not None:
            input_res = resonance[0,:]
            input_subband = resonance[1,:]
        else:
            input_res = self.freq_resp[band]['resonance'][0]
            input_subband = self.freq_resp[band]['resonance'][1]

        n_subbands = self.get_number_sub_bands(band)
        n_channels = self.get_number_channels(band)
        n_subchannels = n_channels / n_subbands

        # Loop over inputs and do eta scans
        for i, (f, sb) in enumerate(zip(input_res, input_subband)):
            freq, res = fast_eta_scan(band, sb)

    def estimate_eta_parameter(self, freq, resp):
        '''
        Estimates the eta parameter.

        Args:
        -----
        freq (float array) : The frequency of the eta scan
        resp (imag array) : The response of the eta scan

        Returns:
        --------

        '''
        I = np.real(resp)
        Q = np.imag(resp)
        amp = np.sqrt(I**2 + Q**2)

        # Define helper functions
        def calc_R(xc, yc):
            """ 
            calculate the distance of each 2D points from the center (xc, yc)
            """
            return np.sqrt((I-xc)**2 + (Q-yc)**2)

        def f_2(c):
            """
            Calculate the algebraic distance between the data points and the 
            mean circle centered at c=(xc, yc)
            """
            Ri = calc_R(*c)
            return Ri - np.mean(Ri)

        f = np.mean(I), np.mean(Q)
        center_est, ier = optimize.leastsq(f_2, f)

        I2, Q2 = center_est
        Ri = calc_R(*center_est)
        R = Ri.mean()
        resid = np.sum((Ri - R)**2)

        center_idx = np.ravel(np.where(amp==np.min(amp)))[0]
        left = center_idx - 5
        right = center_idx + 5

        eta = (freq[right]-freq[left])/(resp[right]-resp[left])

        return I2, Q2, R, resid, eta


    def plot_eta_estimate(self, freq, resp, Ic=None, Qc=None, r=None, eta=None):
        """
        """
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec

        I = np.real(resp)
        Q = np.imag(resp)
        amp = np.sqrt(I**2 + Q**2)
        phase = np.unwrap(np.arctan2(Q, I))  # radians

        center_idx = np.ravel(np.where(amp==np.min(amp)))[0]

        fig = plt.figure(figsize=(8,4.5))
        gs=GridSpec(2,3)
        ax0 = fig.add_subplot(gs[0,0])
        ax1 = fig.add_subplot(gs[1,0], sharex=ax0)
        ax2 = fig.add_subplot(gs[:,1:])
        ax0.plot(freq, I, label='I', linestyle=':', color='k')
        ax0.plot(freq, Q, label='Q', linestyle='--', color='k')
        ax0.scatter(freq, amp, c=np.arange(len(freq)), s=3,
            label='amp')
        ax0.legend()
        ax0.set_ylabel('Resp')

        idx = np.arange(-5,5.1,5, dtype=int)+center_idx
        ax0.plot(freq[idx], amp[idx], 'rx')

        ax1.scatter(freq, np.rad2deg(phase), c=np.arange(len(freq)), s=3)
        ax1.plot(freq[idx], np.rad2deg(phase[idx]), 'rx')
        ax1.set_ylabel('Phase [deg]')

        # IQ circle
        ax2.axhline(0, color='k', linestyle=':', alpha=.5)
        ax2.axvline(0, color='k', linestyle=':', alpha=.5)

        ax2.scatter(I, Q, c=np.arange(len(freq)), s=3)
        if Ic is not None and Qc is not None and r is not None:
            i = np.arange(0,2*np.pi+.05, .05)
            i_model = r*np.sin(i) + Ic
            q_model = r*np.cos(i) + Qc
            ax2.plot(i_model, q_model, color='k')

            respp = eta*resp
            Ip = np.real(respp)
            Qp = np.imag(respp)
            ax2.scatter(Ip, Qp, c=np.arange(len(freq)), s=3)


        plt.tight_layout()


    def tracking_setup(self, band, channel, reset_rate_khz=4., write_log=False):
        """
        Args:
        -----
        band (int) : The band number
        channel (int) : The channel to check
        """

        self.set_cpld_reset(1)
        self.set_cpld_reset(0)

        fraction_full_scale = .99

        # To do: Move to experiment config
        flux_ramp_full_scale_to_phi0 = 2.825/0.75

        lms_delay   = 6  # nominally match refPhaseDelay
        lms_gain    = 7  # incrases by power of 2, can also use etaMag to fine tune
        lms_enable1 = 1  # 1st harmonic tracking
        lms_enable2 = 1  # 2nd harmonic tracking
        lms_enable3 = 1  # 3rd harmonic tracking
        lms_rst_dly  = 31  # disable error term for 31 2.4MHz ticks after reset
        lms_freq_hz  = flux_ramp_full_scale_to_phi0 * fraction_full_scale*\
            (reset_rate_khz*10^3)  # fundamental tracking frequency guess
        lms_delay2    = 255  # delay DDS counter resets, 307.2MHz ticks
        lms_delay_fine = 0
        iq_stream_enable = 0  # stream IQ data from tracking loop

        self.set_lms_delay(band, lms_delay, write_log=write_log)
        self.set_lms_dly_fine(band, lms_delay_fine, write_log=write_log)
        self.set_lms_gain(band, lms_gain, write_log=write_log)
        self.set_lms_enable1(band, lms_enable1, write_log=write_log)
        self.set_lms_enable2(band, lms_enable2, write_log=write_log)
        self.set_lms_enable3(band, lms_enable3, write_log=write_log)
        self.set_lms_rst_dly(band, lms_rst_dly, write_log=write_log)
        self.set_lms_freq_hz(band, lms_freq_hz, write_log=write_log)
        self.set_lms_delay2(band, lms_delay2, write_log=write_log)
        self.set_iq_stream_enable(band, iq_stream_enable, write_log=write_log)

        self.flux_ramp_setup(reset_rate_khz, fraction_full_scale, 
            write_log=write_log)

        # self.set_lms_freq_hz(lms_freq_hz)

        self.flux_ramp_on(write_log=write_log)

        self.set_iq_stream_enable(band, 1, write_log=write_log)

    def flux_ramp_setup(self, reset_rate_khz, fraction_full_scale, df_range=.1, 
        do_read=False):
        """
        """
        # Disable flux ramp
        self.set_cfg_reg_ena_bit(0)
        digitizerFrequencyMHz=614.4
        dspClockFrequencyMHz=digitizerFrequencyMHz/2

        desiredRampMaxCnt = ((dspClockFrequencyMHz*10^3)/
            (desiredResetRatekHz)) - 1
