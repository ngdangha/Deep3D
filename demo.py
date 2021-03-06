import tensorflow as tf 
import numpy as np
import cv2

import os
import glob
import platform
import argparse
import time

from mtcnn import MTCNN
from PIL import Image
from scipy.io import loadmat,savemat
from preprocess_img import align_img
from utils import *
from face_decoder import Face3D
from options import Option

is_windows = platform.system() == "Windows"

def parse_args():

    desc = "Deep3DFaceReconstruction"
    parser = argparse.ArgumentParser(description=desc)

    parser.add_argument('--pretrain_weights', type=str, default=None, help='path for pre-trained model')
    parser.add_argument('--use_pb', type=int, default=1, help='validation data folder')

    return parser.parse_args()

def restore_weights(sess,opt):
	var_list = tf.trainable_variables()
	g_list = tf.global_variables()

	# add batch normalization params into trainable variables 
	bn_moving_vars = [g for g in g_list if 'moving_mean' in g.name]
	bn_moving_vars += [g for g in g_list if 'moving_variance' in g.name]
	var_list +=bn_moving_vars

	# create saver to save and restore weights
	saver = tf.train.Saver(var_list = var_list)
	saver.restore(sess,opt.pretrain_weights)

def demo():
	#initialize tic
	tic = time.perf_counter()

	# input and output folder
	args = parse_args()

	image_path = 'input'
	save_path = 'output'
	image_test_path = 'images'
	if not os.path.exists(save_path):
		os.makedirs(save_path)
	img_list =  glob.glob(image_path + '/' + '*.jpg')
	img_list += glob.glob(image_path + '/' + '*.png')
	img_list += glob.glob(image_path + '/' + '*.JPG')
	img_list += glob.glob(image_path + '/' + '*.PNG')

	# read BFM face model
	# transfer original BFM model to our model
	if not os.path.isfile('./BFM/BFM_model_front.mat'):
		transferBFM09()

	# read standard landmarks for preprocessing images
	lm3D = load_lm3d()
	n = 0

	# build reconstruction model
	with tf.Graph().as_default() as graph:
		
		with tf.device('/cpu:0'):
			opt = Option(is_train=False)
		opt.batch_size = 1
		opt.pretrain_weights = args.pretrain_weights
		FaceReconstructor = Face3D()
		images = tf.placeholder(name = 'input_imgs', shape = [opt.batch_size,224,224,3], dtype = tf.float32)

		if args.use_pb and os.path.isfile('network/FaceReconModel.pb'):
			print('Using pre-trained .pb file.')
			graph_def = load_graph('network/FaceReconModel.pb')
			tf.import_graph_def(graph_def,name='resnet',input_map={'input_imgs:0': images})
			# output coefficients of R-Net (dim = 257) 
			coeff = graph.get_tensor_by_name('resnet/coeff:0')
		else:
			print('Using pre-trained .ckpt file: %s'%opt.pretrain_weights)
			import networks
			coeff = networks.R_Net(images, is_training=False)

		# reconstructing faces
		FaceReconstructor.Reconstruction_Block(coeff,opt)
		
		face_shape = FaceReconstructor.face_shape #frontal view
		# face_shape = FaceReconstructor.face_shape_t #original pose
		face_texture = FaceReconstructor.face_texture
		face_color = FaceReconstructor.face_color
		landmarks_2d = FaceReconstructor.landmark_p
		recon_img = FaceReconstructor.render_imgs
		tri = FaceReconstructor.facemodel.face_buf

		with tf.Session() as sess:

			if not args.use_pb :
				restore_weights(sess,opt)

			print('reconstructing...')
			for file in img_list:
				n += 1
				print(n)
				# load images and corresponding 5 facial landmarks
				img,lm = load_img(file,file.replace('png','txt').replace('PNG','txt').replace('jpg','txt').replace('JPG','txt'))
				# preprocess input image
				input_img, lm_new, transform_params = align_img(img,lm,lm3D)

				#save input images after cropped 
				# input_img = np.squeeze(input_img, (0))
				# cv2.imwrite(os.path.join(image_test_path, file.split(os.path.sep)[-1]), input_img)
				# input_img = np.expand_dims(input_img,0)

				coeff_,face_shape_,face_texture_,face_color_,landmarks_2d_,recon_img_,tri_ = sess.run([coeff,\
					face_shape,face_texture,face_color,landmarks_2d,recon_img,tri],feed_dict = {images: input_img})

				# reshape outputs

				input_img = np.squeeze(input_img)
				face_shape_ = np.squeeze(face_shape_, (0))
				face_texture_ = np.squeeze(face_texture_, (0))
				face_color_ = np.squeeze(face_color_, (0))
				landmarks_2d_ = np.squeeze(landmarks_2d_, (0))

				# save output files
				if not is_windows:
					recon_img_ = np.squeeze(recon_img_, (0))
					cv2.imwrite(os.path.join(image_test_path, file.split(os.path.sep)[-1]), recon_img_)
					savemat(os.path.join(save_path,file.split(os.path.sep)[-1].replace('.png','.mat').replace('.PNG','.mat').replace('jpg','mat').replace('JPG','mat')),{'cropped_img':input_img[:,:,::-1],'recon_img':recon_img_,'coeff':coeff_,\
						'face_shape':face_shape_,'face_texture':face_texture_,'face_color':face_color_,'lm_68p':landmarks_2d_,'lm_5p':lm_new})
				# save_obj(os.path.join(save_path,file.split(os.path.sep)[-1].replace('.png','_mesh.obj').replace('.PNG','_mesh.obj').replace('.jpg','_mesh.obj').replace('.JPG','_mesh.obj')),face_shape_,tri_,np.clip(face_color_,0,255)/255) # 3D reconstruction face (in canonical view)
				save_shape(os.path.join(save_path,file.split(os.path.sep)[-1].replace('.png','_mesh.obj').replace('.PNG','_mesh.obj').replace('.jpg','_mesh.obj').replace('.JPG','_mesh.obj')),face_shape_,tri_)
				# save_shape_txt(os.path.join(save_path,file.split(os.path.sep)[-1].replace('.png','_shape.txt').replace('.PNG','_shape_txt').replace('.jpg','_shape.txt').replace('.JPG','_shape.txt')),face_shape_)
	
	#return timer
	toc = time.perf_counter()
	print(f"Created meshes in {toc - tic:0.4f} seconds")

if __name__ == '__main__':
	demo()
