#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import division
import cv2
import numpy as np
import copy
import math
from matplotlib import pyplot as plt
from scipy import signal, ndimage

# global varibales
global frame
k_list = []
b_list = []
f_k_list = []
f_b_list = []
count_nan = 0
noedge = True

def image_processor(capture):

    global frame

    width = capture.get(cv2.CAP_PROP_FRAME_WIDTH) # 1280
    height = capture.get(cv2.CAP_PROP_FRAME_HEIGHT) # 720

    # print width, height

    while capture.isOpened():

        # 1. start, draw the point of action
        ret, frame = capture.read()

        limg = copy.deepcopy(frame)
        rimg = copy.deepcopy(frame)

        frame = cv2.GaussianBlur(frame,(5,5),0)                    
        hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)

        tip_width = int(width/2)
        tip_height = int(21/64*height) #240
        tip_pos = np.array([tip_width, tip_height])
        tip_box = 20

        cv2.line(frame, (int(width/2), 0), (int(width/2), int(height)), (0, 0, 0))
        cv2.circle(frame, (tip_width,tip_height), radius=5, color=(0, 255, 0), thickness=-1)
        
        # 2. pre zone
        d = process_pre_roi(limg, tip_pos)

        # 3. post zone
        xr,yr,wr,hr = process_post_roi(rimg, tip_pos)


        cv2.imshow('frame', frame)
        # 4. create a black image for displaying information
        # info = display_info(d, xr, yr, hr, wr, tip_height)
        # images = np.hstack((frame, info))
        # cv2.imshow('Processsed', images)

        if cv2.waitKey(60) & 0xFF == ord('q'):
            break

def process_pre_roi(limg, tip_pos):

    """
    Define pre sealing roi and methods to process the image

    Args:
        limg: original frame image
        tip_pos: point of action position

    Returns:
        k: deravative
        b: y-intercept
        (line equation: y = kx + b w.r.t original frame)
    """
    
    global frame, k_list, b_list, count_nan, noedge

    # 1. define left roi
    tip_width = tip_pos[0]
    tip_height = tip_pos[1]
    left_rectangle_center = np.array([tip_width-160, tip_height])
    left_rectangle_height = 50
    left_rectangle_width = 120
    cv2.rectangle(frame,(left_rectangle_center[0]- left_rectangle_width,left_rectangle_center[1]- left_rectangle_height),(left_rectangle_center[0]+ left_rectangle_width,left_rectangle_center[1]+ left_rectangle_height),(255,255,255),1)

    # 2. process left image
    # 2a. define left ROI
    limg = cv2.GaussianBlur(limg,(3,3),0)   
    # (xl1, yl1) denotes left up corner, (xl2,yl2) denotes right bottom corner
    # for the line function, the origin is left bottom corner
    # for image, the origin is left up corner
    yl1 = left_rectangle_center[1]- left_rectangle_height
    yl2 = left_rectangle_center[1]+ left_rectangle_height
    xl1 = left_rectangle_center[0]- left_rectangle_width
    xl2 = left_rectangle_center[0]+ left_rectangle_width
    left_rectangle_img = limg[yl1:yl2, xl1:xl2]

    # 2b. get the line function of the detected edge in left ROI 
    d = np.nan
    lk, lb = process_pre_roi_getkb(left_rectangle_img, tip_pos)

    # for five consective frame
    # if all non then stop using the previous value
    if noedge == True and math.isnan(lk)==False:
        # first detetion
        noedge = False
        count_nan = 0
    
    elif noedge == False:
        if not math.isnan(lk):
            count_nan = 0
        else:
            count_nan += 1
            lk = k_list[-1]
            lb = b_list[-1]
            if count_nan % 20 == 0:
                noedge = True

    if noedge == False:

        k_list.append(lk)
        b_list.append(lb)

        # 2c. filter the line
        lk, lb = preroi_filter(lk, lb)

        # 2d. lb = lb+y_offset-lk*x_offset remap the function from ROI to original frame
        y_offset = yl1
        x_offset = xl1
        lb = lb+y_offset-lk*x_offset
        a1 = xl1
        a2 = xl2 
        b1 = int(lk*a1+lb)
        b2 = int(lk*a2+lb)
        cv2.line(frame,(a1,b1),(a2,b2),(0,0,255),2)

        # 2e. calculate the error (distance between the line to the point of action (tip))
        p1 = np.array([a1, b1])
        p2 = np.array([a2, b2])
        d = np.cross(p2-p1,tip_pos-p1)/np.linalg.norm(p2-p1)
        
    
    return d

