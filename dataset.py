from cv2 import sqrBoxFilter
import numpy as np
import os
from torch.utils.data import Dataset
import torch
from utils import is_png_file, load_img, Augment_RGB_torch
import torch.nn.functional as F
import random
import re, cv2

augment   = Augment_RGB_torch()
transforms_aug = [method for method in dir(augment) if callable(getattr(augment, method)) if not method.startswith('_')] 

##################################################################################################
class DataLoaderTrain(Dataset):
    def __init__(self, rgb_dir, img_options=None, target_transform=None):
        super(DataLoaderTrain, self).__init__()

        self.target_transform = target_transform
        
        gt_dir = 'gt'
        input_dir = 'data'

        self.noisy_filenames, self.clean_filenames = self.getImageNames(rgb_dir, input_dir, gt_dir)
        
        self.img_options=img_options

        self.tar_size = len(self.clean_filenames)  # get the size of target
    
    def getImageNames(self, root_dir, image_dir, gt_dir):
        input_dir = os.path.join(root_dir, image_dir)
        output_dir = os.path.join(root_dir, gt_dir)
        image_names_tmp = []
        image_names = []
        gt_names = []
        for file in os.listdir(input_dir):
            if file.endswith(".png"):
                in_name = os.path.join(input_dir, file)
                image_names_tmp.append(in_name)
        for in_name in image_names_tmp:
            image_ind = re.findall(r'\d+', in_name)[0]
            gt_name = os.path.join(output_dir, image_ind + "_clean.png")
            if os.path.exists(gt_name):
                image_names.append(in_name)
                gt_names.append(gt_name)
        return image_names, gt_names

    def __len__(self):
        return self.tar_size

    def __getitem__(self, index):
        tar_index   = index % self.tar_size
        clean = torch.from_numpy(np.float32(load_img(self.clean_filenames[tar_index])))
        noisy = torch.from_numpy(np.float32(load_img(self.noisy_filenames[tar_index])))
        
        clean = clean.permute(2,0,1)
        noisy = noisy.permute(2,0,1)

        clean_filename = os.path.split(self.clean_filenames[tar_index])[-1]
        noisy_filename = os.path.split(self.noisy_filenames[tar_index])[-1]

        #Crop Input and Target
        ps = self.img_options['patch_size']
        H = clean.shape[1]
        W = clean.shape[2]
        # r = np.random.randint(0, H - ps) if not H-ps else 0
        # c = np.random.randint(0, W - ps) if not H-ps else 0
        if H-ps==0:
            r=0
            c=0
        else:
            r = np.random.randint(0, H - ps)
            c = np.random.randint(0, W - ps)
        clean = clean[:, r:r + ps, c:c + ps]
        noisy = noisy[:, r:r + ps, c:c + ps]

        apply_trans = transforms_aug[random.getrandbits(3)]

        clean = getattr(augment, apply_trans)(clean)
        noisy = getattr(augment, apply_trans)(noisy)        

        return clean, noisy, clean_filename, noisy_filename

##################################################################################################

class DataLoaderTrain_Gaussian(Dataset):
    def __init__(self, rgb_dir, noiselevel=5, img_options=None, target_transform=None):
        super(DataLoaderTrain_Gaussian, self).__init__()

        self.target_transform = target_transform
        #pdb.set_trace()
        clean_files = sorted(os.listdir(rgb_dir))
        #noisy_files = sorted(os.listdir(os.path.join(rgb_dir, 'input')))
        #clean_files = clean_files[0:83000]
        #noisy_files = noisy_files[0:83000]
        self.clean_filenames = [os.path.join(rgb_dir, x) for x in clean_files if is_png_file(x)]
        #self.noisy_filenames = [os.path.join(rgb_dir, 'input', x)       for x in noisy_files if is_png_file(x)]
        self.noiselevel = noiselevel
        self.img_options=img_options

        self.tar_size = len(self.clean_filenames)  # get the size of target
        print(self.tar_size)
    def __len__(self):
        return self.tar_size

    def __getitem__(self, index):
        tar_index   = index % self.tar_size
        #print(self.clean_filenames[tar_index])
        clean = np.float32(load_img(self.clean_filenames[tar_index]))
        #noisy = torch.from_numpy(np.float32(load_img(self.noisy_filenames[tar_index])))
        # noiselevel = random.randint(5,20)
        noisy = clean + np.float32(np.random.normal(0, self.noiselevel, np.array(clean).shape)/255.)
        noisy = np.clip(noisy,0.,1.)
        
        clean = torch.from_numpy(clean)
        noisy = torch.from_numpy(noisy)

        clean = clean.permute(2,0,1)
        noisy = noisy.permute(2,0,1)

        clean_filename = os.path.split(self.clean_filenames[tar_index])[-1]
        noisy_filename = os.path.split(self.clean_filenames[tar_index])[-1]

        #Crop Input and Target
        ps = self.img_options['patch_size']
        H = clean.shape[1]
        W = clean.shape[2]
        r = np.random.randint(0, H - ps)
        c = np.random.randint(0, W - ps)
        clean = clean[:, r:r + ps, c:c + ps]
        noisy = noisy[:, r:r + ps, c:c + ps]

        apply_trans = transforms_aug[random.getrandbits(3)]

        clean = getattr(augment, apply_trans)(clean)
        noisy = getattr(augment, apply_trans)(noisy)

        return clean, noisy, clean_filename, noisy_filename
