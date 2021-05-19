# USAGE
# python pi_face_recognition.py --cascade haarcascade_frontalface_default.xml --encodings encodings.pickle

# import the necessary packages
from imutils.video import FPS, VideoStream
from datetime import datetime
import face_recognition
import argparse
import imutils
import pickle
import time
import cv2
import json
import sys
import signal
import os
import numpy as np
from tensorflow import keras
from keras_preprocessing.image import img_to_array
from google_drive_downloader import GoogleDriveDownloader as gdd


# To properly pass JSON.stringify()ed bool command line parameters, e.g. "--extendDataset"
# See: https://stackoverflow.com/questions/15008758/parsing-boolean-values-with-argparse
def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


def printjson(type, message):
    print(json.dumps({type: message}))
    sys.stdout.flush()


def signalHandler(signal, frame):
    global closeSafe
    closeSafe = True


def getEmotion(prediction):
    if prediction == 0:
        return "angry"
    if prediction == 1:
        return "disgust"
    if prediction == 2:
        return "fear"
    if prediction == 3:
        return "happy"
    if prediction == 4:
        return "sad"
    if prediction == 5:
        return "surprise"
    if prediction == 6:
        return "neutral"


signal.signal(signal.SIGINT, signalHandler)
closeSafe = False

# construct the argument parser and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument("-c", "--cascade", type=str, required=False, default="haarcascade_frontalface_default.xml",
                help="path to where the face cascade resides")
ap.add_argument("-e", "--encodings", type=str, required=False, default="encodings.pickle",
                help="path to serialized db of facial encodings")
ap.add_argument("-md", "--model", type=str, required=False, default="./models/VGG16-AUX-BEST-70.2.h5",
                help="Path to the Model File. (Keras .h5 file)")
ap.add_argument("-p", "--usePiCamera", type=int, required=False, default=1,
                help="Is using picamera or builtin/usb cam")
ap.add_argument("-s", "--source", type=int, required=False, default=0,
                help="Use 0 for /dev/video0 or 'http://link.to/stream'")
ap.add_argument("-r", "--rotateCamera", type=int, required=False, default=0,
                help="rotate camera")
ap.add_argument("-m", "--method", type=str, required=False, default="haar",
                help="method to detect faces (dnn, haar)")
ap.add_argument("-d", "--detectionMethod", type=str, required=False, default="hog",
                help="face detection model to use: either `hog` or `cnn`")
ap.add_argument("-i", "--interval", type=int, required=False, default=2000,
                help="interval between recognitions")
ap.add_argument("-o", "--output", type=int, required=False, default=1,
                help="Show output")
ap.add_argument("-eds", "--extendDataset", type=str2bool, required=False, default=False,
                help="Extend Dataset with unknown pictures")
ap.add_argument("-ds", "--dataset", required=False, default="../dataset/",
                help="path to input directory of faces + images")
ap.add_argument("-t", "--tolerance", type=float, required=False, default=0.6,
                help="How much distance between faces to consider it a match. Lower is more strict.")
args = vars(ap.parse_args())

if not os.path.exists(args["model"]):
    sys.exit("could not find FER model")

# load the known faces and embeddings along with OpenCV's Haar
# cascade for face detection
printjson("status", "loading encodings + face detector...")
data = pickle.loads(open(args["encodings"], "rb").read())
detector = cv2.CascadeClassifier(args["cascade"])
model = keras.models.load_model(args["model"])

# initialize the video stream and allow the camera sensor to warm up
printjson("status", "starting video stream...")

if args["usePiCamera"] >= 1:
    vs = VideoStream(usePiCamera=True, rotation=args["rotateCamera"]).start()
else:
    vs = VideoStream(src=args["source"]).start()
time.sleep(2.0)

# variable for prev names
prevNames = []
emotion = "neutral"

# create unknown path if needed
if args["extendDataset"] is True:
    unknownPath = os.path.dirname(args["dataset"] + "unknown/")
    try:
        os.stat(unknownPath)
    except:
        os.mkdir(unknownPath)

tolerance = float(args["tolerance"])

# start the FPS counter
fps = FPS().start()

