#!/usr/bin/env python

# Import modules
import numpy as np
import sklearn
from sklearn.preprocessing import LabelEncoder
import pickle
from sensor_stick.srv import GetNormals
from sensor_stick.features import compute_color_histograms
from sensor_stick.features import compute_normal_histograms
from visualization_msgs.msg import Marker
from sensor_stick.marker_tools import *
from sensor_stick.msg import DetectedObjectsArray
from sensor_stick.msg import DetectedObject
from sensor_stick.pcl_helper import *
from sensor_stick.training_helper import spawn_model
import rospy
import tf
from geometry_msgs.msg import Pose
from std_msgs.msg import Float64
from std_msgs.msg import Int32
from std_msgs.msg import String
from pr2_robot.srv import *
from rospy_message_converter import message_converter
import yaml


# Helper function to get surface normals
def get_normals(cloud):
    get_normals_prox = rospy.ServiceProxy('/feature_extractor/get_normals', GetNormals)
    return get_normals_prox(cloud).cluster

# Helper function to create a yaml friendly dictionary from ROS messages
def make_yaml_dict(test_scene_num, arm_name, object_name, pick_pose, place_pose):
    yaml_dict = {}
    yaml_dict["test_scene_num"] = test_scene_num.data
    yaml_dict["arm_name"]  = arm_name.data
    yaml_dict["object_name"] = object_name.data
    yaml_dict["pick_pose"] = message_converter.convert_ros_message_to_dictionary(pick_pose)
    yaml_dict["place_pose"] = message_converter.convert_ros_message_to_dictionary(place_pose)
    return yaml_dict

# Helper function to output to yaml file
def send_to_yaml(yaml_filename, dict_list):
    data_dict = {"object_list": dict_list}
    with open(yaml_filename, 'w') as outfile:
        yaml.dump(data_dict, outfile, default_flow_style=False)

# Callback function for your Point Cloud Subscriber
def pcl_callback(pcl_msg):

# Exercise-2 TODOs:

    # TODO: Convert ROS msg to PCL data
    cloud_filtered = ros_to_pcl(pcl_msg)

    # TODO: Statistical Outlier Filtering

    # Much like the previous filters, we start by creating a filter object: 
    outlier_filter = cloud_filtered.make_statistical_outlier_filter()

    # Set the number of neighboring points to analyze for any given point
    outlier_filter.set_mean_k(50)

    # Set threshold scale factor
    x = 0.01

    # Any point with a mean distance larger than global (mean distance+x*std_dev) will be considered outlier
    outlier_filter.set_std_dev_mul_thresh(x)

    # Finally call the filter function for magic
    cloud_filtered = outlier_filter.filter()

    # TODO: Voxel Grid Downsampling

    # Create a VoxelGrid filter object for our input point cloud
    vox = cloud_filtered.make_voxel_grid_filter()

    # Choose a voxel (also known as leaf) size
    LEAF_SIZE = 0.01   

    # Set the voxel (or leaf) size  
    vox.set_leaf_size(LEAF_SIZE, LEAF_SIZE, LEAF_SIZE)

    # Call the filter function to obtain the resultant downsampled point cloud
    cloud_filtered = vox.filter()

    # TODO: PassThrough Filter

    # Create a PassThrough filter object.
    passthrough = cloud_filtered.make_passthrough_filter()

    # Assign axis and range to the passthrough filter object.
    
    filter_axis = 'z'
    passthrough.set_filter_field_name(filter_axis)
    axis_min = 0.6
    axis_max = 1.1
    passthrough.set_filter_limits(axis_min, axis_max)

    cloud_filtered = passthrough.filter()
    passthrough = cloud_filtered.make_passthrough_filter()

    filter_axis = 'x'
    passthrough.set_filter_field_name(filter_axis)
    axis_min = 0.4
    axis_max = 3.0
    passthrough.set_filter_limits(axis_min, axis_max)

    # Finally use the filter function to obtain the resultant point cloud. 
    cloud_filtered = passthrough.filter()

    # TODO: RANSAC Plane Segmentation

    # Create the segmentation object
    seg = cloud_filtered.make_segmenter()

    # Set the model you wish to fit
    seg.set_model_type(pcl.SACMODEL_PLANE)
    seg.set_method_type(pcl.SAC_RANSAC)

    # Max distance for a point to be considered fitting the model
    max_distance =  0.05
    seg.set_distance_threshold(max_distance)

    # Call the segment funcion to obtain set of inlier indices
    # and model coefficients
    inliers, coefficients = seg.segment()

    # TODO: Extract inliers and outliers

    # Extract inliers
    cloud_table = cloud_filtered.extract(inliers, negative=False)

    # Extract outliers
    cloud_objects = cloud_filtered.extract(inliers, negative=True)

    # TODO: Euclidean Clustering

    white_cloud = XYZRGB_to_XYZ(cloud_objects) # Apply function to convert XYZRGB to XYZ
    tree = white_cloud.make_kdtree()
	
    # Create a cluster extraction object
    ec = white_cloud.make_EuclideanClusterExtraction()
    # Set tolerances for distance threshold 
    # as well as minimum and maximum cluster size (in points)
    # NOTE: These are poor choices of clustering parameters
    # Your task is to experiment and find values that work for segmenting objects.
    ec.set_ClusterTolerance(0.03)
    ec.set_MinClusterSize(10)
    ec.set_MaxClusterSize(50000)
    # Search the k-d tree for clusters
    ec.set_SearchMethod(tree)
    # Extract indices for each of the discovered clusters
    cluster_indices = ec.Extract() #cluster_indices ahora contiene una lista de los objetos
    print("Numero de cluster #", len(cluster_indices))
    # print("aqui esta el cluster #",cluster_indices)

    # TODO: Create Cluster-Mask Point Cloud to visualize each cluster separately

    #Assign a color corresponding to each segmented object in scene
    cluster_color = get_color_list(len(cluster_indices))
	
    color_cluster_point_list = []
	
    for j, indices in enumerate(cluster_indices):
	for i, indice in enumerate(indices):
	    color_cluster_point_list.append([white_cloud[indice][0],white_cloud[indice][1],white_cloud[indice][2],rgb_to_float(cluster_color[j])])

    #Create new cloud containing all clusters, each with unique color
    cluster_cloud = pcl.PointCloud_PointXYZRGB()
    cluster_cloud.from_list(color_cluster_point_list)

    # TODO: Convert PCL data to ROS messages

    ros_cloud_objects =  pcl_to_ros(cloud_objects)
    ros_cloud_table = pcl_to_ros(cloud_table)
    ros_cloud_cluster = pcl_to_ros(cluster_cloud)

    # TODO: Publish ROS messages

    pcl_objects_pub.publish(ros_cloud_objects)
    pcl_table_pub.publish(ros_cloud_table)
    pcl_mask_pub.publish(ros_cloud_cluster)

