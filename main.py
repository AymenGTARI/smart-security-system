#python -m venv venv
#.\venv\Scripts\activate
# pip install opencv-python pyttsx3 face_recognition ultralytics

import cv2
import pyttsx3
import threading
import queue
import time
import subprocess
import tkinter as tk
from tkinter import font as tkfont
import math

from face_recognition_module import recognize_face
from inference import detect_ppe, reset_ppe_state
from servo_controller import ServoController

# ================================================================
# AUDIO
# ================================================================
speech_queue = queue.Queue()

def speak_direct(text):
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 150)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception:
        try:
            subprocess.Popen(["espeak", text])
        except Exception:
            pass

def speech_worker():
    while True:
        text = speech_queue.get()
        if text is None:
            break
        speak_direct(text)
        speech_queue.task_done()

threading.Thread(target=speech_worker, daemon=True).start()

def speak(text):
    speech_queue.put(text)

# ================================================================
# PALETTE — Interface claire & professionnelle
# ================================================================
BG        = "#F0F4F8"          # Gris bleuté très clair (fond principal)
WHITE     = "#FFFFFF"          # Blanc pur
MUTED     = "#A0AEC0"          # Gris moyen (textes secondaires)
GREEN     = "#22863A"          # Vert foncé lisible
GREEN_BG  = "#D4EDDA"          # Fond vert pâle
RED       = "#C0392B"          # Rouge vif lisible
RED_BG    = "#FDECEA"          # Fond rouge pâle
AMBER     = "#B7791F"          # Ambre foncé lisible
AMBER_BG  = "#FEF3CD"          # Fond ambre pâle
PANEL_BG  = "#FFFFFF"          # Panneau blanc
ACCENT    = "#2B6CB0"          # Bleu professionnel (en-tête, accents)
TEXT_DARK = "#1A202C"          # Texte principal très foncé
TEXT_MID  = "#4A5568"          # Texte secondaire
BORDER    = "#CBD5E0"          # Bordures légères