def process_pre_roi_getkb(limg, tip_pos):

    """
    Get the function of most likely edge using Hough Transfrmation

    Args:
        limg: original frame image
        tip_pos: point of action position

    Returns:
        k: deravative
        b: y-intercept
        (line equation: y = kx + b w.r.t left ROI)
    """
    limg_width = limg.shape[1]
    limg_height = limg.shape[0]
    new_p0 = np.array([limg_width, int(limg_height/2)])

    cv2.circle(limg, (new_p0[0],new_p0[1]), radius=3, color=(0, 255, 0), thickness=-1)

    gray = cv2.cvtColor(limg,cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray,50,150,apertureSize = 3) #apertureSize size of kernal
    lines = cv2.HoughLines(edges,1,np.pi/180,threshold=50)
    

    k = np.nan
    b = np.nan
    select_one = 1

    if lines is not None:
        # filter out the line that is too far away from point of action
        slines = select_line(new_p0, lines)
        if slines is not None:
            for line in slines:
                for rho,theta in line:
                    # only select the first one (strongest one) to be the edge
                    if select_one == 1:
                        a = np.cos(theta)
                        b = np.sin(theta)
                        x0 = a*rho
                        y0 = b*rho
                        x1 = int(x0 + 1000*(-b))
                        y1 = int(y0 + 1000*(a))
                        x2 = int(x0 - 1000*(-b))
                        y2 = int(y0 - 1000*(a))
                        cv2.line(limg,(x1,y1),(x2,y2),(0,0,255),2)    
                        k, b = polar2cartesian(rho, theta, rotate90 = True) 
                        select_one = select_one +1 
    cv2.imshow('roi', limg)
    cv2.imshow('edge', edges)

    return k, b

def polar2cartesian(rho, theta_rad, rotate90 = True):
    """
    Converts line equation from polar to cartesian coordinates

    Args:
        rho: input line rho
        theta_rad: input line theta
        rotate90: output line perpendicular to the input line

    Returns:
        m: slope of the line
           For horizontal line: m = 0
           For vertical line: m = np.nan
        b: intercept when x=0
    """
    x = np.cos(theta_rad) * rho
    y = np.sin(theta_rad) * rho
    m = np.nan
    if not np.isclose(x, 0.0):
        m = y / x
    if rotate90:
        if m is np.nan:
            m = 0.0
        elif np.isclose(m, 0.0):
            m = np.nan
        else:
            m = -1.0 / m
    b = 0.0
    if m is not np.nan:
        b = y - m * x

    return m, b

def select_line(p0, lines):

    """
    Filter the lines 

    Args:
        p0: position of point of action
        lines: all the lines(edges) detected

    Returns:
        slines: lines that meet the tolerance (order: from strong to weak according to Hough Transfrmation)
    """

    slines = []
    # angle of line, 0 for vertical, pi/2 for horizonal
    angle_threshold = [np.pi/4, np.pi*3/4] 
    # the farest allowable distance from line to point of action
    distance_threshold = 30
    # the farest allowable distance from line y-intercept to point of action
    y_threshold = 40

    for line in lines:
        for rho,theta in line:
            if angle_threshold[0] <= theta <= angle_threshold[1]: 
                a = np.cos(theta)
                b = np.sin(theta)
                x0 = a*rho
                y0 = b*rho
                x1 = int(x0 + 1000*(-b))
                y1 = int(y0 + 1000*(a))
                x2 = int(x0 - 1000*(-b))
                y2 = int(y0 - 1000*(a))

                p1 = np.array([x1, y1])
                p2 = np.array([x2, y2])

                k, b = polar2cartesian(rho, theta)

                if not math.isnan(k):
                    d = np.abs(np.cross(p2-p1,p0-p1)/np.linalg.norm(p2-p1))
                    if d < distance_threshold and abs(b-p0[1]) < y_threshold:
                        slines.append(line)

    # you should not choose the line with the nearest distance, 
    # cuz if the seam move, it will output the wrong line 
    # (the one close to the tip may not be the correct one)
        
    return slines

