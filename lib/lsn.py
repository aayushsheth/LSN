# -*- coding: utf-8 -*-
"""
Created on Wed June  8, 2018
@author: Nikhil Bhagwat
"""

# Package imports
import tensorflow as tf
import numpy as np
import time

# Main slim library
slim = tf.contrib.slim

class siamese_net(object):
  
    def __init__(self, net_arch):
              
      self.input_L = tf.placeholder(tf.float32, [None, net_arch['input_shape']],name='baseline')
      self.input_R = tf.placeholder(tf.float32, [None, net_arch['input_shape']],name='follow_up')
      self.aux_gen = tf.placeholder(tf.float32, [None,1],name='apoe')  #apoe4 status
      self.aux_clinical = tf.placeholder(tf.float32, [None,net_arch['aux_clinical_shape']],name='clinical_attr') #demo+clinical scores
      self.labels = tf.placeholder(tf.float32, [None,net_arch['output']],name='trajectory')         
      self.use_aux = True #use aux branch for non-imaging variables
      self.is_training = True  #toggles dropout in slim
      self.dropout = 1
      self.n_layers = net_arch['n_layers']

      with tf.variable_scope("siamese") as scope:
          self.branch_L = self.mlpnet_slim(self.input_L)
          scope.reuse_variables()
          self.branch_R = self.mlpnet_slim(self.input_R)
          
      # Create metrics      
      self.distance = tf.sqrt(tf.reduce_sum(tf.pow(tf.subtract(self.branch_L,self.branch_R),2),1,keepdims=True))
      self.preds = self.get_predictions()
      self.loss = self.get_loss()
      self.accuracy = self.get_accuracy()

    # Individual branch    
    def mlpnet_slim(self, X):
      with slim.arg_scope([slim.fully_connected], activation_fn=tf.nn.relu,
                          weights_regularizer=slim.l2_regularizer(net_arch['reg'])):
        
        # If needed, within the scope layer is made linear by setting activation_fn=None.
        # Creates a fully connected layers 
        for l in range(self.n_layers):
          net = slim.fully_connected(X, net_arch['l{}'.format(l+1)], normalizer_fn=slim.batch_norm, scope='fc{}'.format(l))
          net = slim.dropout(net, self.dropout, is_training=self.is_training)

        # MR output
        MR_predictions = slim.fully_connected(net, net_arch['mr_output'], 
                                              normalizer_fn=slim.batch_norm, scope='MR_prediction')               
 
        return MR_predictions #Later also return end_points 
    
    # Auxilary branch for demographics, genetics, and clinical attributes
    def auxnet(self):
      distance_vec  = tf.concat([self.branch_L,self.branch_R],1,name='MR_embed_concat')
      distance_vec_mod = tf.multiply(distance_vec,self.aux_gen)
      distance_vec_mod_aux = tf.concat([distance_vec_mod,self.aux_clinical],1)
      
      with tf.name_scope('aux_layers'):
        aux_predictions = slim.fully_connected(distance_vec_mod_aux, net_arch['aux_output'],
                                               activation_fn=tf.nn.relu, 
                                               weights_regularizer=slim.l2_regularizer(net_arch['reg']),
                                               normalizer_fn=slim.batch_norm) 
        #aux_predictions = slim.dropout(net, self.dropout, is_training=is_training)
        return aux_predictions
        
    def get_predictions(self):
      if self.use_aux:
        embed_vec = self.auxnet()
      else:
        embed_vec = tf.concat([self.branch_L,self.branch_R],1,name='MR_embed_concat')
        
      penult_predict = slim.fully_connected(embed_vec, net_arch['output'], activation_fn=tf.nn.softmax, 
                                           normalizer_fn=slim.batch_norm, scope='aux_prediction')
      return penult_predict
    
    #-------------- net with basic/raw TF code (without slim) --------------#
    #-------------- not used when slim is used (preferred)------------------#
    def mlpnet(self, X,net_arch):
      l1 = self.mlp(X,net_arch['input_shape'],net_arch['l1'],name='l1')
      l1 = tf.nn.dropout(l1,self.dropout)
      l2 = self.mlp(l1,net_arch['l1'],net_arch['l2'],name='l2')
      l2 = tf.nn.dropout(l2,self.dropout_f)
      l3 = self.mlp(l2,net_arch['l2'],net_arch['l3'],name='l3')
      l3 = tf.nn.dropout(l3,self.dropout)
      l4 = self.mlp(l3,net_arch['l3'],net_arch['l4'],name='l4')
      l4 = tf.nn.dropout(l4,self.dropout)
      output = self.mlp(l4,net_arch['l4'],net_arch['output'],name='output')
      return output
      
    def mlp(self, input_,input_dim,output_dim,name="mlp"):
      with tf.variable_scope(name):
        w = tf.get_variable('w',[input_dim,output_dim],tf.float32,tf.random_normal_initializer(mean = 0.001,stddev=0.02))            
        b = tf.get_variable('b',[output_dim],tf.float32,tf.constant_initializer(0.1))
        return tf.nn.relu(tf.matmul(input_,w)+b)   
    #-----------------------------------------------------------------------#
   
    # Set methods for class variables
    def set_dropout(self, dropout):
      self.dropout = dropout
      
    def set_aux(self, use_aux):
      self.use_aux = use_aux
      
    def set_train_mode(self,is_training):  
      self.is_training = is_training
      
    # Get methods for loss and acc metrics
    def get_loss(self):            
      return tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(labels=self.labels,logits=self.preds)) 

    def get_accuracy(self):
      correct_preds = tf.equal(tf.argmax(self.labels,1), tf.argmax(self.preds,1))
      return tf.reduce_mean(tf.cast(correct_preds, tf.float32)) 
       
    
