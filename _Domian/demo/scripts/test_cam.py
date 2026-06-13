import cv2
cap = cv2.VideoCapture(0)
print("Cámara detectada:", cap.isOpened())
ret, frame = cap.read()
print("Frame capturado:", ret)
if ret:
    print("Resolución:", frame.shape)
cap.release()