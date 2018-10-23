import os 
import torchvision.transforms as transforms
from torch.utils.data import Dataset
import tables
import pickle
import numpy as np
import nibabel as nib
from nilearn.image import new_img_like, resample_to_img
from utils import pickle_load

def open_data_file(filename, readwrite="r"):
    return tables.open_file(filename, readwrite)

def random_flip_dimensions(n_dimensions):
    axis = list()
    for dim in range(n_dimensions):
        if np.random.choice([True, False]):
            axis.append(dim)
            
    return axis

def flip_image(image, axis):
    try:
        new_data = np.copy(image.get_data())
        for axis_index in axis:
            new_data = np.flip(new_data, axis=axis_index)
    except TypeError:
        new_data = np.flip(image.get_data(), axis=axis)
        
    return new_img_like(image, data=new_data)

def offset_image(image, offset_factor):
    image_data = image.get_data()
    image_shape = image_data.shape
    
    new_data = np.zeros(image_shape)

    assert len(image_shape) == 3, "Wrong dimessions! Expected 3 but got {0}".format(len(image_shape))
       
    if len(image_shape) == 3: 
        new_data[:] = image_data[0][0][0] # 左上角背景点像素值
        
        oz = int(image_shape[0] * offset_factor[0])
        oy = int(image_shape[1] * offset_factor[1])
        ox = int(image_shape[2] * offset_factor[2])
        if oy >= 0:
            slice_y = slice(image_shape[1]-oy)
            index_y = slice(oy, image_shape[1])
        else:
            slice_y = slice(-oy,image_shape[1])
            index_y = slice(image_shape[1] + oy)
        if ox >= 0:
            slice_x = slice(image_shape[2]-ox)
            index_x = slice(ox, image_shape[2])
        else:
            slice_x = slice(-ox,image_shape[2])
            index_x = slice(image_shape[2] + ox)
        if oz >= 0:
            slice_z = slice(image_shape[0]-oz)
            index_z = slice(oz, image_shape[0])
        else:
            slice_z = slice(-oz,image_shape[0])
            index_z = slice(image_shape[0] + oz)
        new_data[index_z, index_y, index_x] = image_data[slice_z,slice_y,slice_x]            

    return new_img_like(image, data=new_data)
    
def augment_image(image, flip_axis=None, offset_factor=None):
    if flip_axis:
        image = flip_image(image, axis=flip_axis)
    if offset_factor:
        image = offset_image(image, offset_factor=offset_factor)
        
    return image
    
class BratsDataset(Dataset):
    def __init__(self, phase, config):
        super(BratsDataset, self).__init__()
        
        self.config = config
        self.phase = phase
        self.data_file = open_data_file(config["data_file"])
        if phase == "train":
            self.data_ids = config["traing_file"]
        elif phase == "validate":
            self.data_ids = config["validation_file"]
        elif phase == "test":
            self.data_ids = config["test_file"]
        
        self.data_list = pickle_load(self.data_ids)

        
    def __getitem__(self, index):
        item = self.data_list[index]
        input_data = self.data_file.root.data[item] # data shape:(4, 128, 128, 128)
        seg_label = self.data_file.root.truth[item] # truth shape:(1, 128, 128, 128)
        affine = self.data_file.root.affine[item]
        # dimessions of data
        n_dim = len(seg_label[0])
        
        if self.phase == "train":
            if self.config["random_offset"] is not None:
                offset_factor = -0.25 + np.random.random(n_dim)
            else:
                offset_factor = None
            if self.config["random_flip"] is not None:
                flip_axis = random_flip_dimensions(n_dim)
            else:
                flip_axis = None 
            # Apply random offset and flip to each channel according to randomly generated offset factor and flip axis respectively.
            data_list = list()
            for data_channel in range(input_data.shape[0]):
                # Transform ndarray data to Nifti1Image
                channel_image = nib.Nifti1Image(dataobj=input_data[data_channel], affine=affine)
                data_list.append(resample_to_img(augment_image(channel_image, flip_axis=flip_axis, offset_factor=offset_factor), image, interpolation="continuous").get_data())
            input_data = np.asarray(data_list)
            # Transform ndarray segmentation label to Nifti1Image
            seg_image = nib.Nifti1Image(dataobj=seg_label[0], affine=affine)
            seg_label = resample_to_img(augment_image(seg_image, flip_axis=flip_axis, offset_factor=offset_factor), seg_image, interpolation="nearest").get_data()
        elif self.phase == "validate":
            pass
        elif self.phase == "test":
            pass
        # Concatenate to (5, 128, 128, 128) as network output
        final_label = np.concatenate((seg_label, input_data), axis=0)
        
        return input_data， final_label
    
    def __len__(self):
        return len(self.data_list)
    