# Other helper functions
def next_batch(s,e,mr_inputs,aux_inputs,labels):
    input1 = mr_inputs[s:e,0]
    input2 = mr_inputs[s:e,1]        
    input3 = aux_inputs[s:e,:]
    y = labels[s:e,:]    
    return input1,input2,input3,y
  
  
def check_data_shapes(data,net_arch):
  check = True
  n_layers = net_arch['n_layers']
  if data['X_MR'].shape[1] != 2:
    print('wrong input data dimensions - need MR data for two branches')
    check = False
  elif data['X_MR'].shape[2] != net_arch['input_shape']:
    print('input MR data <-> LSN arch mismatch')
    check = False
  elif data['X_aux'].shape[1] != net_arch['aux_clinical_shape']+1:
    print('input aux data <-> LSN arch mismatch')
    check = False
  elif data['y'].shape[1] != net_arch['output']:
    print('number of classes (2,3) <-> LSN arch mismatch')
    check = False
  else:
    for l in range(n_layers):
      try:
        _ = net_arch['l{}'.format(l+1)]
      except:
        print('Specify number of nodes for layer {}'.format(l))
        check = False        
  
  return check

# Train and test defs
def train_lsn(sess, lsn, data, optimizer, n_epochs, batch_size, dropout, validate_after):
  valid_frac = int(0.1*len(data['y']))

  # Training cycle
  for epoch in range(n_epochs):
      avg_loss = 0.
      avg_acc = 0.
  
      # Split into train and valid data for hyperparam tuning
      X_MR_train = data['X_MR'][:1-valid_frac]
      X_aux_train = data['X_aux'][:1-valid_frac]
      y_train = data['y'][:1-valid_frac]
      
      X_MR_valid = data['X_MR'][1-valid_frac:]
      X_aux_valid = data['X_aux'][1-valid_frac:]
      y_valid = data['y'][1-valid_frac:]
      
      total_batch = int(len(y_valid)/batch_size)
      
      start_time = time.time()
      # Loop over all batches
      for i in range(total_batch):
          s  = i * batch_size
          e = (i+1) *batch_size

          # Fit training using batch data
          MR_L_batch,MR_R_batch,aux_batch,y_batch = next_batch(s,e,X_MR_train,X_aux_train,y_train)
          
          # Train pass
          lsn.set_dropout(dropout)
          _,distance,preds,loss_value,acc_value=sess.run([optimizer,lsn.distance,lsn.preds,lsn.loss,lsn.accuracy], 
                                        feed_dict={lsn.input_L:MR_L_batch,
                                                   lsn.input_R:MR_R_batch,
                                                   lsn.aux_gen:aux_batch[:,0:1],
                                                   lsn.aux_clinical:aux_batch[:,1:],
                                                   lsn.labels:y_batch})                

          avg_loss += loss_value
          avg_acc +=acc_value*100

      duration = time.time() - start_time
      print('epoch %d  time: %.2f loss %0.4f acc %0.2f' %(epoch,duration,avg_loss/total_batch,avg_acc/total_batch))      
  
      #Compute perf on entire training and validation sets (no need after every epoch)
      if epoch%validate_after == 0:
        train_acc = lsn.accuracy.eval(feed_dict={lsn.input_L:X_MR_train[:,0,:],lsn.input_R:X_MR_train[:,1,:],
                                     lsn.aux_gen:X_aux_train[:,0:1],lsn.aux_clinical:X_aux_train[:,1:],
                                     lsn.labels:y_train})
        valid_acc = lsn.accuracy.eval(feed_dict={lsn.input_L:X_MR_valid[:,0,:],lsn.input_R:X_MR_valid[:,1,:],
                                     lsn.aux_gen:X_aux_valid[:,0:1],lsn.aux_clinical:X_aux_valid[:,1:],
                                     lsn.labels:y_valid})
        print('performance on entire train and valid subsets')
        print('epoch {}\t train_acc:{}\t valid_acc:{}\n'.format(epoch,train_acc,valid_acc))
  
  # -----------TODO--------------
  # Save trained model
  # -----------TODO--------------
      
  # Post training: Compute preds and metrics for entire train data
  X_MR_train = data['X_MR']
  X_aux_train = data['X_aux']
  y_train = data['y']
  train_feature_L = lsn.branch_L.eval(feed_dict={lsn.input_L:X_MR_train[:,0,:]})
  train_feature_R = lsn.branch_R.eval(feed_dict={lsn.input_R:X_MR_train[:,1,:]})    
  train_preds= lsn.preds.eval(feed_dict={lsn.input_L:X_MR_train[:,0,:],lsn.input_R:X_MR_train[:,1,:],
                                  lsn.aux_gen:X_aux_train[:,0:1],lsn.aux_clinical:X_aux_train[:,1:]})

  train_metrics = {'train_feature_L':train_feature_L,'train_feature_R':train_feature_R,'train_preds':train_preds}

  return lsn, train_metrics