# loop over frames from the video file stream
while True:
    # grab the frame from the threaded video stream and resize it
    # to 500px (to speedup processing)
    originalFrame = vs.read()
    frame = imutils.resize(originalFrame, width=500)

    if args["method"] == "dnn":
        # load the input image and convert it from BGR (OpenCV ordering)
        # to dlib ordering (RGB)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        # detect the (x, y)-coordinates of the bounding boxes
        # corresponding to each face in the input image
        boxes = face_recognition.face_locations(rgb,
                                                model=args["detectionMethod"])
    elif args["method"] == "haar":
        # convert the input frame from (1) BGR to grayscale (for face
        # detection) and (2) from BGR to RGB (for face recognition)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # detect faces in the grayscale frame
        rects = detector.detectMultiScale(gray, scaleFactor=1.3,
                                          minNeighbors=10, minSize=(75, 75),
                                          flags=cv2.CASCADE_SCALE_IMAGE)

        # OpenCV returns bounding box coordinates in (x, y, w, h) order
        # but we need them in (top, right, bottom, left) order, so we
        # need to do a bit of reordering
        boxes = [(y, x + w, y + h, x) for (x, y, w, h) in rects]

    # compute the facial embeddings for each face bounding box
    encodings = face_recognition.face_encodings(rgb, boxes)

    names = []
    persons = []
    minDistance = 0.0

    # loop over the facial embeddings
    for encoding in encodings:
        # compute distances between this encoding and the faces in dataset
        distances = face_recognition.face_distance(data["encodings"], encoding)

        # the smallest distance is the closest to the encoding
        minDistance = min(distances)

        # save the name if the distance is below the tolerance
        if minDistance < tolerance:
            idx = np.where(distances == minDistance)[0][0]
            person = {
                "name": data["names"][idx],
                "emotion": emotion
            }
            # name = data["names"][idx]
        else:
            person = {
                "name": "unknown",
                "emotion": emotion
            }
            # name = "unknown"

        # update the list of names
        names.append(person["name"])
        persons.append(person)

    # loop over the recognized faces
    for ((top, right, bottom, left), person) in zip(boxes, persons):
        # draw the predicted face name on the image

        # Preprocessing for our model
        roi = frame[top:bottom, left:right]
        roi = cv2.resize(roi, (197, 197))
        roi = img_to_array(roi)
        roi = np.expand_dims(roi, axis=0)

        predictions = model.predict(roi)
        classes = np.argmax(predictions, axis=1)
        em = getEmotion(classes[0])
        if emotion != em:
            emotion = em
            person["emotion"] = emotion
            printjson("emotion", {
                "person": person
            })

        cv2.rectangle(frame, (left, top), (right, bottom),
                      (0, 255, 0), 2)

        y = top - 15 if top - 15 > 15 else top + 15
        txt = person["name"] + " (" + "{:.2f}".format(minDistance) + ")" + person["emotion"]
        cv2.putText(frame, txt, (left, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.75, (0, 255, 0), 2)

    # display the image to our screen
    if args["output"] == 1:
        cv2.imshow("Frame", frame)

    # update the FPS counter
    fps.update()

    logins = []
    logouts = []
    # Check which names are new login and which are new logout with prevNames
    for n in names:
        if prevNames.__contains__(n) == False and n is not None:
            logins.append(n)

            # if extendDataset is active we need to save the picture
            if args["extendDataset"] is True:
                # set correct path to the dataset
                path = os.path.dirname(args["dataset"] + '/' + n + '/')

                today = datetime.now()
                cv2.imwrite(path + '/' + n + '_' + today.strftime("%Y%m%d_%H%M%S") + '.jpg', originalFrame)
    for n in prevNames:
        if names.__contains__(n) == False and n is not None:
            logouts.append(n)

    # send inforrmation to prompt, only if something has changes
    if logins.__len__() > 0:
        printjson("login", {
            "names": logins
        })

    if logouts.__len__() > 0:
        printjson("logout", {
            "names": logouts
        })

    # set this names as new prev names for next iteration
    prevNames = names

    key = cv2.waitKey(1) & 0xFF
    # if the `q` key was pressed, break from the loop
    if key == ord("q") or closeSafe == True:
        break

    time.sleep(args["interval"] / 1000)

# stop the timer and display FPS information
fps.stop()
printjson("status", "elasped time: {:.2f}".format(fps.elapsed()))
printjson("status", "approx. FPS: {:.2f}".format(fps.fps()))

# do a bit of cleanup
cv2.destroyAllWindows()
vs.stop()
