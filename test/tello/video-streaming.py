import cv2
from djitellopy import Tello

tello = Tello()
tello.connect()

tello.streamon()

# tello.takeoff()

while True:
    try:
        frame_read = tello.get_frame_read()
        cv2.imshow("tello", cv2.resize(frame_read.frame, (640, 480)))
        cv2.waitKey(1)
    except KeyboardInterrupt:
        cv2.destroyAllWindows()
        # tello.land()
        print("Exit")
        break