import torch
import numpy as np
import os

class ToTensor(object):
    """Convert ndarrays in sample to Tensors."""

    def __call__(self, sample):
        return torch.from_numpy(sample).float()


class ToNormalized(object):
    """Normalize."""

    def __init__(self, path, mean_filename, std_filename):
        self.mean = np.load(os.path.join(path, mean_filename)).T
        self.std = np.load(os.path.join(path, std_filename)).T


    def __call__(self, sample):
        np.seterr(divide='ignore', invalid='ignore')
        return np.nan_to_num((sample.T-self.mean)/self.std).T