def plotkb():
    """
    Plot k, b value
    """
    global k_list, b_list, f_k_list, f_b_list

    x = range(np.array(k_list).shape[0])
    plt.ion()
    plt.show()
    plt.cla()
    
    plt.subplot(4,1,1)
    plt.plot(x, k_list, color='r', linewidth=0.5)
    plt.title('slope: k_list')
    plt.subplot(4,1,2)
    plt.plot(x, f_k_list, color='k', linewidth=0.5)
    plt.title('filtered_k_list')
    plt.subplot(4,1,3)
    plt.plot(x, b_list,  color='r', linewidth=0.5)
    plt.title('y-intercept: b_list')
    plt.subplot(4,1,4)
    plt.plot(x, f_b_list,  color='k', linewidth=0.5)
    plt.title('filtered_b_list')
        #     >>> plot(x, y, 'go--', linewidth=2, markersize=12)
        # >>> plot(x, y, color='green', marker='o', linestyle='dashed',
        # ...      linewidth=2, markersize=12)

    plt.tight_layout()
    plt.autoscale(enable=True)

    plt.draw()
    plt.pause(0.001)

def preroi_filter(lk, lb):
    """
    Filter the data using first order low-pass filter, two parameters to adjust the result
    alpha: how much the original data should be "corrected", 0 for no correction
    n: how close should this new measures be to the previous one, for averaging the value

    Args:
        lk: slope
        lb: y-intercept

    Returns:
        new_k: new slope
        new_b: new y-intercept
    """
    global k_list, b_list, f_k_list, f_b_list

    # low pass filter
    new_k = lk
    new_b = lb
    # how close is this new measures to the previous one
    n = 10
    # how much the original data should be "corrected"q
    alpha = 0.2

    # k_weights=[1,1,1,1,1,2,2,2,2,2]
    k_weights = np.ones(n)
    
    if np.array(k_list).shape[0]>n:
        new_k = np.average(np.array(k_list)[-n-1:-1], weights=k_weights)
        new_b = np.average(np.array(b_list)[-n-1:-1], weights=k_weights)
    
    f_k_list.append(new_k)
    f_b_list.append(new_b)
    k_list[-1] = alpha*new_k + (1-alpha)*k_list[-1]
    b_list[-1] = alpha*new_b + (1-alpha)*b_list[-1]

    # plotkb()

    return new_k, new_b 

def process_post_roi(rimg, tip_pos):
    """
    Define post sealing roi and methods to process the image

    Args:
        rimg: original frame image
        tip_pos: point of action position

    Returns:
        x: x coordiante for left top corner point
        y: y coordiante for left top corner point
        w: width of rectangle
        h: height of rectangle
        all value is w.r.t frame
    """
    global frame

    # 1. define right(post) roi
    tip_width = tip_pos[0]
    tip_height = tip_pos[1]
    right_rectangle_center = np.array([tip_width+100, tip_height])
    right_rectangle_height = 45
    right_rectangle_width = 75
    cv2.rectangle(frame,(right_rectangle_center[0]- right_rectangle_width,right_rectangle_center[1]- right_rectangle_height),(right_rectangle_center[0]+ right_rectangle_width,right_rectangle_center[1]+ right_rectangle_height),(255,255,255),1)

    # 2. process right image
    # 2a. define right ROI
    yr1 = right_rectangle_center[1]- right_rectangle_height
    yr2 = right_rectangle_center[1]+ right_rectangle_height
    xr1 = right_rectangle_center[0]- right_rectangle_width
    xr2 = right_rectangle_center[0]+ right_rectangle_width
    right_rectangle_img = rimg[yr1:yr2, xr1:xr2]

    # 2b. get the shape (presumably rectangle) using process_right_rectangle
    xr,yr,wr,hr = process_post_roi_getshape(right_rectangle_img)

    # 2c. remap the result from ROI to original frame
    if not (xr==0 and yr==0 and wr==0 and hr==0):
        xr = xr + right_rectangle_center[0]- right_rectangle_width
        yr = yr + right_rectangle_center[1]- right_rectangle_height
        xr = int(xr)
        yr = int(yr)
        cv2.rectangle(frame, (xr, yr), (xr + wr, yr + hr), (255, 255, 0), 2)  # blue
    
    return xr,yr,wr,hr