# Exercise-3 TODOs:

    # <arg name="world_name" value="$(find pr2_robot)/worlds/test1.world"/>
    '''
    models = [\
       'biscuits',
       'soap',
       'soap2']
    
    # <arg name="world_name" value="$(find pr2_robot)/worlds/test2.world"/>
    
    models = [\
       'biscuits',
       'soap',
       'book',
       'soap2',
       'glue',]
    
    '''
    # <arg name="world_name" value="$(find pr2_robot)/worlds/test3.world"/>
    models = [\
       'sticky_notes',
       'book',
       'snacks',
       'biscuits',
       'eraser',
       'soap2',
       'soap',
       'glue']
    
    # Disable gravity and delete the ground plane
    # initial_setup()
    labeled_features = []

    for model_name in models:
        spawn_model(model_name)
    
    # Classify the clusters! (loop through each detected cluster one at a time)
    detected_objects_labels = []
    detected_objects = []

    for index, pts_list in enumerate(cluster_indices):
        # Grab the points for the cluster from the extracted outliers (cloud_objects)
        pcl_cluster = cloud_objects.extract(pts_list)
        
        # TODO: convert the cluster from pcl to ROS using helper function
        sample_cloud =  pcl_to_ros(pcl_cluster)
        
        # Extract histogram features
        # TODO: complete this step just as is covered in capture_features.py
        
        chists = compute_color_histograms(sample_cloud, using_hsv=True)
        normals = get_normals(sample_cloud)
        nhists = compute_normal_histograms(normals)
        feature = np.concatenate((chists, nhists))
        labeled_features.append([feature, model_name])
        
        # Make the prediction, retrieve the label for the result
        # and add it to detected_objects_labels list
        prediction = clf.predict(scaler.transform(feature.reshape(1,-1)))
        label = encoder.inverse_transform(prediction)[0]
        detected_objects_labels.append(label)

        # Publish a label into RViz
        label_pos = list(white_cloud[pts_list[0]])
        label_pos[2] += .4
        object_markers_pub.publish(make_label(label,label_pos, index))

        # Add the detected object to the list of detected objects.
        do = DetectedObject()
        do.label = label
        do.cloud = sample_cloud
        detected_objects.append(do)

        #print(detected_objects)

    rospy.loginfo('Detected {} objects: {}'.format(len(detected_objects_labels), detected_objects_labels))

    # Publish the list of detected objects
    # This is the output you'll need to complete the upcoming project!
    detected_objects_pub.publish(detected_objects)

    # Suggested location for where to invoke your pr2_mover() function within pcl_callback()
    # Could add some logic to determine whether or not your object detections are robust
    # before calling pr2_mover()
    detected_objects_list = detected_objects
    try:
        pr2_mover(detected_objects_list)
    except rospy.ROSInterruptException:
        pass
    # pass
