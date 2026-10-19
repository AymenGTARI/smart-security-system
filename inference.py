import cv2
import time
from pathlib import Path
from ultralytics import YOLO
from collections import deque

BASE_DIR   = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "best.pt"

CONF_THRESHOLD = 0.5
FRAME_HISTORY  = 5
HOLD_TIME      = 5

REQUIRED_PPE     = {"Hardhat", "Mask", "Safety Vest"}
VIOLATION_CLASSES = {"NO-Hardhat", "NO-Mask", "NO-Safety Vest"}
IGNORE_CLASSES   = {"Person", "Safety Cone", "machinery", "vehicle"}

#model = YOLO("best.onnx", task="detect")
model = YOLO("best_ncnn_model", task="detect")
#model = YOLO(str(MODEL_PATH))
#model.to("cpu")
print("[INFO] Model classes:", model.names)

helmet_hist   = deque(maxlen=FRAME_HISTORY)
mask_hist     = deque(maxlen=FRAME_HISTORY)
vest_hist     = deque(maxlen=FRAME_HISTORY)
violation_hist = deque(maxlen=FRAME_HISTORY)

stable_state     = "INIT"
last_change_time = time.time()


def reset_ppe_state():
    """Remet a zero l'historique et l'etat stable — a appeler apres chaque reset."""
    global stable_state, last_change_time
    helmet_hist.clear()
    mask_hist.clear()
    vest_hist.clear()
    violation_hist.clear()
    stable_state     = "INIT"
    last_change_time = time.time()


def detect_ppe(frame):
    """
    Returns:
        annotated_frame : frame with YOLO annotations
        ppe_ok          : bool
        stable_state    : str  "ALL_OK" | "VIOLATION" | "INCOMPLETE"
        detail          : dict  { 'helmet': bool, 'mask': bool, 'vest': bool,
                                  'violation': bool }
    """
    global stable_state, last_change_time

    frame = cv2.convertScaleAbs(frame, alpha=1.2, beta=20)
    #img   = cv2.resize(frame, (640, 640))
    #results = model.predict(source=img, conf=CONF_THRESHOLD, verbose=False)
    #optimization
    img = cv2.resize(frame, (320, 320))
    results = model.predict(source=img, conf=CONF_THRESHOLD, imgsz=320, verbose=False)
    annotated_frame = results[0].plot()
    names = model.names

    detected          = set()
    violation_detected = False

    for box in results[0].boxes:
        cls   = int(box.cls[0])
        label = names[cls]
        if label in IGNORE_CLASSES:
            continue
        if label in REQUIRED_PPE:
            detected.add(label)
        if label in VIOLATION_CLASSES:
            violation_detected = True

    helmet_hist.append("Hardhat"     in detected)
    mask_hist.append(  "Mask"        in detected)
    vest_hist.append(  "Safety Vest" in detected)
    violation_hist.append(violation_detected)

    helmet_ok    = sum(helmet_hist)    >= 3
    mask_ok      = sum(mask_hist)      >= 3
    vest_ok      = sum(vest_hist)      >= 3
    violation_ok = sum(violation_hist) >= 3

    if violation_ok:
        current_state = "VIOLATION"
    elif helmet_ok and mask_ok and vest_ok:
        current_state = "ALL_OK"
    else:
        current_state = "INCOMPLETE"

    now = time.time()
    if current_state != stable_state:
        if now - last_change_time > HOLD_TIME:
            stable_state     = current_state
            last_change_time = now
    else:
        last_change_time = now

    if stable_state == "ALL_OK":
        text  = "ALL PPE DETECTED"
        color = (0, 255, 0)
        ppe_ok = True
    elif stable_state == "VIOLATION":
        text  = "VIOLATION DETECTED"
        color = (0, 0, 255)
        ppe_ok = False
    else:
        text  = "PPE INCOMPLETE"
        color = (0, 0, 255)
        ppe_ok = False

    cv2.putText(annotated_frame, text, (20, 170),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 3)

    def draw_status(label, status, y):
        c   = (0, 255, 0) if status else (0, 0, 255)
        txt = f"{label}: {'OK' if status else 'NO'}"
        cv2.putText(annotated_frame, txt, (20, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, c, 2)

    draw_status("Helmet", helmet_ok, 40)
    draw_status("Mask",   mask_ok,   80)
    draw_status("Vest",   vest_ok,   120)

    detail = {
        "helmet":    helmet_ok,
        "mask":      mask_ok,
        "vest":      vest_ok,
        "violation": violation_ok,
    }

    return annotated_frame, ppe_ok, stable_state, detail