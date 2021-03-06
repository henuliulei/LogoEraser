# Example:
# python test_video.py -f ./examples/video.mp4 -o ./examples/output_video.mp4 -w weights.h5 -c ./csvpaths/classes.csv

import keras
import keras.preprocessing.image
from keras_retinanet.models.resnet import custom_objects
from keras_retinanet.preprocessing.generator import Generator
from train import create_models
from keras_retinanet.utils.image import preprocess_image, resize_image, random_transform
from six import raise_from

import matplotlib.pyplot as plt
import cv2
import os
import numpy as np
import time
import sys
import getopt

import numpy as np
import os
import scipy.io
from scripts.data_manipulation import *

import tensorflow as tf


def get_session():
    config = tf.ConfigProto()
    config.gpu_options.allow_growth = False
    return tf.Session(config=config)


os.environ["CUDA_VISIBLE_DEVICES"] = "0"
keras.backend.tensorflow_backend.set_session(get_session())


def parse(argv):
    p = dict()
    try:
        opts, args = getopt.getopt(argv, 'f:o:w:c:e:', ['-f=', '-o=', '-w=', '-c=', '-e='])
    except getopt.GetoptError:
        print('see readme for instructions')
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print('args: -f = path to photo, -o = output photo path, -w = weights path,'
                  ' -c = classes csv path, -e = erase(True or False)')
            sys.exit()
        elif opt in ('-f'):
            p['input_path'] = arg
        elif opt in ('-o'):
            p['output_path'] = arg
        elif opt in ('-w'):
            p['weights_path'] = arg
        elif opt in ('-c'):
            p['classes_csv'] = arg
        elif opt in ('-e'):
            p['erase'] = arg
    return p


def params(argv):
    args = parse(argv)
    p = dict()
    p['output'] = args['output_path']
    p['video'] = args['input_path']
    p['weights'] = args['weights_path']
    p['resnet'] = 50
    p['learning-rate'] = 1e-5
    p['valid-samples'] = 3960
    p['train-samples'] = 8150
    p['l2n'] = label2name(args['classes_csv'])
    p['erase'] = args['erase']
    return p


def create_models_local(p):
    model, training_model, prediction_model = create_models(num_classes=32, p=p)
    return model, training_model, prediction_model


def _parse(value, function, fmt):
    try:
        return function(value)
    except ValueError as e:
        raise_from(ValueError(fmt.format(e)), None)


def _open_for_csv(path):
    if sys.version_info[0] < 3:
        return open(path, 'rb')
    else:
        return open(path, 'r', newline='')


def _read_classes(csv_reader):
    result = {}
    for line, row in enumerate(csv_reader):
        try:
            class_name, class_id = row
        except ValueError:
            raise_from(ValueError('line {}: format should be \'class_name,class_id\''.format(line)), None)
        class_id = _parse(class_id, int, 'line {}: malformed class ID: {{}}'.format(line))

        if class_name in result:
            raise ValueError('line {}: duplicate class name: \'{}\''.format(line, class_name))
        result[class_name] = class_id
    return result


def label2name(csv_class_file):
    try:
        with _open_for_csv(csv_class_file) as file:
            classes = _read_classes(csv.reader(file, delimiter=','))
    except ValueError as e:
        raise_from(ValueError('invalid CSV class file: {}: {}'.format(csv_class_file, e)), None)

    labels = {}
    for key, value in classes.items():
        labels[value] = key

    return labels


def logopreds(prediction_model, image, p):
    draw = image.copy()

    # Masking을 위한 프레임 생성
    mask = np.zeros(image.shape, np.uint8)
    mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)

    image = preprocess_image(image)
    image, scale = resize_image(image)

    _, _, detections = prediction_model.predict_on_batch(np.expand_dims(image, axis=0))

    predicted_labels = np.argmax(detections[0, :, 4:], axis=1)
    scores = detections[0, np.arange(detections.shape[1]), 4 + predicted_labels]

    detections[:, :4] /= scale

    for idx, (label, score) in enumerate(zip(predicted_labels, scores)):
        if score < 0.3:
            continue
        b = detections[0, idx, :4].astype(int)

        # 타원으로 마스킹 하기 위한 계산(center: 타원 중심, axes: 중심에서 가장 큰 거리와 작은 거리)
        center = ((int)((b[0] + b[2]) / 2), (int)((b[1] + b[3]) / 2))
        axes = ((int)(abs((b[0] - b[2]) / 2)), (int)(abs((b[1] - b[3]) / 2)))

        if p['erase'] == "erase":

            # Detect된 영역 Masking(사각형)
            # cv2.rectangle(mask, (b[0], b[1]), (b[2], b[3]), (255, 255, 255), -1)

            # Detect된 영역 Masking(타원)
            cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1)

            # cv2.INPAINT_TELEA / cv2.INPAINT_NS
            dst = cv2.inpaint(draw, mask, 0.01, cv2.INPAINT_NS)
            draw = dst
        else:
            cv2.rectangle(draw, (b[0], b[1]), (b[2], b[3]), (0, 0, 255), 3)
            caption = "{} {:.3f}".format(p['l2n'][label], score)
            cv2.putText(draw, caption, (b[0], b[1] - 10), cv2.FONT_HERSHEY_PLAIN, 1.5, (0, 0, 0), 3)
            cv2.putText(draw, caption, (b[0], b[1] - 10), cv2.FONT_HERSHEY_PLAIN, 1.5, (255, 255, 255), 2)
    #cv2.imshow("mask", mask)
    return draw


def main(argv):
    p = params(argv)

    model, training_model, prediction_model = create_models_local(p)

    cap = cv2.VideoCapture(p['video'])

    fourcc = cv2.VideoWriter_fourcc(*'MP4V')
    # 영상 크기에 맞게 조절해야 저장됨
    out = cv2.VideoWriter(p['output'], fourcc, 20.0, (854, 480))

    while (cap.isOpened()):
        ret, frame = cap.read()

        if ret != True:
            break

        draw = logopreds(prediction_model, frame, p)

        # Display the resulting frame
        cv2.imshow('frame', draw)
        out.write(draw)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # When everything done, release the capture
    cap.release()
    out.release()
    cv2.destroyAllWindows()


# showlogo(prediction_model, p['input_photo'],p['output_photo'],p)


if __name__ == '__main__':
    main(sys.argv[1:])