#'''
# function to load parameters and request PickPlace service
def pr2_mover(object_list):

    # TODO: Initialize variables
    test_scene_num = Int32()
    object_name = String()
    arm_name = String()
    pick_pose = Pose()
    place_pose = Pose()

    test_scene_num.data = 3 # Change the number as the case may be: 1,  2, 3.

    # TODO: Get/Read parameters
    
    # get/read parameters
    object_list_param = rospy.get_param('/object_list')
    dropbox_list_param = rospy.get_param('/dropbox')

    # TODO: Parse parameters into individual variables
    obj_label = []
    arm_label = []
    box_pose = []
    for i in range(0,len(object_list_param)):
        objlabel = object_list_param[i]['name'] # object_name
	obj_label.append(objlabel)
	print(" xxx obj_label: ",obj_label)
        armlabel = object_list_param[i]['group'] # object_group
	arm_label.append(armlabel)
	print(" yyy arm_label: ",arm_label)

    for j in range(0,len(dropbox_list_param)):
        boxpose = dropbox_list_param[j]['position'] # plase_pose
	box_pose.append(boxpose)	
	print(" zzz box_pose: ",box_pose)

    # TODO: Rotate PR2 in place to capture side tables for the collision map

    # TODO: Loop through the pick list
    
    dict_list = []
    labels = []
    centroids = [] # to be list of tuples (x, y, z)
    objects = object_list

    for object in objects:
        
        # TODO: Get the PointCloud for a given object and obtain it's centroid

        #labels.append(object.label)
	labels = object.label	
	print("labels obj kkkkk:",labels)
        points_arr = ros_to_pcl(object.cloud).to_array()	
	centroids = np.mean(points_arr, axis=0)        
        pick_pose.position.x = np.asscalar(centroids[0])
        pick_pose.position.y = np.asscalar(centroids[1])
        pick_pose.position.z = np.asscalar(centroids[2])
	print("pick_pose= ",pick_pose)
        # pick_pose.data = = Point(float(centroids[0]),float(centroids[1]),float(centroids[2]))

        # TODO: Create 'place_pose' for the object

        # TODO: Assign the arm to be used for pick_place

        for k in range(0,len(obj_label)): # Analizo la lista de objetos
	    print("labels: ",labels)
	    print("obj_label: ",obj_label[k])
	    
            compare = labels == obj_label[k]
	    print("compare: ",compare)
            if compare == True:           # Compara la lista de objetos con uno de los objetos detectado
                object_name.data = obj_label[k]
                print(arm_label[k])
                if arm_label[k] == 'green':                 # If arm_label[k] = green
                    print("arm label = green")
		    arm_name.data = 'right'    
                    #place_pose.data = box_pose[0];
		    place_pose.position.x = box_pose[1][0]
        	    place_pose.position.y = box_pose[1][1]
        	    place_pose.position.z = box_pose[1][2]
                if arm_label[k] == 'red':                   # If arm_label[k] = red
                    print("arm label = red")
		    arm_name.data = 'left'
                    #place_pose.data = box_pose[1];
		    place_pose.position.x = box_pose[0][0]
        	    place_pose.position.y = box_pose[0][1]
        	    place_pose.position.z = box_pose[0][2]
	
	print("place_pose= ",place_pose)    

        # TODO: Create a list of dictionaries (made with make_yaml_dict()) for later output to yaml format

        # Populate various ROS messages
        yaml_dict = make_yaml_dict(test_scene_num, arm_name, object_name, pick_pose, place_pose)
        dict_list.append(yaml_dict)
	print("dict_list= ",dict_list)
	'''
        # Wait for 'pick_place_routine' service to come up
        rospy.wait_for_service('pick_place_routine')
	
        try:
            pick_place_routine = rospy.ServiceProxy('pick_place_routine', PickPlace)

            # TODO: Insert your message variables to be sent as a service request
            #resp = pick_place_routine(TEST_SCENE_NUM, OBJECT_NAME, WHICH_ARM, PICK_POSE, PLACE_POSE)
	    resp = pick_place_routine(test_scene_num, object_name, arm_name, pick_pose, place_pose)

            print ("Response: ",resp.success)

        except rospy.ServiceException, e:
            print "Service call failed: %s"%e
	'''
    # TODO: Output your request parameters into output yaml file
    yaml_filename = ('output'+'3'+'.yaml')
    
    try:
        send_to_yaml(yaml_filename, dict_list)
    except rospy.ROSInterruptException:
        pass
    

if __name__ == '__main__':
    
    # TODO: ROS node initialization
    rospy.init_node('clustering', anonymous=True)

    # TODO: Create Subscribers
    pcl_sub = rospy.Subscriber("/pr2/world/points", pc2.PointCloud2, pcl_callback, queue_size=1)

    # TODO: Create Publishers

    object_markers_pub = rospy.Publisher("/object_markers", Marker, queue_size=1)
    detected_objects_pub = rospy.Publisher("/detected_objects", DetectedObjectsArray, queue_size=1)
    
    pcl_objects_pub = rospy.Publisher("/pcl_objects", PointCloud2, queue_size=1)
    pcl_table_pub = rospy.Publisher("/pcl_table", PointCloud2, queue_size=1)
    pcl_mask_pub = rospy.Publisher("/pcl_mask", PointCloud2, queue_size=1)

    # TODO: Load Model From disk

    model = pickle.load(open('model.sav', 'rb'))
    clf = model['classifier']
    encoder = LabelEncoder()
    encoder.classes_ = model['classes']
    scaler = model['scaler']

    # Initialize color_list
    get_color_list.color_list = []

    # TODO: Spin while node is not shutdown
    while not rospy.is_shutdown():
 	rospy.spin()
