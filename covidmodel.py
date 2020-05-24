import os
import matplotlib.pyplot as plt
import random
import cv2
import pandas as pd
import numpy as np
import seaborn as sns
import itertools
import sklearn
import scipy
import skimage
from skimage.transform import resize
import csv
from tqdm import tqdm
from sklearn import model_selection
from sklearn.model_selection import train_test_split, learning_curve,KFold,cross_val_score,StratifiedKFold
from sklearn.utils import class_weight
import keras
import tensorflow as tf
from keras.utils.np_utils import to_categorical
from keras.preprocessing.image import ImageDataGenerator
from keras import models, layers, optimizers
from sklearn.metrics import confusion_matrix, accuracy_score
from keras.optimizers import Adam
from keras.models import Sequential, model_from_json, Model
from keras.layers import Activation, Dense, Dropout, Flatten, Conv2D, MaxPool2D, MaxPooling2D, Lambda,AveragePooling2D, BatchNormalization
from keras import backend as K
from keras.applications.inception_v3 import InceptionV3
from imblearn.over_sampling import RandomOverSampler
from imblearn.under_sampling import RandomUnderSampler
from keras.applications.vgg19 import VGG19
from keras.applications.vgg16 import VGG16
from keras.applications.resnet50 import ResNet50
from keras.callbacks import Callback, EarlyStopping, ReduceLROnPlateau, ModelCheckpoint

wkdir = "./weights/"
pb_filename = "retrained_graph.pb"
label_file = "weights/retrained_labels.txt"
weight_path1 = './weights/vgg16_weights_tf_dim_ordering_tf_kernels_notop.h5'
weight_path2 = './weights/inception_v3_weights_tf_dim_ordering_tf_kernels_notop.h5' 
pretrained_model_1 = VGG16(weights = weight_path1, include_top=False, input_shape=(200, 200, 3))
pretrained_model_2 = InceptionV3(weights = weight_path2, include_top=False, input_shape=(299, 299, 3))


class MetricsCheckpoint(Callback):
    """Callback that saves metrics after each epoch"""
    def __init__(self, savepath):
        super(MetricsCheckpoint, self).__init__()
        self.savepath = savepath
        self.history = {}
    def on_epoch_end(self, epoch, logs=None):
        for k, v in logs.items():
            self.history.setdefault(k, []).append(v)
        np.save(self.savepath, self.history)

def get_data(folder):
    X = []
    y = []
    for folderName in os.listdir(folder):
        if not folderName.startswith('.'):
            if folderName in ['NON-COVID']:
                label = 0
            elif folderName in ['COVID']:
                label = 1
            else:
                label = 2
            for image_filename in tqdm(os.listdir(folder + folderName)):
                img_file = cv2.imread(folder + folderName + '/' + image_filename)
                if img_file is not None:
                    img_file = skimage.transform.resize(img_file, (299,299,3))
                    img_arr = np.asarray(img_file)
                    X.append(img_arr)
                    y.append(label)
    X = np.asarray(X)
    y = np.asarray(y)
    return X,y

def plotKerasLearningCurve():
    plt.figure(figsize=(10,5))
    metrics = np.load('logs.npy')[()]
    filt = ['acc'] # try to add 'loss' to see the loss learning curve
    for k in filter(lambda x : np.any([kk in x for kk in filt]), metrics.keys()):
        l = np.array(metrics[k])
        plt.plot(l, c= 'r' if 'val' not in k else 'b', label='val' if 'val' in k else 'train')
        x = np.argmin(l) if 'loss' in k else np.argmax(l)
        y = l[x]
        plt.scatter(x,y, lw=0, alpha=0.25, s=100, c='r' if 'val' not in k else 'b')
        plt.text(x, y, '{} = {:.4f}'.format(x,y), size='15', color= 'r' if 'val' not in k else 'b')   
    plt.legend(loc=4)
    plt.axis([0, None, None, None])
    plt.grid()
    plt.xlabel('Number of epochs')
    plt.ylabel('Accuracy')

