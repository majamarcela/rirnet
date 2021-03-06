import numpy as np
import librosa
import scipy as sp
import os
#import matplotlib.pyplot as plt

def mfcc_to_waveform(mfcc, rate, phase_data=None):
    n_mel = 128
    n_fft = 2048
    n_mfcc = mfcc.shape[0]

    dctm = librosa.filters.dct(n_mfcc, n_mel)
    mel_basis = librosa.filters.mel(rate, n_fft)
    power_spectrum = np.dot(mel_basis.T, 10.**(np.dot(dctm.T, mfcc)/10.))
    amplitude_spectrum = np.sqrt(power_spectrum)
    if phase_data is None:
        phase = np.random.random(np.shape(amplitude_spectrum))*2*np.pi-np.pi
    else:
        phase = np.exp(1j*phase_data)

    waveform = librosa.core.istft(amplitude_spectrum*phase)
    return waveform


def waveform_to_mfcc(waveform, rate, n_mfcc):
    n_fft = 2048
    phase_data, mel_spectrogram = melspectrogram(waveform, rate, n_fft)
    mel_spectrogram_db = librosa.core.power_to_db(mel_spectrogram)
    mfcc = sp.fftpack.dct(mel_spectrogram_db, axis=0, type=2, norm='ortho')[:n_mfcc]
    return phase_data, mfcc


def melspectrogram(waveform, rate=44100, n_fft=2048, hop_length=512, power=2.0, **kwargs):
    complex_spectrum = librosa.core.stft(waveform, n_fft=n_fft, hop_length=hop_length)
    amplitude_spectrum = np.abs(complex_spectrum)
    power_spectrum = amplitude_spectrum**power
    phase_data = np.angle(complex_spectrum)

    mel_basis = librosa.filters.mel(rate, n_fft, **kwargs)
    mel_spectrogram = np.dot(mel_basis, power_spectrum)

    return phase_data, mel_spectrogram


def calculate_delta_features(data_list):
    delta_list = []
    delta_2_list = []
    for data in data_list:
        delta_list.append(librosa.feature.delta(data))
        delta_2_list.append(librosa.feature.delta(data, order=2))
    return delta_list, delta_2_list


def convolve(x, h):
    return sp.signal.fftconvolve(x, h)


def next_power_of_two(x):
    return 1 if x == 0 else 2**(x-1).bit_length()


def pad_to(x, length, value=0):
    return np.pad(x, (0, length - np.size(x)), 'constant', constant_values=value)


def normalize(x):
    return x / np.max(np.abs(x))


def resample(waveform, rate, target_rate):
    return librosa.core.resample(waveform, rate, target_rate)


def play_file(path):
    exitcode = os.system('cvlc ' + path + ' --play-and-exit')
    if exitcode == 32512:
        print('Unable to play file. Please install cvlc.')


def save_wav(path, data, rate = 44100, norm=None):
    librosa.output.write_wav(path, data, rate, norm)


def split_signal(signal, rate = 44100, segment_length = 44100//4, min_energy=100, max_energy=2, hop_length=512, debug=False):
    sound_starts = librosa.onset.onset_detect(signal[:-segment_length], sr=rate, backtrack=False, hop_length=hop_length)*hop_length-256
    if debug:
        import matplotlib.pyplot as plt
        plt.figure()
        plt.plot(signal)
        plt.vlines(sound_starts, -1, 1)
    segment_list = []
    for i, start in enumerate(sound_starts):
        stop = start + int(segment_length)
        energy_before = np.sum(np.abs(signal[start-1000:start]))
        energy_after = np.sum(np.abs(signal[stop-1000:stop]))
        energy = np.sum(np.abs(signal[start:stop]))
        if energy_before < max_energy and energy_after < max_energy and energy > min_energy:
            if debug:
                plt.vlines(start, -1, 1, color='g')
                plt.vlines(stop, -1, 1, color='r')
            segment_list.append(signal[start:stop])
    return segment_list


def read_wav(path, rate=None):
    signal_rate, signal = sp.io.wavfile.read(path)
    signal = signal/np.max(np.abs(signal))
    if rate is not None:
        signal = librosa.core.resample(signal, signal_rate, rate)
    return signal, rate
