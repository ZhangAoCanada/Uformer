
import numpy as np
import os,sys,math
import argparse
from tqdm import tqdm
from einops import rearrange, repeat

import torch.nn as nn
import torch
from torch.utils.data import DataLoader
import torch.nn.functional as F
from ptflops import get_model_complexity_info

sys.path.append('/content/drive/MyDrive/DERAIN/Uformer')

import scipy.io as sio
from utils.loader import get_validation_data
import utils

from model import UNet,Uformer,Uformer_Cross,Uformer_CatCross

from skimage import img_as_float32, img_as_ubyte
from skimage.metrics import peak_signal_noise_ratio as psnr_loss
from skimage.metrics import structural_similarity as ssim_loss
from collections import OrderedDict
from skimage.measure import compare_psnr, compare_ssim
import cv2, time
from torchinfo import summary


# ----------------- from TransWeather ------------------
def calc_psnr(im1, im2):
    im1, im2 = img_as_ubyte(im1), img_as_ubyte(im2)
    im1_y = cv2.cvtColor(im1, cv2.COLOR_BGR2YCR_CB)[:, :, 0]
    im2_y = cv2.cvtColor(im2, cv2.COLOR_BGR2YCR_CB)[:, :, 0]
    ans = [compare_psnr(im1_y, im2_y)]
    return ans

def calc_ssim(im1, im2):
    im1, im2 = img_as_ubyte(im1), img_as_ubyte(im2)
    im1_y = cv2.cvtColor(im1, cv2.COLOR_BGR2YCR_CB)[:, :, 0]
    im2_y = cv2.cvtColor(im2, cv2.COLOR_BGR2YCR_CB)[:, :, 0]
    ans = [compare_ssim(im1_y, im2_y)]
    return ans
# ------------------------------------------------------


def load_checkpoint(model, weights):
    # checkpoint = torch.load(weights, map_location=torch.device('cpu'))
    checkpoint = torch.load(weights)
    try:
        model.load_state_dict(checkpoint["state_dict"])
    except:
        state_dict = checkpoint["state_dict"]
        new_state_dict = OrderedDict()
        for k, v in state_dict.items():
            name = k[7:] if 'module.' in k else k
            new_state_dict[name] = v
        model.load_state_dict(new_state_dict)

parser = argparse.ArgumentParser(description='RGB denoising evaluation on the validation set of SIDD')
parser.add_argument('--input_dir', default='/content/drive/MyDrive/DERAIN/test/',
    type=str, help='Directory of validation images')
parser.add_argument('--result_dir', default='./results/',
    type=str, help='Directory for results')
parser.add_argument('--weights', default='./logs/Uformer_/models/model_best.pth',
    type=str, help='Path to weights')
parser.add_argument('--gpus', default='0', type=str, help='CUDA_VISIBLE_DEVICES')
parser.add_argument('--arch', default='Uformer', type=str, help='arch')
parser.add_argument('--batch_size', default=1, type=int, help='Batch size for dataloader')
parser.add_argument('--save_images', action='store_true', help='Save denoised images in result directory')
parser.add_argument('--embed_dim', type=int, default=32, help='number of data loading workers')    
parser.add_argument('--win_size', type=int, default=8, help='number of data loading workers')
parser.add_argument('--token_projection', type=str,default='linear', help='linear/conv token projection')
parser.add_argument('--token_mlp', type=str,default='leff', help='ffn/leff token mlp')
# args for vit
parser.add_argument('--vit_dim', type=int, default=256, help='vit hidden_dim')
parser.add_argument('--vit_depth', type=int, default=12, help='vit depth')
parser.add_argument('--vit_nheads', type=int, default=8, help='vit hidden_dim')
parser.add_argument('--vit_mlp_dim', type=int, default=512, help='vit mlp_dim')
parser.add_argument('--vit_patch_size', type=int, default=16, help='vit patch_size')
parser.add_argument('--global_skip', action='store_true', default=False, help='global skip connection')
parser.add_argument('--local_skip', action='store_true', default=False, help='local skip connection')
parser.add_argument('--vit_share', action='store_true', default=False, help='share vit module')

parser.add_argument('--train_ps', type=int, default=128, help='patch size of training sample')
args = parser.parse_args()


# os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
# os.environ["CUDA_VISIBLE_DEVICES"] = args.gpus
# os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
# os.environ["CUDA_VISIBLE_DEVICES"] = args.gpus

