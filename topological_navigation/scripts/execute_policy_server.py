#!/usr/bin/env python

import rospy
import actionlib
import pymongo
import json
import sys

import calendar
from time import sleep
from datetime import datetime


from actionlib_msgs.msg import *
from move_base_msgs.msg import *
from std_msgs.msg import String

from strands_navigation_msgs.msg import MonitoredNavigationAction
from strands_navigation_msgs.msg import MonitoredNavigationGoal
from strands_navigation_msgs.msg import MonitoredNavigationGoal

from strands_navigation_msgs.msg import NavStatistics


#from strands_navigation_msgs.msg import TopologicalNode
from strands_navigation_msgs.msg import TopologicalMap
from mongodb_store.message_store import MessageStoreProxy
#from topological_navigation.topological_node import *
from topological_navigation.navigation_stats import *

import topological_navigation.msg
import strands_navigation_msgs.msg
#import dynamic_reconfigure.client


"""
 Class for Policy Execution

"""

class PolicyExecutionServer(object):
    _feedback = strands_navigation_msgs.msg.ExecutePolicyModeFeedback()
    _result   = strands_navigation_msgs.msg.ExecutePolicyModeResult()

    """
     Initialization for Policy Execution Class
    
    """
    def __init__(self) :
        self.cancelled = False
        self.preempted = False
        #self.aborted = False
        self.current_node = 'unknown'
        self.closest_node = 'unknown'
        self.current_action = 'none'
        self.n_tries = 3        
        
        rospy.on_shutdown(self._on_node_shutdown)
#        self._target = "None"
        self.move_base_actions = ['move_base','human_aware_navigation']
        self.navigation_activated=False
        self._action_name = '/topological_navigation/execute_policy_mode'
#        self.stats_pub = rospy.Publisher('/topological_navigation/Statistics', NavStatistics)


        self.lnodes = []
        rospy.Subscriber('/topological_map', TopologicalMap, self.MapCallback)       
        rospy.loginfo("Waiting for Topological map ...")        

        #Creating Action Server
        rospy.loginfo("Creating action server.")
        self._as = actionlib.SimpleActionServer(self._action_name, topological_navigation.msg.ExecutePolicyModeAction, execute_cb = self.executeCallback, auto_start = False)
        self._as.register_preempt_callback(self.preemptCallback)
        rospy.loginfo(" ...starting")
        self._as.start()
        rospy.loginfo(" ...done")


        #Creating monitored navigation client
        rospy.loginfo("Creating monitored navigation client.")
        self.monNavClient= actionlib.SimpleActionClient('monitored_navigation', MonitoredNavigationAction)
        self.monNavClient.wait_for_server()
        rospy.loginfo(" ...done")


        #Subscribing to Localisation Topics
        rospy.loginfo("Subscribing to Localisation Topics")
        rospy.Subscriber('/closest_node', String, self.closestNodeCallback)
        rospy.Subscriber('/current_node', String, self.currentNodeCallback)
        rospy.loginfo(" ...done")

        
        #Creating Reconfigure Client