def plot_confusion_matrix(cm, classes,
                          normalize=False,
                          title='Confusion matrix',
                          cmap=plt.cm.Blues):
    """
    This function prints and plots the confusion matrix.
    Normalization can be applied by setting `normalize=True`.
    """
    plt.figure(figsize = (5,5))
    plt.imshow(cm, interpolation='nearest', cmap=cmap)
    plt.title(title)
    plt.colorbar()
    tick_marks = np.arange(len(classes))
    plt.xticks(tick_marks, classes, rotation=90)
    plt.yticks(tick_marks, classes)
    if normalize:
        cm = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]

    thresh = cm.max() / 2.
    for i, j in itertools.product(range(cm.shape[0]), range(cm.shape[1])):
        plt.text(j, i, cm[i, j],
                 horizontalalignment="center",
                 color="white" if cm[i, j] > thresh else "black")
    plt.tight_layout()
    plt.ylabel('True label')
    plt.xlabel('Predicted label')

def plot_learning_curve(history):
    plt.figure(figsize=(8,8))
    plt.subplot(1,2,1)
    plt.plot(history.history['accuracy'])
    plt.plot(history.history['val_accuracy'])
    plt.title('model accuracy')
    plt.ylabel('accuracy')
    plt.xlabel('epoch')
    plt.legend(['train', 'test'], loc='upper left')
    plt.savefig('./accuracy_curve.png')
    plt.subplot(1,2,2)
    plt.plot(history.history['loss'])
    plt.plot(history.history['val_loss'])
    plt.title('model loss')
    plt.ylabel('loss')
    plt.xlabel('epoch')
    plt.legend(['train', 'test'], loc='upper left')
    plt.savefig('./loss_curve.png')

def plotHistogram(a):
    """
    Plot histogram of RGB Pixel Intensities
    """
    plt.figure(figsize=(10,5))
    plt.subplot(1,2,1)
    plt.imshow(a)
    plt.axis('off')
    histo = plt.subplot(1,2,2)
    histo.set_ylabel('Count')
    histo.set_xlabel('Pixel Intensity')
    n_bins = 30
    plt.hist(a[:,:,0].flatten(), bins= n_bins, lw = 0, color='r', alpha=0.5);
    plt.hist(a[:,:,1].flatten(), bins= n_bins, lw = 0, color='g', alpha=0.5);
    plt.hist(a[:,:,2].flatten(), bins= n_bins, lw = 0, color='b', alpha=0.5);

def freeze_session(session, keep_var_names=None, output_names=None, clear_devices=True):
    """
    Freezes the state of a session into a pruned computation graph.
    Creates a new computation graph where variable nodes are replaced by
    constants taking their current value in the session. The new graph will be
    pruned so subgraphs that are not necessary to compute the requested
    outputs are removed.
    @param session The TensorFlow session to be frozen.
    @param keep_var_names A list of variable names that should not be frozen,
                          or None to freeze all the variables in the graph.
    @param output_names Names of the relevant graph outputs.
    @param clear_devices Remove the device directives from the graph for better portability.
    @return The frozen graph definition.
    """
    from tensorflow.python.framework.graph_util import convert_variables_to_constants
    graph = session.graph
    with graph.as_default():
        self.tf.placeholder(tf.int64, shape=[None])
        freeze_var_names = list(set(v.op.name for v in tf.global_variables()).difference(keep_var_names or []))
        output_names = output_names or []
        output_names += [v.op.name for v in tf.global_variables()]
        input_graph_def = graph.as_graph_def()
        if clear_devices:
            for node in input_graph_def.node:
                node.device = ""
        frozen_graph = convert_variables_to_constants(session, input_graph_def,
                                                      output_names, freeze_var_names)
        return frozen_graph

def save(session, directory, filename):
    if not os.path.exists(directory):
        os.makedirs(directory)
    filepath = os.path.join(directory, filename + '.ckpt')
    tf.train.Saver(session, filepath)
    return filepath

