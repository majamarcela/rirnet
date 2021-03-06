from __future__ import print_function
from rirnet_database import RirnetDatabase
from datetime import datetime, timedelta
from torch.autograd import Variable
from importlib import import_module
from glob import glob
from pyroomacoustics.utilities import fractional_delay

import sys
import torch
import os
import csv
import signal

import torch.nn.functional as F
import torch.optim as optim
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import rirnet.misc as misc

# -------------  Initialization  ------------- #
class Model:
    def __init__(self, model_dir):
        self.model_dir = model_dir
        sys.path.append(model_dir)
        extractor = import_module('extractor')
        self.extractor, self.epoch = misc.load_latest(model_dir, 'extractor')
        self.autoenc, _ = misc.load_latest(model_dir, 'autoencoder')
        self.extractor_args = self.extractor.args()

        use_cuda = not self.extractor_args.no_cuda and torch.cuda.is_available()
        self.device = torch.device("cuda" if use_cuda else "cpu")
        self.extractor.to(self.device)
        self.autoenc.to(self.device)
        self.kwargs = {'num_workers': 1, 'pin_memory': True} if use_cuda else {}

        self.extractor_optimizer = optim.Adam(self.extractor.parameters(), lr=self.extractor_args.lr, betas=(0.9, 0.99), eps=1e-5, weight_decay=0, amsgrad=False)

        if self.epoch != 0:
            self.extractor_optimizer.load_state_dict(torch.load(os.path.join(model_dir, '{}_opt_extractor.pth'.format(self.epoch))))
            for g in self.extractor_optimizer.param_groups:
                g['lr'] = self.extractor_args.lr
                g['momentum'] = self.extractor_args.momentum

        data_transform = self.extractor.data_transform()
        target_transform = self.extractor.target_transform()

        train_db = RirnetDatabase(is_training = True, args = self.extractor_args, data_transform = data_transform, target_transform = target_transform)
        eval_db = RirnetDatabase(is_training = False, args = self.extractor_args, data_transform = data_transform, target_transform = target_transform)
        self.train_loader = torch.utils.data.DataLoader(train_db, batch_size=self.extractor_args.batch_size, shuffle=True, **self.kwargs)
        self.eval_loader = torch.utils.data.DataLoader(eval_db, batch_size=self.extractor_args.batch_size, shuffle=True, **self.kwargs)

        self.extractor_mean_train_loss = 0
        self.extractor_mean_eval_loss = 0

        try:
            getattr(F, self.extractor_args.loss_function)
        except AttributeError:
            print('AttributeError! {} is not a valid loss function. The string must exactly match a pytorch loss '
                  'function'.format(self.extractor_args.loss_function))
            sys.exit()


    def train(self):
        self.extractor.train()
        extractor_loss_latent_list = []
        extractor_loss_output_list = []
        for batch_idx, (source, target) in enumerate(self.train_loader):
            torch.cuda.empty_cache()

            source, target = source.to(self.device), target.to(self.device)

            latent_target = self.autoenc(target, encode=True, decode=False)
            latent_source = self.extractor(source)
            extractor_loss = 0
            self.extractor_optimizer.zero_grad()
            extractor_loss_latent = self.mse_weighted(latent_source, latent_target, 10)
            extractor_loss += extractor_loss_latent

            output = self.autoenc(latent_source, encode=False, decode=True)
            extractor_loss_output = self.chamfer_loss(output, target)
            #extractor_loss += extractor_loss_output
            extractor_loss_latent.backward()
            self.extractor_optimizer.step()

            extractor_loss_latent_list.append(extractor_loss_latent.item())
            extractor_loss_output_list.append(extractor_loss_output.item())

            if batch_idx % self.extractor_args.log_interval == 0:
                print('Train Epoch: {:5d} [{:5d}/{:5d} ({:4.1f}%)]\tLatent loss: {:.6f}\t Output loss: {:.6f}'.format(
                    self.epoch + 1, batch_idx * len(source), len(self.train_loader.dataset),
                    100. * batch_idx / len(self.train_loader), extractor_loss_latent.item(), extractor_loss_output.item()))
        self.extractor_mean_train_loss_latent = np.mean(extractor_loss_latent_list)
        self.extractor_mean_train_loss_output = np.mean(extractor_loss_output_list)

        self.latent_target_im_train = latent_target.cpu().detach().numpy()[0]
        self.latent_output_im_train = latent_source.cpu().detach().numpy()[0]

    def evaluate(self):
        self.extractor.eval()
        eval_loss_list = []
        eval_loss_list_latent = []
        with torch.no_grad():
            for batch_idx, (source, target) in enumerate(self.eval_loader):
                torch.cuda.empty_cache()
                source, target = source.to(self.device), target.to(self.device)

                latent_target = self.autoenc(target, encode=True, decode=False)
                latent_source = self.extractor(source)

                eval_loss_list_latent.append(self.mse_weighted(latent_source, latent_target, 10).item())

                output = self.autoenc(latent_source, encode=False, decode=True)
                output_source = self.autoenc(latent_target, encode=False, decode=True)
                extractor_loss = self.chamfer_loss(output, target)

                self.rir_im = []
                eval_loss_list.append(extractor_loss.item())
        self.latent_target_im_eval = latent_target.cpu().detach().numpy()[0]
        self.latent_output_im_eval = latent_source.cpu().detach().numpy()[0]

        self.target_im = target.cpu().detach().numpy()[0].T
        self.output_im = output.cpu().detach().numpy()[0].T
        self.source_im = output_source.cpu().detach().numpy()[0].T
        self.source2_im = source.cpu().detach().numpy()[0].T

        eval_loss_list = np.sort(eval_loss_list)
        self.mean_eval_loss = np.mean(eval_loss_list[:-1])
        eval_loss_list_latent = np.sort(eval_loss_list_latent)
        self.mean_eval_loss_latent = np.mean(eval_loss_list_latent[:-1])
        print('Latent loss eval:', self.mean_eval_loss_latent)
        print('Output loss eval:', self.mean_eval_loss)

    def mse_weighted(self, output, target, weight):
        return torch.sum(weight * (output - target)**2)/output.numel()

    def chamfer_loss(self, output, target):
        x,y = output.permute(0,2,1), target.permute(0,2,1)
        B, N, D = x.size()
        xx = torch.bmm(x, x.transpose(2,1))
        yy = torch.bmm(y, y.transpose(2,1))
        zz = torch.bmm(x, y.transpose(2,1))
        diag_ind = torch.arange(0, N).type(torch.cuda.LongTensor)
        rx = xx[:, diag_ind, diag_ind].unsqueeze(1).expand_as(xx)
        ry = yy[:, diag_ind, diag_ind].unsqueeze(1).expand_as(yy)
        P = (rx.transpose(2, 1) + ry - 2*zz)
        l1 = torch.mean(P.min(1)[0])
        l2 = torch.mean(P.min(2)[0])
        return 10*(l1 + l2)

    def reconstruct_rir(self, output):
        fdl = 81
        fdl2 = (fdl-1) // 2
        time = (output[:,0].astype('double')+1)*1024
        peaks = np.exp(-output[:,1]).astype('double')
        ir = np.arange(np.ceil((1.05*time.max()) + fdl))*0
        for i in range(time.shape[0]):
            time_ip = int(np.round(time[i]))
            time_fp = time[i] - time_ip
            ir[time_ip-fdl2:time_ip+fdl2+1] += peaks[i]*fractional_delay(time_fp)
        start_ind = min(np.where(ir != 0)[0])
        ir = ir[start_ind:-3000]
        return ir

    def save_model(self):
        print(' '+'-'*64, '\nSaving\n', '-'*64)
        model_full_path = os.path.join(self.model_dir, '{}_extractor.pth'.format(str(self.epoch)))
        optimizer_full_path = os.path.join(self.model_dir, '{}_opt_extractor.pth'.format(str(self.epoch)))
        torch.save(self.extractor.state_dict(), model_full_path)
        torch.save(self.extractor_optimizer.state_dict(), optimizer_full_path)

    def loss_to_file(self):
        with open('loss_over_epochs_ex.csv', 'a') as csvfile:
            writer = csv.writer(csvfile, delimiter=',')
            writer.writerow([self.epoch, self.extractor_mean_train_loss_latent, self.extractor_mean_train_loss_output, self.mean_eval_loss, self.mean_eval_loss_latent, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

    def generate_plot(self):
        frmt = "%Y-%m-%d %H:%M:%S"
        plot_data = pd.read_csv('loss_over_epochs_ex.csv', header=None)
        epochs_raw, train_l1_raw, train_l2_raw, eval_losses_raw, eval_losses_raw_latent, times_raw = plot_data.values.T

        epochs = [int(epoch) for epoch in list(epochs_raw) if is_number(epoch)]
        l1_train_losses = [float(loss) for loss in list(train_l1_raw) if is_number(loss)]
        l2_train_losses = [float(loss) for loss in list(train_l2_raw) if is_number(loss)]
        eval_losses = [float(loss) for loss in list(eval_losses_raw) if is_number(loss)]
        eval_losses_latent = [float(loss) for loss in list(eval_losses_raw_latent) if is_number(loss)]

        total_time = timedelta(0, 0, 0)
        if np.size(times_raw) > 1:
            start_times = times_raw[epochs_raw == 'started']
            stop_times = times_raw[epochs_raw == 'stopped']
            for i_stop_time, stop_time in enumerate(stop_times):
                total_time += datetime.strptime(stop_time, frmt) - datetime.strptime(start_times[i_stop_time], frmt)
            total_time += datetime.now() - datetime.strptime(start_times[-1], frmt)
            plt.title('Trained for {} hours and {:2d} minutes'.format(int(total_time.days/24 + total_time.seconds//3600), (total_time.seconds//60)%60))

        plt.figure(figsize=(16,9), dpi=110)
        plt.subplot(3,1,1)
        plt.xlabel('Epochs')
        plt.ylabel('Loss ({})'.format(self.extractor_args.loss_function))
        plt.semilogy(epochs, l1_train_losses, label='Latent Train Loss')
        plt.semilogy(epochs, l2_train_losses, label='Output Train Loss')
        plt.semilogy(epochs, eval_losses_latent, label='Latent Eval Loss')
        plt.semilogy(epochs, eval_losses, label='Output Eval Loss')
        plt.legend(loc=3)
        plt.grid(True, 'both')
        plt.title('Loss')

        plt.subplot(3,2,3)
        plt.plot(self.latent_target_im_train, '--ok', linewidth=0.5, markersize=3, label='target0')
        plt.plot(self.latent_output_im_train, '-o', linewidth=0.5, markersize=3, label='output0')
        plt.grid(True)
        plt.legend()
        plt.title('Train latent')

        plt.subplot(3,2,4)
        plt.plot(self.latent_target_im_eval, '--ok', linewidth=0.5, markersize=3, label='target0')
        plt.plot(self.latent_output_im_eval, '-o', linewidth=0.5, markersize=3, label='output0')
        plt.grid(True)
        plt.legend()
        plt.title('Eval latent')

        plt.subplot(3,2,5)
        plt.plot(self.target_im[:,0], self.target_im[:,1], 'o', linewidth=0.5, markersize=2, label='target')
        plt.plot(self.output_im[:,0], self.output_im[:,1], 'x', linewidth=0.5, markersize=2, label='output')
        plt.grid(True)
        plt.legend()
        plt.title('Eval output')

        plt.subplot(3,2,6)
        plt.plot(self.target_im[:,0], self.target_im[:,1], 'o', linewidth=0.5, markersize=2, label='target')
        plt.plot(self.source_im[:,0], self.source_im[:,1], 'x', linewidth=0.5, markersize=2, label='output')
        plt.grid(True)
        plt.legend()
        plt.title('Eval target output')


        plt.tight_layout()
        plt.savefig('complete_pipeline.png')
        plt.close()

        plt.figure()
        plt.plot(self.source2_im)
        plt.savefig('source.png')
        plt.close()


    def stop_session(self):
        with open('loss_over_epochs_ex.csv', 'a') as csvfile:
            writer = csv.writer(csvfile, delimiter=',')
            writer.writerow(['stopped', 'stopped', 'stopped', 'stopped', 'stopped', datetime.now().strftime("%Y-%m-%d %H:%M:%S")])


    def start_session(self):
        with open('loss_over_epochs_ex.csv', 'a') as csvfile:
            writer = csv.writer(csvfile, delimiter=',')
            writer.writerow(['started', 'started', 'started', 'started', 'started', datetime.now().strftime("%Y-%m-%d %H:%M:%S")])



def main(model_dir):
    global interrupted
    interrupted = False
    signal.signal(signal.SIGINT, signal_handler)

    model = Model(model_dir)
    model.start_session()

    for epoch in range(model.epoch, model.extractor_args.epochs + 1):
        model.train()
        model.evaluate()
        model.epoch = epoch+1
        model.loss_to_file()
        model.generate_plot()

        if interrupted:
            print(' '+'-'*64, '\nEarly stopping\n', '-'*64)
            model.stop_session()
            model.save_model()
            break


def signal_handler(signal, frame):
    print(' '+'-'*64, '\nTraining will stop after this epoch\n', '-'*64)
    global interrupted
    interrupted = True


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


if __name__ == '__main__':
    main(sys.argv[1])

