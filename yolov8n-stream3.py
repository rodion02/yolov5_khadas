import numpy as np
import os
import urllib.request
from matplotlib import gridspec
from matplotlib import pyplot as plt
from PIL import Image
import argparse
import sys
import math
from ksnn.api import KSNN
from ksnn.types import *
import cv2 as cv
import time
from pathlib import Path
import json

IMG_FORMATS = 'bmp', 'dng', 'jpeg', 'jpg', 'mpo', 'png', 'tif', 'tiff', 'webp', 'pfm'  # include image suffixes
VID_FORMATS = 'asf', 'avi', 'gif', 'm4v', 'mkv', 'mov', 'mp4', 'mpeg', 'mpg', 'ts', 'wmv'  # include video suffixes
GRID0 = 20
GRID1 = 40
GRID2 = 80
# LISTSIZE = 144
# SPAN = 1
# NUM_CLS = 80
# MAX_BOXES = 500
# OBJ_THRESH = 0.4
# NMS_THRESH = 0.5

constant_martix = np.array([[0,  1,  2,  3,
			     4,  5,  6,  7,
			     8,  9,  10, 11,
			     12, 13, 14, 15]]).T

# CLASSES = ("person", "bicycle", "car","motorbike ","aeroplane ","bus","train","truck ","boat","traffic light",
#            "fire hydrant","stop sign","parking meter","bench","bird","cat","dog ","horse ","sheep","cow","elephant",
#            "bear","zebra ","giraffe","backpack","umbrella","handbag","tie","suitcase","frisbee","skis","snowboard","sports ball","kite",
#            "baseball bat","baseball glove","skateboard","surfboard","tennis racket","bottle","wine glass","cup","fork","knife ",
#            "spoon","bowl","banana","apple","sandwich","orange","broccoli","carrot","hot dog","pizza ","donut","cake","chair","sofa",
#            "pottedplant","bed","diningtable","toilet ","tvmonitor","laptop","mouse","remote","keyboard","cell phone","microwave ",
#            "oven","toaster","sink","refrigerator ","book","clock","vase","scissors","teddy bear","hair drier", "toothbrush")

def sigmoid(x):
    return 1 / (1 + np.exp(-x))

def softmax(x, axis=0):
	x = np.exp(x)
	return x / x.sum(axis=axis, keepdims=True)

def process(input):

    grid_h, grid_w = map(int, input.shape[0:2])
    
    box_class_probs = sigmoid(input[..., :NUM_CLS])

    box_0 = softmax(input[...,  NUM_CLS: NUM_CLS+16],   -1)
    box_1 = softmax(input[...,  NUM_CLS+16:NUM_CLS+32], -1)
    box_2 = softmax(input[...,  NUM_CLS+32:NUM_CLS+48], -1)
    box_3 = softmax(input[...,  NUM_CLS+48:NUM_CLS+64], -1)
    result = np.zeros((grid_h, grid_w, 1, 4))
    for i in range(grid_h):
    	for j in range(grid_w):
            result[i, j, :, 0] = np.dot(box_0[i, j], constant_martix)
            result[i, j, :, 1] = np.dot(box_1[i, j], constant_martix)
            result[i, j, :, 2] = np.dot(box_2[i, j], constant_martix)
            result[i, j, :, 3] = np.dot(box_3[i, j], constant_martix)

    col = np.tile(np.arange(0, grid_w), grid_w).reshape(-1, grid_w)
    row = np.tile(np.arange(0, grid_h).reshape(-1, 1), grid_h)

    col = col.reshape(grid_h, grid_w, 1, 1)
    row = row.reshape(grid_h, grid_w, 1, 1)
    grid = np.concatenate((col, row), axis=-1)

    result[..., 0:2] = 0.5 - result[..., 0:2]
    result[..., 0:2] += grid
    result[..., 0:2] /= (grid_w, grid_h)
    result[..., 2:4] = 0.5 + result[..., 2:4]
    result[..., 2:4] += grid
    result[..., 2:4] /= (grid_w, grid_h)

    return result, box_class_probs

