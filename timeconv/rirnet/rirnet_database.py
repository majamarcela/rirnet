#!/usr/bin/env python3

import os
import pandas as pd
from torch.utils.data import Dataset
import numpy as np
import matplotlib.pyplot as plt
import torch

class RirnetDatabase(Dataset):
    """ Data-Target dataset to use with rirnet"""

    def __init__(self, is_training, args, data_transform=None, target_transform=None):
        if is_training:
            csv_file = args.train_db_path
            self.folder = '../../db_fft_horder/train/'
        else:
            csv_file = args.val_db_path
            self.folder = '../../db_fft_horder/val/'
        database = pd.read_csv(csv_file)

        self.dataset = database
        self.data_transform = data_transform
        self.target_transform = target_transform

    def __len__(self):
        return len(self.dataset)


    def __getitem__(self, idx):
        data_path = self.dataset.iloc[idx, 0]
        target_path = self.dataset.iloc[idx, 1]
        data = np.load(data_path)
        target = np.load(target_path)

        if self.data_transform and self.target_transform:
            data = -np.log(data)
            data = self.data_transform(data)
            target = target/np.max(target)
            target = self.target_transform(target)
        return data, target