utils.mkdir(args.result_dir)

test_dataset = get_validation_data(args.input_dir)
test_loader = DataLoader(dataset=test_dataset, batch_size=1, shuffle=False, num_workers=8, drop_last=False)

model_restoration= utils.get_arch(args)
summary(model_restoration)
model_restoration = torch.nn.DataParallel(model_restoration)

load_checkpoint(model_restoration,args.weights)
print("===>Testing using weights: ", args.weights)

model_restoration.cuda()
model_restoration.eval()


def expand2square(timg,factor=16.0):
    _, _, h, w = timg.size()

    X = int(math.ceil(max(h,w)/float(factor))*factor)

    img = torch.zeros(1,3,X,X).type_as(timg) # 3, h,w
    mask = torch.zeros(1,1,X,X).type_as(timg)

    # print(img.size(),mask.size())
    # print((X - h)//2, (X - h)//2+h, (X - w)//2, (X - w)//2+w)
    img[:,:, ((X - h)//2):((X - h)//2 + h),((X - w)//2):((X - w)//2 + w)] = timg
    mask[:,:, ((X - h)//2):((X - h)//2 + h),((X - w)//2):((X - w)//2 + w)].fill_(1.0)
    
    return img, mask


with torch.no_grad():
    all_inference_time = []
    psnr_list = []
    ssim_list = []
    # psnr_val_rgb = []
    # ssim_val_rgb = []
    for ii, data_test in enumerate(tqdm(test_loader), 0):

        ## TEST THE EFFECT IN DIFFERENT SIZE
        # xsize = (456,234)
        # rgb_gt = F.interpolate(data_test[0],size=xsize).numpy().squeeze().transpose((1,2,0))
        # rgb_noisy, mask = expand2square(F.interpolate(data_test[1].cuda(),size=xsize), factor=64)

        # rgb_gt = data_test[0].numpy().squeeze().transpose((1,2,0))
        # The factor is calculated (window_size(8) * down_scale(2^4) in this case) 
        # rgb_noisy, mask = expand2square(data_test[1].cuda(), factor=128) 
        # rgb_noisy, mask = expand2square(data_test[1], factor=128) 
        filenames = data_test[2]
        
        rgb_gt = data_test[0]
        rgb_noisy = data_test[1]

        rgb_gt = rgb_gt.cuda()
        rgb_noisy = rgb_noisy.cuda() 

        # rgb_restored = model_restoration(rgb_noisy, 1 - mask)
        # rgb_restored = torch.masked_select(rgb_restored,mask.bool()).reshape(1,3,rgb_gt.shape[0],rgb_gt.shape[1])
        start_time = time.time()
        rgb_restored = model_restoration(rgb_noisy)
        rgb_restored = torch.clamp(rgb_restored,0,1).cpu().numpy().squeeze().transpose((1,2,0))
        all_inference_time.append(time.time() - start_time)

        rgb_gt = rgb_gt.cpu().numpy().squeeze().transpose((1,2,0))
        # psnr_val_rgb.append(psnr_loss(rgb_restored, rgb_gt))
        # ssim_val_rgb.append(ssim_loss(rgb_restored, rgb_gt, multichannel=True))

        # if args.save_images:

        # --- Calculate the average PSNR --- #
        psnr_list.extend(calc_psnr(rgb_restored, rgb_gt))
        # --- Calculate the average SSIM --- #
        ssim_list.extend(calc_ssim(rgb_restored, rgb_gt))

        image_cv = img_as_ubyte(rgb_restored)
        utils.save_img(os.path.join(args.result_dir,filenames[0]), img_as_ubyte(rgb_restored))

# psnr_val_rgb = sum(psnr_val_rgb)/(len(test_dataset)+1e-10)
# ssim_val_rgb = sum(ssim_val_rgb)/(len(test_dataset)+1e-10)
# print("PSNR: %f, SSIM: %f " %(psnr_val_rgb,ssim_val_rgb))

avr_psnr = sum(psnr_list) / (len(psnr_list) + 1e-10)
avr_ssim = sum(ssim_list) / (len(ssim_list) + 1e-10)
print("[RESULTS] PSNR: {:.4f}, SSIM: {:.4f}, Average time: {:.4f} ms".format(avr_psnr, avr_ssim, np.mean(all_inference_time)*1000))