#        rospy.loginfo("Creating Reconfigure Client")
#        self.rcnfclient = dynamic_reconfigure.client.Client('/move_base/DWAPlannerROS')
#        config = self.rcnfclient.get_configuration()
#        self.dyt = config['yaw_goal_tolerance']


        rospy.loginfo("All Done ...")
        rospy.spin()


    """
     Preempt CallBack
     
    """
    def preemptCallback(self):
        self.cancelled = True
        self.preempted = True
        self._result.success = False
        self.navigation_activated = False
        self.monNavClient.cancel_all_goals()
        #self._as.set_preempted(self._result)
    

    """
     Closest Node CallBack
     
    """
    def closestNodeCallback(self, msg):
        self.closest_node=msg.data



    """
     Current Node CallBack
     
    """
    def currentNodeCallback(self, msg):
        if self.current_node != msg.data :
            self.current_node = msg.data
            if msg.data != 'none' :
                print "new node reached %s" %self.current_node
                
                if self.navigation_activated :
                    if self.current_action in self.move_base_actions and self.current_node in self.current_route.source :
                        nod_ind = self.current_route.source.index(self.current_node)
                        next_action = self.find_action(self.current_route.source[nod_ind], self.current_route.target[nod_ind])
                        if next_action in self.move_base_actions :
                            self.goal_reached=True
                    #print "goal reached %s" %self.current_node


    """
     Execute CallBack
     
     This Functions is called when the Action Server is called
    """
    def executeCallback(self, goal):
        self.cancelled = False
        self.preempted = False
        
        #print self.current_node
        result = self.followRoute(goal.route)
    
        if not self.cancelled :       
            self._result.success = result
            self._feedback.route_status = self.current_node
            self._as.publish_feedback(self._feedback)
            if result:
                self._as.set_succeeded(self._result)
            else :
                self._as.set_aborted(self._result)
        else:
            if self.preempted :
                self._result.success = False
                self._as.set_preempted(self._result)
            else : 
                self._result.success = False
                self._as.set_aborted(self._result)
        #self._feedback.route_status = 'Starting...'
        #self._as.publish_feedback(self._feedback)
        #rospy.loginfo('%s: Navigating From %s to %s', self._action_name, self.closest_node, goal.target)
        #self.navigate(goal.target)


    
    """
     Follow Route
     
    """
    def followRoute(self, route):
        

        for i in range(0, len(route.source)):
            action = self.find_action(route.source[i], route.target[i])
            print '%s -(%s)-> %s' %(route.source[i], action, route.target[i])

        #If the robot is not on a node navigate to closest node
        if self.current_node == 'none' :
            print 'Do move_base to %s' %self.closest_node#(route.source[0])
            result=self.navigate_to('move_base',self.closest_node)
        
        result=self.execute_policy(route)
        
        
        #result=True
        return result


    """
     Execute Policy
     
    """
    def execute_policy(self, route):
        keep_executing=True
        success = True
        self.current_route = route
        self.navigation_activated=True
        nfails=0
        while keep_executing :
            if self.current_node in route.source and not self.cancelled :
                if success :
                    nfails=0
                    nod_ind = route.source.index(self.current_node)
                    self.current_action = self.find_action(route.source[nod_ind], route.target[nod_ind])
                    if self.current_action != 'none':
                        print '%s -(%s)-> %s' %(route.source[nod_ind], self.current_action, route.target[nod_ind])
                        success=self.navigate_to(self.current_action,route.target[nod_ind])
                    else:
                        success = False
                        keep_executing = False
                    
                else :
                    nfails+=1
                    if nfails < self.n_tries :
                        nod_ind = route.source.index(self.current_node)
                        action = self.find_action(route.source[nod_ind], route.target[nod_ind])
                        if action != 'none':
                            if action in self.move_base_actions :
                                self.current_action = action
                                print '%s -(%s)-> %s' %(route.source[nod_ind], self.current_action, route.target[nod_ind])
                                success=self.navigate_to(self.current_action,route.target[nod_ind])
                            else:                           
                                print 'Do move_base to %s' %self.current_node#(route.source[0])
                                self.current_action = 'move_base'
                                success=self.navigate_to(self.current_action,self.current_node)
                        else:
                            success = False
                            keep_executing = False
                    else:
                        success = False
                        keep_executing = False
            else :
                if self.cancelled:
                    success = False
                    keep_executing = False
                    break
                else :
                    print "%s not in:" %self.current_node 
                    print route.source
                    if self.current_node == 'none' :
                        nfails+=1
                        if nfails < self.n_tries :
                            if self.closest_node in route.source :
                                nod_ind = route.source.index(self.closest_node)
                                action = self.find_action(route.source[nod_ind], route.target[nod_ind])
                                if action != 'none':
                                    if action in self.move_base_actions :
                                        self.current_action = action
                                        print '%s -(%s)-> %s' %(route.source[nod_ind], self.current_action, route.target[nod_ind])
                                        success=self.navigate_to(self.current_action,route.target[nod_ind])
                                    else:                           
                                        print 'Do move_base to %s' %self.closest_node#(route.source[0])
                                        self.current_action = 'move_base'
                                        success=self.navigate_to(self.current_action,self.closest_node)
                                else:
                                    success = False
                                    keep_executing = False
                            else :
                                print 'Do move_base to %s' %self.closest_node
                                self.current_action = 'move_base'
                                success=self.navigate_to(self.current_action,self.closest_node)
                        else:
                            success = False
                            keep_executing = False
                    else :
                        nfails=0
                        success = True
                        keep_executing = False
            rospy.sleep(rospy.Duration.from_sec(0.3))
            self._feedback.route_status = self.current_node
            self._as.publish_feedback(self._feedback)
        self.navigation_activated = False
        return success


    """
     Find Action
         
    """
    def find_action(self, source, target):
        #print 'Searching for action between: %s -> %s' %(source, target)
        found = False
        action = 'none'
        for i in self.lnodes:
            if i.name == source :
                for j in i.edges:
                    if j.node == target:
                        action = j.action
                found = True
        if not found:
            self._feedback.route_status = self.current_node
            self._as.publish_feedback(self._feedback)
            print "source node not found"
        return action



    """
     Map CallBack
     
    """
    def MapCallback(self, msg) :
        self.lnodes = msg.nodes
#        for i in self.lnodes : 
#            print i


    def navigate_to(self, action, node):
        found = False
        for i in self.lnodes:
            if i.name == node :
                found = True
                target_pose = i.pose
                break
        if found:
            self.current_action = action
            result = self.monitored_navigation(target_pose, action)
        else :
            result = False
        return result
        
    
    def monitored_navigation(self, pose, command):
        result = True
        goal=MonitoredNavigationGoal()
        goal.action_server=command
        goal.target_pose.header.frame_id = "map"
        goal.target_pose.header.stamp = rospy.get_rostime()
        goal.target_pose.pose = pose

        self.goal_reached=False
        self.monNavClient.send_goal(goal)
        status=self.monNavClient.get_state()
        
        while (status == GoalStatus.ACTIVE or status == GoalStatus.PENDING) and not self.cancelled and not self.goal_reached :
            status=self.monNavClient.get_state()
            rospy.sleep(rospy.Duration.from_sec(0.1))


        #rospy.loginfo(str(status))
        #print status
        if status != GoalStatus.SUCCEEDED :
            if not self.goal_reached:
                result = False
#                if status is GoalStatus.PREEMPTED:
#                    self.preempted = True
#                    result = False
#                else:
#                    result = True
            else:
                result = True
        else :
            result = True
#            ps = self.monNavClient.get_result()
#            if ps.outcome != 'succeded' :
#                result = False
#            else :
#                result = True
        #rospy.sleep(rospy.Duration.from_sec(0.3))
        return result


    def _on_node_shutdown(self):
        self.cancelled = True



if __name__ == '__main__':
    mode="normal"
#    if len(sys.argv) > 2:
#        print str(sys.argv[2])
#        if str(sys.argv[2]) == "true":
#            mode="Node_by_Node"
#            print "Node_by_Node"
    rospy.init_node('execute_policy_mode')
    server = PolicyExecutionServer()