def test_lsn(sess,lsn,data):
  print('Testing model')    
  lsn.set_dropout(1)
  lsn.set_train_mode(False) 
  X_MR_test = data['X_MR']
  X_aux_test = data['X_aux']
  y_test = data['y']
  #print(lsn.dropout)
  
  test_feature_L = lsn.branch_L.eval(feed_dict={lsn.input_L:X_MR_test[:,0,:]})
  test_feature_R = lsn.branch_R.eval(feed_dict={lsn.input_R:X_MR_test[:,1,:]})

  test_preds = lsn.preds.eval(feed_dict={lsn.input_L:X_MR_test[:,0,:],lsn.input_R:X_MR_test[:,1,:],
                                      lsn.aux_gen:X_aux_test[:,0:1],lsn.aux_clinical:X_aux_test[:,1:]})
  test_acc = lsn.accuracy.eval(feed_dict={lsn.input_L:X_MR_test[:,0,:],lsn.input_R:X_MR_test[:,1,:],
                                       lsn.aux_gen:X_aux_test[:,0:1],lsn.aux_clinical:X_aux_test[:,1:],
                                       lsn.labels:y_test})

  test_metrics = {'test_feature_L':test_feature_L,'test_feature_R':test_feature_R,'test_preds':test_preds}
  print('Accuracy test set %0.2f' % (100 * test_acc))
  return lsn, test_metrics