def pretrainedNetwork(xtrain, ytrain, xtest, ytest, pretrainedmodel, pretrainedweights, classweight, numclasses, numepochs, optimizer, labels):
    base_model = pretrained_model_2 # Topless
    # Add top layer
    x = base_model.output
    x = Flatten()(x)
    
    predictions = Dense(numclasses, activation='softmax', input_shape=(None, 2))(x)
    model = Model(inputs=base_model.input, outputs=predictions)
    # Train top layer
    for layer in base_model.layers:
        layer.trainable = False
    model.compile(loss='categorical_crossentropy', 
                  optimizer=optimizer, 
                  metrics=['accuracy'])
    callbacks_list = [keras.callbacks.EarlyStopping(monitor='val_acc', patience=3, verbose=1)]
    model.summary()
    # Fit model
    history = model.fit(xtrain,ytrain, epochs=numepochs, class_weight=classweight, validation_data=(xtest,ytest), verbose=1,callbacks = [MetricsCheckpoint('logs')])
    # Evaluate model
    score = model.evaluate(xtest,ytest, verbose=0)
    print('\nKeras CNN - accuracy:', score[1], '\n')
    y_pred = model.predict(xtest)
    print('\n', sklearn.metrics.classification_report(np.where(ytest > 0)[1], np.argmax(y_pred, axis=1), target_names=list(labels.values())), sep='') 
    Y_pred_classes = np.argmax(y_pred,axis = 1) 
    Y_true = np.argmax(ytest,axis = 1) 
    confusion_mtx = confusion_matrix(Y_true, Y_pred_classes) 
    plot_learning_curve(history)
    plt.show()
    plot_confusion_matrix(confusion_mtx, classes = list(labels.values()))
    plt.show()

    model.save('inceptionV3covid.h5')
    return model

def load_graph(model_filepath):
        '''
        Lode trained model.
        '''
        print('Loading model...')
        graph1 = tf.Graph()
        sess1  = tf.InteractiveSession(graph = graph1)

        with tf.gfile.GFile(model_filepath, 'rb') as f:
            graph_def = tf.GraphDef()
            graph_def.ParseFromString(f.read())

        print()
        print('Check out the input placeholders:')
        nodes = [n.name + ' => ' +  n.op for n in graph_def.node if n.op in ('Placeholder')]
        for node in nodes:
            print(node)

        # Define input tensor
        input1 = tf.compat.v1.placeholder(np.float32, shape = [None, 32, 32, 3], name='input')
        dropout_rate = tf.compat.v1.placeholder(tf.float32, shape = [], name = 'dropout_rate')

        tf.import_graph_def(graph_def, {'input': input1, 'dropout_rate': dropout_rate})

        print('Model loading complete!')

import model as tcav_model
class CustomPublicImageModelWrapper(tcav_model.ImageModelWrapper):
    def __init__(self, sess, labels, image_shape,
                endpoints_dict, name, image_value_range):
        super(self.__class__, self).__init__(image_shape)
        
        self.sess = sess
        self.labels = labels
        self.model_name = name
        self.image_value_range = image_value_range

        # get endpoint tensors
        self.ends = {'input': endpoints_dict['input_tensor'], 'prediction': endpoints_dict['prediction_tensor']}
        
        self.bottlenecks_tensors = self.get_bottleneck_tensors()
        
        # load the graph from the backend
        graph = tf.get_default_graph()

        # Construct gradient ops.
        with graph.as_default():
            self.y_input = tf.placeholder(tf.int64, shape=[None])

            self.pred = tf.expand_dims(self.ends['prediction'][0], 0)
            self.loss = tf.reduce_mean(
                tf.nn.softmax_cross_entropy_with_logits_v2(
                    labels=tf.one_hot(
                        self.y_input,
                        self.ends['prediction'].get_shape().as_list()[1]),
                    logits=self.pred))
        self._make_gradient_tensors()


    def id_to_label(self, idx):
        return self.labels[idx]

    def label_to_id(self, label):
        return self.labels.index(label)

    @staticmethod
    def create_input(t_input, image_value_range):
        """Create input tensor."""
        def forget_xy(t):
            """Forget sizes of dimensions [1, 2] of a 4d tensor."""
            zero = tf.identity(0)
            return t[:, zero:, zero:, :]

        t_prep_input = t_input
        if len(t_prep_input.shape) == 3:
            t_prep_input = tf.expand_dims(t_prep_input, 0)
        t_prep_input = forget_xy(t_prep_input)
        lo, hi = image_value_range
        t_prep_input = lo + t_prep_input * (hi-lo)
        return t_input, t_prep_input

    @staticmethod
    def get_bottleneck_tensors():
        """Add Inception bottlenecks and their pre-Relu versions to endpoints dict."""
        graph = tf.get_default_graph()
        bn_endpoints = {}
        for op in graph.get_operations():
            # change this below string to change which layers are considered bottlenecks
            # use 'ConcatV2' for InceptionV3
            # use 'MaxPool' for VGG16 (for example)
            if 'ConcatV2' in op.type:
                name = op.name.split('/')[0]
                bn_endpoints[name] = op.outputs[0]
            
        return bn_endpoints   

