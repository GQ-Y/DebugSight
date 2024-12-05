import cv2
from src.utils import extract_frame, save_frame

def process_camera(camera_index, show_video=False):
    source = cv2.VideoCapture(camera_index)
    while True:
        frame = extract_frame(source)
        if frame is None:
            break
        if show_video:
            cv2.imshow('Local Camera', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        yield frame
    source.release()
    if show_video:
        cv2.destroyAllWindows()