##################################################################################################
class DataLoaderVal(Dataset):
    def __init__(self, rgb_dir, target_transform=None):
        super(DataLoaderVal, self).__init__()

        self.target_transform = target_transform

        gt_dir = 'gt'
        input_dir = 'data'
        
        self.noisy_filenames, self.clean_filenames = self.getImageNames(rgb_dir, input_dir, gt_dir)

        self.tar_size = len(self.clean_filenames)  

    def getImageNames(self, root_dir, image_dir, gt_dir):
        input_dir = os.path.join(root_dir, image_dir)
        output_dir = os.path.join(root_dir, gt_dir)
        image_names_tmp = []
        image_names = []
        gt_names = []
        for file in os.listdir(input_dir):
            if file.endswith(".png"):
                in_name = os.path.join(input_dir, file)
                image_names_tmp.append(in_name)
        for in_name in image_names_tmp:
            image_ind = re.findall(r'\d+', in_name)[0]
            gt_name = os.path.join(output_dir, image_ind + "_clean.png")
            if os.path.exists(gt_name):
                image_names.append(in_name)
                gt_names.append(gt_name)
        return image_names, gt_names

    def __len__(self):
        return self.tar_size

    def __getitem__(self, index):
        tar_index   = index % self.tar_size
        
        clean = np.float32(load_img(self.clean_filenames[tar_index]))
        noisy = np.float32(load_img(self.noisy_filenames[tar_index]))

        w, h, _ = clean.shape
        # square_size = max(w, h)
        square_size = 768
        h_pad, w_pad = square_size - h, square_size - w
        h_half = h_pad // 2
        w_half = w_pad // 2

        clean = np.pad(clean, ((w_half, w_pad - w_half), (h_half, h_pad - h_half), (0, 0)), 'constant', constant_values=0)
        noisy = np.pad(noisy, ((w_half, w_pad - w_half), (h_half, h_pad - h_half), (0, 0)), 'constant', constant_values=0)

        # clean = cv2.resize(clean, (h, w)) 
        # noisy = cv2.resize(noisy, (h, w))

        clean = torch.from_numpy(clean)
        noisy = torch.from_numpy(noisy)
                
        clean_filename = os.path.split(self.clean_filenames[tar_index])[-1]
        noisy_filename = os.path.split(self.noisy_filenames[tar_index])[-1]

        clean = clean.permute(2,0,1)
        noisy = noisy.permute(2,0,1)

        return clean, noisy, clean_filename, noisy_filename

##################################################################################################

class DataLoaderTest(Dataset):
    def __init__(self, rgb_dir, target_transform=None):
        super(DataLoaderTest, self).__init__()

        self.target_transform = target_transform

        noisy_files = sorted(os.listdir(os.path.join(rgb_dir, 'input')))


        self.noisy_filenames = [os.path.join(rgb_dir, 'input', x) for x in noisy_files if is_png_file(x)]
        

        self.tar_size = len(self.noisy_filenames)  

    def __len__(self):
        return self.tar_size

    def __getitem__(self, index):
        tar_index   = index % self.tar_size
        

        noisy = torch.from_numpy(np.float32(load_img(self.noisy_filenames[tar_index])))
                
        noisy_filename = os.path.split(self.noisy_filenames[tar_index])[-1]

        noisy = noisy.permute(2,0,1)

        return noisy, noisy_filename


##################################################################################################

class DataLoaderTestSR(Dataset):
    def __init__(self, rgb_dir, target_transform=None):
        super(DataLoaderTestSR, self).__init__()

        self.target_transform = target_transform

        LR_files = sorted(os.listdir(os.path.join(rgb_dir)))


        self.LR_filenames = [os.path.join(rgb_dir, x) for x in LR_files if is_png_file(x)]
        

        self.tar_size = len(self.LR_filenames)  

    def __len__(self):
        return self.tar_size

    def __getitem__(self, index):
        tar_index   = index % self.tar_size
        

        LR = torch.from_numpy(np.float32(load_img(self.LR_filenames[tar_index])))
                
        LR_filename = os.path.split(self.LR_filenames[tar_index])[-1]

        LR = LR.permute(2,0,1)

        return LR, LR_filename