def process_post_roi_getshape(rimg):
    """
    Get the parameter of silicone(shape: rectangle) using color detection

    Args:
        rimg: original frame image

    Returns:
        x: x coordiante for left top corner point
        y: y coordiante for left top corner point
        w: width of rectangle
        h: height of rectangle
        all value is w.r.t right ROI
    """
    hsv=cv2.cvtColor(rimg,cv2.COLOR_BGR2HSV)  
    l_b = np.array([70, 0, 0])
    u_b = np.array([100, 80, 255])
    
    mask=cv2.inRange(hsv, l_b, u_b)        
    mask=cv2.erode(mask,None,iterations=2)
    mask=cv2.dilate(mask,None,iterations=2)
    mask=cv2.GaussianBlur(mask,(3,3),0)
    res=cv2.bitwise_and(rimg,rimg,mask=mask)            
    cnts=cv2.findContours(mask.copy(),cv2.RETR_EXTERNAL,
                          cv2.CHAIN_APPROX_SIMPLE)[-2] 

    x,y,w,h = 0,0,0,0

    if len(cnts)>0:
        cnt = max (cnts,key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(cnt)
        cv2.rectangle(rimg, (x, y), (x + w, y + h), (255,255,0), 2)

    # cv2.imshow('rcapture',rimg)
    # cv2.imshow('rres', res)
    return x,y,w,h

def display_info(d, xr, yr, hr, wr, tip_height):
    """
    Dispaly useful information
    """
    note = np.zeros((480,400,3), np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    i_in = 20
    b_in = 50
    s_in = 30
    cv2.putText(note,'Feedback',(10,i_in), font, 0.5,(255,255,255),1)

    cv2.putText(note,'Green: point of action (target)',(10,i_in+b_in), font, 0.5,(0,255,0),1)

    cv2.putText(note,'Left box',(10,i_in+2*b_in), font, 0.5,(255,255,255),1)
    cv2.putText(note,'Red line: edge (detected)',(10,i_in+2*b_in+s_in), font, 0.5,(0,0,255),1)
    
    if not math.isnan(d):
        cv2.putText(note,'Distance to target: '+ str(round(d,2)) +' pixel (error)',(10,i_in+2*b_in+2*s_in), font, 0.5,(0,0,255),1)
    
    cv2.putText(note,'Right box',(10,i_in+3*b_in+2*s_in), font, 0.5,(255,255,255),1)
    cv2.putText(note,'Blue box: Sealed region',(10,i_in+3*b_in+3*s_in), font, 0.5,(255,255,0),1)
    if hr != 0:
        cv2.putText(note,'Height of silicone: ' + str(round(hr,2)) +' pixel',(10,i_in+3*b_in+4*s_in),font, 0.5,(255,255,0),1)
        cv2.putText(note,'Distance to target (height): ' + str(round(yr+hr/2-tip_height,2)) +' pixel (error)',(10,i_in+3*b_in+5*s_in),font, 0.5,(255,255,0),1)

    return note

if __name__ == '__main__':

    try:
        # capture = cv2.VideoCapture(-1)
        # capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        # capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        capture = cv2.VideoCapture('/home/maggie/ros/feedback/1.avi')
        # capture = cv2.VideoCapture('/home/maggie/ros/feedback/sealing.avi')
        image_processor(capture)

    finally:
        capture.release()
        cv2.destroyAllWindows()