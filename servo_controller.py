# servo_controller.py
# pip install RPi.GPIO  (Raspberry Pi only)
# ================================================================
# SERVO MOTOR CONTROLLER
# ================================================================
import threading
import time

try:
    import RPi.GPIO as GPIO
    _GPIO_AVAILABLE = True
except ImportError:
    _GPIO_AVAILABLE = False   # PC de développement : simulation console


class ServoController:
    """
    Controls a servo motor via GPIO PWM (Raspberry Pi).

    Pin        : BCM numbering (default GPIO 18)
    Open gate  : 0°  → 90°   (duty ~2.5 % → ~7.5 %)
    Close gate : 90° →  0°   automatically after CLOSE_DELAY seconds
    Safe       : always cleans up GPIO on exit.

    On non-Pi hardware the class falls back to console simulation
    so the rest of the application runs without error.

    Usage
    -----
        servo = ServoController(pin=18)
        servo.open()      # opens gate, auto-closes after 5 s
        servo.close()     # force-close immediately
        servo.cleanup()   # call on application exit
    """

    FREQ        = 50    # Hz  — standard servo PWM frequency
    OPEN_ANGLE  = 90    # degrees — gate open position
    CLOSE_ANGLE = 0     # degrees — gate closed position
    CLOSE_DELAY = 5     # seconds before automatic close

    def __init__(self, pin: int = 18):
        self._pin   = pin
        self._pwm   = None
        self._lock  = threading.Lock()
        self._timer = None          # pending auto-close timer
        self._angle = self.CLOSE_ANGLE
        self._setup()

    # ── Private helpers ───────────────────────────────────────────

    def _angle_to_duty(self, angle: float) -> float:
        """Convert 0-180° to PWM duty cycle (2.5 % – 12.5 %)."""
        return 2.5 + (angle / 180.0) * 10.0

    def _setup(self):
        """Initialise GPIO and start PWM at closed position."""
        if not _GPIO_AVAILABLE:
            print(f"[SERVO] Simulation mode — GPIO not available (pin {self._pin})")
            return
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self._pin, GPIO.OUT)
        self._pwm = GPIO.PWM(self._pin, self.FREQ)
        self._pwm.start(0)                              # démarrer PWM à 0 — aucun mouvement
        time.sleep(0.1)                                 # laisser le PWM se stabiliser
        self._pwm.ChangeDutyCycle(self._angle_to_duty(self.CLOSE_ANGLE))
        time.sleep(0.4)                                 # laisser le servo atteindre 0°
        self._pwm.ChangeDutyCycle(0)                    # couper le signal — pas de jitter
        print(f"[SERVO] Initialised on GPIO {self._pin} — position CLOSED ({self.CLOSE_ANGLE}°)")

    def _move(self, angle: float):
        """
        Send PWM signal to reach target angle, then cut signal to avoid jitter.
        Must be called from inside self._lock.
        """
        self._angle = angle
        if _GPIO_AVAILABLE and self._pwm:
            self._pwm.ChangeDutyCycle(self._angle_to_duty(angle))
            time.sleep(0.4)         # wait for servo to reach position
            self._pwm.ChangeDutyCycle(0)    # cut signal — no jitter
        else:
            print(f"[SERVO] → {angle}°")

    def _cancel_timer(self):
        """Cancel any pending auto-close timer."""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    # ── Public API ────────────────────────────────────────────────

    def open(self):
        """
        Open gate : 0° → 90°.
        Schedules automatic close after CLOSE_DELAY seconds.
        Non-blocking — runs in a background thread.
        """
        def _do_open():
            with self._lock:
                self._cancel_timer()
                print(f"[SERVO] Opening gate  : {self.CLOSE_ANGLE}° → {self.OPEN_ANGLE}°")
                self._move(self.OPEN_ANGLE)
                self._timer = threading.Timer(self.CLOSE_DELAY, self.close)
                self._timer.daemon = True
                self._timer.start()
                print(f"[SERVO] Auto-close scheduled in {self.CLOSE_DELAY}s")

        threading.Thread(target=_do_open, daemon=True).start()

    def close(self):
        """
        Close gate immediately : 90° → 0°.
        Cancels any pending auto-close timer.
        Non-blocking — runs in a background thread.
        """
        def _do_close():
            with self._lock:
                self._cancel_timer()
                print(f"[SERVO] Closing gate  : {self.OPEN_ANGLE}° → {self.CLOSE_ANGLE}°")
                self._move(self.CLOSE_ANGLE)

        threading.Thread(target=_do_close, daemon=True).start()

    def cleanup(self):
        """
        Release GPIO resources.
        Always call this when the application exits.
        """
        self._cancel_timer()
        if _GPIO_AVAILABLE:
            if self._pwm:
                self._move(self.CLOSE_ANGLE)    # ensure gate is closed
                self._pwm.stop()
            GPIO.cleanup()
            print("[SERVO] GPIO cleaned up")
        else:
            print("[SERVO] Simulation cleanup done")