def filter_boxes(boxes, box_class_probs):
    
    box_classes = np.argmax(box_class_probs, axis=-1)
    box_class_scores = np.max(box_class_probs, axis=-1)
    pos = np.where(box_class_scores >= OBJ_THRESH)

    boxes = boxes[pos]
    classes = box_classes[pos]
    scores = box_class_scores[pos]

    return boxes, classes, scores

def nms_boxes(boxes, scores):
    
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]

    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]

    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w1 = np.maximum(0.0, xx2 - xx1 + 0.00001)
        h1 = np.maximum(0.0, yy2 - yy1 + 0.00001)
        inter = w1 * h1

        ovr = inter / (areas[i] + areas[order[1:]] - inter)
        inds = np.where(ovr <= NMS_THRESH)[0]
        order = order[inds + 1]
    keep = np.array(keep)
    return keep


def yolov3_post_process(input_data):
    boxes, classes, scores = [], [], []
    for i in range(3):
        result, confidence = process(input_data[i])
        b, c, s = filter_boxes(result, confidence)
        boxes.append(b)
        classes.append(c)
        scores.append(s)

    boxes = np.concatenate(boxes)
    classes = np.concatenate(classes)
    scores = np.concatenate(scores)

    nboxes, nclasses, nscores = [], [], []
    for c in set(classes):
        inds = np.where(classes == c)
        b = boxes[inds]
        c = classes[inds]
        s = scores[inds]

        keep = nms_boxes(b, s)

        nboxes.append(b[keep])
        nclasses.append(c[keep])
        nscores.append(s[keep])

    if not nclasses and not nscores:
        return None, None, None

    boxes = np.concatenate(nboxes)
    classes = np.concatenate(nclasses)
    scores = np.concatenate(nscores)

    return boxes, scores, classes

