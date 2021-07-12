import numpy as np
import matplotlib.pyplot as plt
from NuRadioReco.utilities import units

fiber_names = [
    '7A1',
    '7A2',
    '7A3',
    '7A4',
    '7A5',
    '7A6',
    '7ABLUE',
    '7ABROWN',
    '7AGREEN',
    '7AORANGE'
]
fig1 = plt.figure(figsize=(8, 15))
fig2 = plt.figure(figsize=(8, 15))
for i_fiber, fiber_name in enumerate(fiber_names):
    log_mag_data = np.genfromtxt(
        'data/{}_FULL_LM.csv'.format(fiber_name),
        delimiter=',',
        skip_header=17,
        skip_footer=1
    )
    mag_freqs = log_mag_data[:, 0] * units.Hz
    log_magnitude = log_mag_data[:, 1]
    ax1_1 = fig1.add_subplot(len(fiber_names), 1, i_fiber + 1)
    ax1_1.grid()
    ax1_1.plot(
        mag_freqs / units.MHz,
        np.power(10., -log_magnitude)
    )
    phase_data = np.genfromtxt(
        'data/{}_FULL_P.csv'.format(fiber_name),
        delimiter=',',
        skip_header=17,
        skip_footer=1
    )
    phase_freqs = phase_data[:, 0] * units.Hz
    phase = np.unwrap(phase_data[:, 1] * units.deg)
    group_delay = -1. * np.diff(phase) / np.diff(phase_freqs)
    # phase = (phase_data[:, 1] * units.deg)
    freq_mask = phase_freqs > 25 * units.MHz
    ax2_1 = fig2.add_subplot(len(fiber_names), 2, 2 * i_fiber + 1)
    ax2_1.grid()
    ax2_1.plot(
        phase_freqs[freq_mask] / units.MHz,
        phase[freq_mask]
    )
    line_fit = np.polyfit(
        phase_freqs[freq_mask],
        - phase[freq_mask],
        1
    )
    ax2_1.set_xlabel('f [MHz]')
    ax2_1.set_ylabel('phase [rad]')
    ax2_2 = fig2.add_subplot(len(fiber_names), 2, 2 * i_fiber + 2)
    ax2_2.grid()
    ax2_2.plot(
        phase_freqs[freq_mask][:-1] / units.MHz,
        group_delay[freq_mask[:-1]] / units.ns
    )
    print('Fiber {}: {:.2f}ns'.format(fiber_name, line_fit[0]))
    ax2_2.axhline(
        line_fit[0],
        color='r',
        linestyle=':'
    )
    ax2_2.set_xlabel('f [MHz]')
    ax2_2.set_ylabel(r'$\Delta t$ [ns]')

fig1.tight_layout()
fig1.savefig('fiber_magnitudes.png')

fig2.tight_layout()
fig2.savefig('fiber_phases.png')