def dataProcessing(X_train, y_train, X_test, y_test):
    # Deal with imbalanced class sizes below
    # Make Data 1D for compatability upsampling methods
    X_trainShape = X_train.shape[1]*X_train.shape[2]*X_train.shape[3]
    X_testShape  = X_test.shape[1]*X_test.shape[2]*X_test.shape[3]

    X_trainFlat = X_train.reshape(X_train.shape[0], X_trainShape)
    X_testFlat = X_test.reshape(X_test.shape[0], X_testShape)

    Y_train = y_train
    Y_test  = y_test
    ros     = RandomUnderSampler(sampling_strategy='auto')

    X_trainRos, Y_trainRos = ros.fit_sample(X_trainFlat, Y_train)
    X_testRos, Y_testRos   = ros.fit_sample(X_testFlat, Y_test)

    Y_trainRosHot = to_categorical(Y_trainRos, num_classes = 2)
    Y_testRosHot  = to_categorical(Y_testRos, num_classes = 2)
    
    # Make Data 2D again
    for i in range(len(X_trainRos)):
        height, width, channels = 299,299,3
        X_trainRosReshaped = X_trainRos.reshape(len(X_trainRos),height,width,channels)
    for i in range(len(X_testRos)):
        height, width, channels = 299,299,3
        X_testRosReshaped = X_testRos.reshape(len(X_testRos),height,width,channels)

    class_weight2 = class_weight.compute_class_weight('balanced', np.unique(Y_trainRos), Y_trainRos)

    return X_trainRosReshaped, Y_trainRosHot, X_testRosReshaped, Y_testRosHot, class_weight2

def main():
    map_characters1 = {0: 'No COVID', 1: 'Yes COVID'} 
    dict_characters = map_characters1

    df = pd.DataFrame()
    model_file1  = "./weights/inceptionv3covid.pb"
    
    weight_path1 = './weights/vgg16_weights_tf_dim_ordering_tf_kernels_notop.h5'
    weight_path2 = './weights/inception_v3_weights_tf_dim_ordering_tf_kernels_notop.h5'
    path_s       = './weights/tensorflow_inception_graph.pb'

    train_dir = "./chest_xray/train/"
    test_dir  = "./chest_xray/test/"

    X_train, y_train = get_data(train_dir)
    X_test, y_test = get_data(test_dir)

    plotHistogram(X_train[1])
    y_trainHot = to_categorical(y_train, num_classes = 2)
    y_testHot  = to_categorical(y_test, num_classes = 2)
    
    class_weight1 = class_weight.compute_class_weight('balanced', np.unique(y_train), y_train)
    pretrained_model_1 = VGG16(weights = weight_path1, include_top=False, input_shape=(200, 200, 3))
    pretrained_model_2 = InceptionV3(weights = weight_path2, include_top=False, input_shape=(299, 299, 3))

    optimizer1 = keras.optimizers.Adam(lr=0.0001)

    x_train, y_train, x_test, y_test, class_weights2 = dataProcessing(X_train, y_train, X_test, y_test)

    pretrainedNetwork(x_train, y_train, x_test, y_test, pretrained_model_2, weight_path2, class_weights2, 2, 6, optimizer1, map_characters1)
    
    return 0


if __name__ == "__main__":
    main()