def draw(image, boxes, scores, classes):
    
    for box, score, cl in zip(boxes, scores, classes):
        x1, y1, x2, y2 = box
        print('class: {}, score: {}'.format(CLASSES[cl], score))
        print('box coordinate left,top,right,down: [{}, {}, {}, {}]'.format(x1, y1, x2, y2))
        x1 *= image.shape[1]
        y1 *= image.shape[0]
        x2 *= image.shape[1]
        y2 *= image.shape[0]
        left = max(0, np.floor(x1 + 0.5).astype(int))
        top = max(0, np.floor(y1 + 0.5).astype(int))
        right = min(image.shape[1], np.floor(x2 + 0.5).astype(int))
        bottom = min(image.shape[0], np.floor(y2 + 0.5).astype(int))

        cv.rectangle(image, (left, top), (right, bottom), (255, 0, 0), 2)
        cv.putText(image, '{0} {1:.2f}'.format(CLASSES[cl], score),
                    (left, top - 6),
                    cv.FONT_HERSHEY_SIMPLEX,
                    0.6, (0, 0, 255), 2)


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument("--library", help="Path to C static library file")
    parser.add_argument("--model", help="Path to nbg file")
    parser.add_argument("--source", default=None, help="the number of video camera")
    parser.add_argument("--imgsz", default=(640, 640), help="the stream adress")
    parser.add_argument("--visualize", default=False, help="visualize or not")
    parser.add_argument("--conf", default=None, help="visualize or not")
    parser.add_argument("--level", default='0', help="Information printer level: 0/1/2")

    args = parser.parse_args()
    ##----------------------------------------------------------------------------------------------
    if args.model:
        if os.path.exists(args.model) == False:
            sys.exit('Model \'{}\' not exist'.format(args.model))
        model = args.model
    else:
        sys.exit("NBG file not found !!! Please use format: --model")
    ##----------------------------------------------------------------------------------------------
    if not args.source:
        sys.exit("video camera not found !!!")
    else:
        source = args.source
        is_video_file = Path(source).suffix[1:] in (VID_FORMATS)
        is_image_file = Path(source).suffix[1:] in (IMG_FORMATS)
        is_url = source.lower().startswith(('rtsp://', 'rtmp://', 'http://', 'https://'))
        webcam = source.isnumeric()
        source = int(args.source) if webcam else args.source
    ##----------------------------------------------------------------------------------------------
    if args.library:
        if os.path.exists(args.library) == False :
            sys.exit('C static library \'{}\' not exist'.format(args.library))
        library = args.library
    else:
        sys.exit("C static library not found !!! Please use format: --library")
    ##----------------------------------------------------------------------------------------------
    if args.conf:
        if args.conf.endswith("json"):
            F = open("config.json")
            j = json.load(F)
            CLASSES = j["CLASSES"]
            NUM_CLS = len(CLASSES)
            LISTSIZE = NUM_CLS + 64
            SPAN, MAX_BOXES, OBJ_THRESH, NMS_THRESH = j["SETTINGS"]["SPAN"], j["SETTINGS"]["MAX_BOXES"], j["SETTINGS"]["OBJ_THRESH"], j["SETTINGS"]["NMS_THRESH"]
    else:
        sys.exit("config file wasn't found !!! Please use format: --conf")
    if args.level == '1' or args.level == '2' :
        level = int(args.level)
    else :
        level = 0
    ##----------------------------------------------------------------------------------------------

    yolov3 = KSNN('VIM3')
    print(' |---+ KSNN Version: {} +---| '.format(yolov3.get_nn_version()))

    print('Start init neural network ...')
    yolov3.nn_init(library=library, model=model, level=level)
    print('Done.')
    if is_video_file or is_url or webcam:
        cap = cv.VideoCapture(source)
        cap.set(3,1920)
        cap.set(4,1080)
        while(1):
            cv_img = list()
            ret,img = cap.read()
            cv_img.append(img)
            start = time.time()
            '''
                default input_tensor is 1
            '''
            data = yolov3.nn_inference(cv_img, platform='ONNX', reorder='2 1 0', output_tensor=3, output_format=output_format.OUT_FORMAT_FLOAT32)
            end = time.time()
            print('1 frame per: {}s'.format(end - start))
            input0_data = data[2]
            input1_data = data[1]
            input2_data = data[0]

            input0_data = input0_data.reshape(SPAN, LISTSIZE, GRID0, GRID0)
            input1_data = input1_data.reshape(SPAN, LISTSIZE, GRID1, GRID1)
            input2_data = input2_data.reshape(SPAN, LISTSIZE, GRID2, GRID2)
            
            input_data = list()
            input_data.append(np.transpose(input0_data, (2, 3, 0, 1)))
            input_data.append(np.transpose(input1_data, (2, 3, 0, 1)))
            input_data.append(np.transpose(input2_data, (2, 3, 0, 1)))

            boxes, scores, classes = yolov3_post_process(input_data)

            if boxes is not None:
                draw(img, boxes, scores, classes)

            if args.visualize:
                cv.imshow("capture", img)
                if cv.waitKey(1) & 0xFF == ord('q'):
                    break

        cap.release()
        cv.destroyAllWindows() 

    elif is_image_file:
        print('Get input data ...')
        cv_img =  list()
        orig_img = cv.imread(source, cv.IMREAD_COLOR)
        img = cv.resize(orig_img, (640, 640))
        cv_img.append(img)
        print('Done.')

        print('Start inference ...')
        start = time.time()
        data = yolov3.nn_inference(cv_img, platform='ONNX', reorder='2 1 0', output_tensor=3, output_format=output_format.OUT_FORMAT_FLOAT32)
        end = time.time()
        print('Done. inference time: ', end - start)

        input0_data = data[2]
        input1_data = data[1]
        input2_data = data[0]

        input0_data = input0_data.reshape(SPAN, LISTSIZE, GRID0, GRID0)
        input1_data = input1_data.reshape(SPAN, LISTSIZE, GRID1, GRID1)
        input2_data = input2_data.reshape(SPAN, LISTSIZE, GRID2, GRID2)

        input_data = list()
        input_data.append(np.transpose(input0_data, (2, 3, 0, 1)))
        input_data.append(np.transpose(input1_data, (2, 3, 0, 1)))
        input_data.append(np.transpose(input2_data, (2, 3, 0, 1)))
        
        boxes, scores, classes = yolov3_post_process(input_data)

        if boxes is not None:
            draw(orig_img, boxes, scores, classes)

        cv.imwrite("./result.jpg", orig_img)

        if args.visualize:
            cv.imshow("results", img)
            cv.waitKey(0)