# ================================================================
# GUI
# ================================================================
class FaceDisplay:
    """
    Interface claire, moderne et professionnelle.
    Layout grid redimensionnable.
    """

    def __init__(self, root):
        self.root = root
        root.title("Intelligent Security System")
        root.configure(bg=BG)

        root.minsize(560, 440)
        root.resizable(True, True)
        try:
            root.state("zoomed")
        except Exception:
            root.attributes("-fullscreen", True)

        # ── Layout principal ─────────────────────────────────────
        root.rowconfigure(0, weight=0)   # bandeau en-tête
        root.rowconfigure(1, weight=3)   # canvas yeux
        root.rowconfigure(2, weight=2)   # panneau EPI
        root.rowconfigure(3, weight=0)   # pied de page
        root.columnconfigure(0, weight=1)

        # ── Bandeau en-tête ──────────────────────────────────────
        header_frame = tk.Frame(root, bg=ACCENT, pady=8)
        header_frame.grid(row=0, column=0, sticky="ew")
        header_frame.columnconfigure(0, weight=1)

        tk.Label(
            header_frame,
            text="🛡  INTELLIGENT SECURITY SYSTEM",
            bg=ACCENT, fg=WHITE,
            font=tkfont.Font(family="Helvetica", size=13, weight="bold"),
            anchor="center"
        ).grid(row=0, column=0)

        # ── Canvas visage ─────────────────────────────────────────
        self.canvas = tk.Canvas(root, bg=BG, highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew")

        # ── Panneau EPI ───────────────────────────────────────────
        panel = tk.Frame(root, bg=PANEL_BG,
                         highlightbackground=BORDER, highlightthickness=1)
        panel.grid(row=2, column=0, sticky="nsew", padx=24, pady=(4, 8))

        panel.rowconfigure(0, weight=1)
        panel.rowconfigure(1, weight=0)
        panel.rowconfigure(2, weight=1)
        panel.columnconfigure(0, weight=1)

        # Grille 2×2 des indicateurs
        grid = tk.Frame(panel, bg=PANEL_BG)
        grid.grid(row=0, column=0, sticky="nsew", padx=20, pady=8)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.rowconfigure(0, weight=1)
        grid.rowconfigure(1, weight=1)

        rows = [
            ("🪖  HELMET",  "helmet"),
            ("😷  MASK",    "mask"),
            ("🦺  VEST",    "vest"),
            ("🔑  ACCESS",  "access"),
        ]

        self._status_vars   = {}
        self._status_labels = {}
        self._cell_frames   = {}

        for idx, (display, key) in enumerate(rows):
            col_idx = idx % 2
            row_idx = idx // 2

            # Carte individuelle avec bordure et coins arrondis simulés
            cell = tk.Frame(grid, bg=WHITE,
                            highlightbackground=BORDER, highlightthickness=1,
                            padx=14, pady=8)
            cell.grid(row=row_idx, column=col_idx,
                      sticky="nsew", padx=8, pady=6)
            cell.rowconfigure(0, weight=1)
            cell.rowconfigure(1, weight=1)
            cell.columnconfigure(0, weight=1)
            self._cell_frames[key] = cell

            tk.Label(
                cell, text=display, bg=WHITE, fg=TEXT_MID,
                font=tkfont.Font(family="Helvetica", size=10, weight="bold"),
                anchor="w"
            ).grid(row=0, column=0, sticky="w")

            var = tk.StringVar(value="—")
            val_lbl = tk.Label(
                cell, textvariable=var, bg=WHITE, fg=TEXT_DARK,
                font=tkfont.Font(family="Helvetica", size=12, weight="bold"),
                anchor="w"
            )
            val_lbl.grid(row=1, column=0, sticky="w")
            self._status_vars[key]   = var
            self._status_labels[key] = val_lbl

        # Séparateur
        tk.Frame(panel, bg=BORDER, height=1).grid(
            row=1, column=0, sticky="ew", padx=20, pady=2)

        # Zone message + compte à rebours
        msg_frame = tk.Frame(panel, bg=PANEL_BG)
        msg_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=6)
        msg_frame.columnconfigure(0, weight=1)
        msg_frame.rowconfigure(0, weight=1)
        msg_frame.rowconfigure(1, weight=1)

        self._msg_var = tk.StringVar(value="Waiting for detection...")
        self._msg_lbl = tk.Label(
            msg_frame, textvariable=self._msg_var,
            bg=PANEL_BG, fg=TEXT_MID,
            font=tkfont.Font(family="Helvetica", size=10, weight="bold"),
            wraplength=800, justify="center"
        )
        self._msg_lbl.grid(row=0, column=0, sticky="ew")

        self._cdt_var = tk.StringVar(value="")
        tk.Label(
            msg_frame, textvariable=self._cdt_var,
            bg=PANEL_BG, fg=MUTED,
            font=tkfont.Font(family="Helvetica", size=11)
        ).grid(row=1, column=0)

        # ── Pied de page ──────────────────────────────────────────
        tk.Label(
            root,
            text="[R] Reset   [Q] Quit",
            bg=BG, fg=MUTED,
            font=tkfont.Font(family="Helvetica", size=9)
        ).grid(row=3, column=0, pady=(0, 6))

        # ── État interne ──────────────────────────────────────────
        self._state       = "sleeping"
        self._anim_tick   = 0
        self._blink       = False
        self._blink_timer = 0
        self._eye_items   = []

        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self._draw_eyes()
        self._animate()

    # ── Resize handler ────────────────────────────────────────────
    def _on_canvas_resize(self, event):
        W = event.width
        H = event.height
        margin = max(60, W // 8)
        self.EYE_RX = max(40, min(W // 9, H // 4))
        self.EYE_RY = self.EYE_RX
        self.EYE_Y  = H // 2
        self.EL_X   = margin + self.EYE_RX
        self.ER_X   = W - margin - self.EYE_RX
        self._msg_lbl.configure(wraplength=max(300, W - 60))

    # ── API publique (thread-safe) ─────────────────────────────────
    def set_sleeping(self):
        self.root.after(0, self._apply_sleeping)

    def set_neutral(self, nom=""):
        self.root.after(0, lambda: self._apply_neutral(nom))

    def set_happy(self, items: dict, msg: str, countdown: int = 0):
        self.root.after(0, lambda: self._apply_happy(items, msg, countdown))

    def set_angry(self, items: dict, msg: str):
        self.root.after(0, lambda: self._apply_angry(items, msg))

    def set_incomplete(self, items: dict, msg: str):
        self.root.after(0, lambda: self._apply_incomplete(items, msg))

    # ── Setters internes ──────────────────────────────────────────
    def _apply_sleeping(self):
        self._state = "sleeping"
        self._cdt_var.set("")
        self._update_status({}, "No person detected", MUTED)

    def _apply_neutral(self, nom):
        self._state = "neutral"
        self._cdt_var.set("")
        msg = f"Analysing... {nom}" if nom else "Face detected — analysing..."
        self._update_status({}, msg, ACCENT)

    def _apply_happy(self, items, msg, countdown):
        self._state = "happy"
        cdt = f"Resetting in {countdown}s..." if countdown > 0 else ""
        self._cdt_var.set(cdt)
        self._update_status(items, msg, GREEN)

    def _apply_angry(self, items, msg):
        self._state = "angry"
        self._cdt_var.set("")
        self._update_status(items, msg, RED)

    def _apply_incomplete(self, items, msg):
        self._state = "incomplete"
        self._cdt_var.set("")
        self._update_status(items, msg, AMBER)

    def _update_status(self, items: dict, msg: str, msg_color: str):
        defaults = {"helmet": "—", "mask": "—", "vest": "—", "access": "—"}
        merged = {**defaults, **items}
        for key, val in merged.items():
            if key not in self._status_vars:
                continue
            self._status_vars[key].set(val)
            if "✅" in val:
                fg       = GREEN
                cell_bg  = GREEN_BG
                border   = GREEN
            elif "❌" in val:
                fg       = RED
                cell_bg  = RED_BG
                border   = RED
            else:
                fg       = TEXT_DARK
                cell_bg  = WHITE
                border   = BORDER
            self._status_labels[key].configure(fg=fg, bg=cell_bg)
            cell = self._cell_frames[key]
            cell.configure(bg=cell_bg, highlightbackground=border)
            # Mettre à jour aussi le label de titre de la carte
            for child in cell.winfo_children():
                if child != self._status_labels[key]:
                    child.configure(bg=cell_bg)

        self._msg_var.set(msg)
        self._msg_lbl.configure(fg=msg_color)

    # ── Dessin des yeux ───────────────────────────────────────────
    def _clear_eyes(self):
        for item in self._eye_items:
            self.canvas.delete(item)
        self._eye_items = []

    def _draw_eyes(self):
        self._clear_eyes()
        if not hasattr(self, "EYE_RX"):
            self.root.after(50, self._draw_eyes)
            return

        state  = self._state
        t      = self._anim_tick
        RX, RY = self.EYE_RX, self.EYE_RY
        # Couleurs des yeux adaptées au thème clair
        EYE_SLEEP   = "#CBD5E0"
        EYE_NEUTRAL = ACCENT
        EYE_HAPPY   = GREEN
        EYE_ANGRY   = RED
        EYE_AMBER   = AMBER

        for i, x in enumerate([self.EL_X, self.ER_X]):
            y = self.EYE_Y

            if state == "sleeping":
                self._eye_items.append(self.canvas.create_line(
                    x - RX, y, x + RX, y,
                    fill=EYE_SLEEP, width=max(5, RX // 8), capstyle="round"))

            elif state == "neutral":
                if self._blink:
                    self._eye_items.append(self.canvas.create_line(
                        x - RX, y, x + RX, y,
                        fill=EYE_NEUTRAL, width=max(5, RX // 8), capstyle="round"))
                else:
                    # Cercle plein avec anneau
                    self._eye_items.append(self.canvas.create_oval(
                        x - RX, y - RY, x + RX, y + RY,
                        outline=EYE_NEUTRAL, width=max(5, RX // 8), fill=BG))
                    # Pupille
                    pr = max(8, RX // 4)
                    self._eye_items.append(self.canvas.create_oval(
                        x - pr, y - pr, x + pr, y + pr,
                        fill=EYE_NEUTRAL, outline=""))

            elif state == "happy":
                pts = []
                for angle in range(180, 361, 4):
                    rad = math.radians(angle)
                    pts.extend([x + RX * math.cos(rad),
                                 y + RY * math.sin(rad)])
                pts.extend([x + RX, y, x - RX, y])
                self._eye_items.append(
                    self.canvas.create_polygon(pts, fill=EYE_HAPPY, outline=""))

            elif state == "angry":
                pts = []
                for angle in range(0, 181, 4):
                    rad = math.radians(angle)
                    pts.extend([x + RX * math.cos(rad),
                                 y - RY * math.sin(rad)])
                pts.extend([x + RX, y, x - RX, y])
                offset = RY // 2
                if i == 0:
                    pts[1] -= offset
                else:
                    pts[-3] -= offset
                self._eye_items.append(
                    self.canvas.create_polygon(pts, fill=EYE_ANGRY, outline=""))

            elif state == "incomplete":
                pulsed = (RY // 6) + (RY // 15) * math.sin(t * 0.15)
                self._eye_items.append(self.canvas.create_rectangle(
                    x - RX, y - pulsed, x + RX, y + pulsed,
                    fill=EYE_AMBER, outline=""))

    def _animate(self):
        self._anim_tick += 1
        if self._state == "neutral":
            if self._anim_tick - self._blink_timer > 90:
                self._blink = True
                if self._anim_tick - self._blink_timer > 94:
                    self._blink = False
                    self._blink_timer = self._anim_tick
        self._draw_eyes()
        self.root.after(33, self._animate)


# ================================================================
# MAIN
# ================================================================
def main():
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640) 
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 15)

    person_locked      = False
    locked_name        = None
    last_unknown_speak = 0
    UNKNOWN_COOLDOWN   = 3
    last_seen_name     = None
    last_seen_time     = 0
    LOCK_DELAY         = 2
    last_ppe_state     = None
    last_voice_time    = 0
    VOICE_COOLDOWN     = 5
    all_ok_since       = None
    AUTO_RESET_DELAY   = 8
    frozen_items       = None
    frozen_msg         = None

    root    = tk.Tk()
    face_ui = FaceDisplay(root)
    servo   = ServoController(pin=18)   # GPIO 18 (BCM) — change pin if needed

    def do_reset():
        nonlocal person_locked, locked_name, last_seen_name, last_seen_time
        nonlocal last_ppe_state, last_voice_time, last_unknown_speak
        nonlocal all_ok_since, frozen_items, frozen_msg
        person_locked      = False
        locked_name        = None
        last_seen_name     = None
        last_seen_time     = 0
        last_ppe_state     = None
        last_voice_time    = 0
        last_unknown_speak = 0
        all_ok_since       = None
        frozen_items       = None
        frozen_msg         = None
        while not speech_queue.empty():
            try:
                speech_queue.get_nowait()
                speech_queue.task_done()
            except Exception:
                break
        reset_ppe_state()
        servo.close()          # ensure gate is closed on manual reset
        face_ui.set_sleeping()

    def detection_loop():
        nonlocal person_locked, locked_name, last_unknown_speak
        nonlocal last_seen_name, last_seen_time, last_ppe_state, last_voice_time
        nonlocal all_ok_since, frozen_items, frozen_msg
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # ── ÉTAPE 1 : Reconnaissance faciale ─────────────────
            if not person_locked:
                name, frame, face_detected = recognize_face(frame)

                if not face_detected:
                    face_ui.set_sleeping()

                elif name == "Inconnu":
                    face_ui.set_neutral("Unknown")
                    if time.time() - last_unknown_speak > UNKNOWN_COOLDOWN:
                        speak("Unrecognized person")
                        last_unknown_speak = time.time()

                elif name not in ["Aucun"]:
                    face_ui.set_neutral(name)
                    if name == last_seen_name:
                        if time.time() - last_seen_time > LOCK_DELAY:
                            person_locked = True
                            locked_name   = name
                            speak(f"Welcome {name}")
                    else:
                        last_seen_name = name
                        last_seen_time = time.time()

            # ── ÉTAPE 2 : Détection EPI ───────────────────────────
            else:
                if all_ok_since is not None:
                    elapsed   = time.time() - all_ok_since
                    remaining = max(0, int(AUTO_RESET_DELAY - elapsed) + 1)
                    if elapsed >= AUTO_RESET_DELAY:
                        do_reset()
                    else:
                        face_ui.set_happy(frozen_items, frozen_msg, countdown=remaining)

                    cv2.imshow("Camera Feed", frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('r'):
                        do_reset()
                    if key == ord('q'):
                        root.quit()
                        break
                    continue

                frame, ppe_ok, state, detail = detect_ppe(frame)

                def item_label(ok, violation=False):
                    if violation:
                        return "VIOLATION ❌"
                    return "Detected ✅" if ok else "Not detected ❌"

                v = detail.get("violation", False)
                items = {
                    "helmet": item_label(detail["helmet"], v),
                    "mask":   item_label(detail["mask"],   v),
                    "vest":   item_label(detail["vest"],   v),
                    "access": "GRANTED ✅" if ppe_ok else "DENIED ❌",
                }

                if state == "ALL_OK":
                    msg = f"Welcome {locked_name} — access granted"
                elif state == "VIOLATION":
                    msg = "PPE violation detected — access denied"
                else:
                    msg = "Incomplete safety equipment — access denied"

                if state == "ALL_OK":
                    if all_ok_since is None:
                        all_ok_since = time.time()
                        frozen_items = dict(items)
                        frozen_msg   = msg
                        servo.open()   # 0° → 90° ; auto-close after 5 s
                    face_ui.set_happy(frozen_items, frozen_msg, countdown=AUTO_RESET_DELAY)
                elif state == "VIOLATION":
                    all_ok_since = None
                    face_ui.set_angry(items, msg)
                else:
                    all_ok_since = None
                    face_ui.set_incomplete(items, msg)

                if state != last_ppe_state:
                    last_ppe_state = state
                    if time.time() - last_voice_time > VOICE_COOLDOWN:
                        if state == "ALL_OK":
                            speak("Welcome, you may enter the work area")
                        elif state == "VIOLATION":
                            speak("PPE violation detected")
                        elif state == "INCOMPLETE":
                            speak("Incomplete safety equipment")
                        last_voice_time = time.time()

            cv2.imshow("Camera Feed", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('r'):
                do_reset()
            if key == ord('q'):
                root.quit()
                break

        cap.release()
        cv2.destroyAllWindows()
        servo.cleanup()
        speech_queue.put(None)

    threading.Thread(target=detection_loop, daemon=True).start()
    root.mainloop()


if __name__ == "__main__":
    main()