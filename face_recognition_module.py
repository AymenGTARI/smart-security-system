# face_recognition_module.py
import cv2
import face_recognition as fr
import os

# ---------------- INIT ----------------
known_face_encodings = []
known_face_names = []

dataset_path = "face_db"

for person_name in os.listdir(dataset_path):
    person_folder = os.path.join(dataset_path, person_name)

    if os.path.isdir(person_folder):
        for image_name in os.listdir(person_folder):
            image_path = os.path.join(person_folder, image_name)

            try:
                image = fr.load_image_file(image_path)
                encodings = fr.face_encodings(image)

                if len(encodings) > 0:
                    known_face_encodings.append(encodings[0])
                    known_face_names.append(person_name)
                    print(f"[OK] {person_name} -> {image_name}")

            except Exception as e:
                print(f"[ERREUR] {image_name}: {e}")

print(f"[INFO] Total visages chargés: {len(known_face_names)}")


# ---------------- FONCTION ----------------
def recognize_face(frame):
    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

    face_locations = fr.face_locations(rgb_small_frame)
    face_encodings = fr.face_encodings(rgb_small_frame, face_locations)

    name = "Aucun"

    if len(face_encodings) > 0:
        name = "Inconnu"

        for face_encoding in face_encodings:
            distances = fr.face_distance(known_face_encodings, face_encoding)

            if len(distances) > 0:
                best_match_index = distances.argmin()

                if distances[best_match_index] < 0.50:
                    name = known_face_names[best_match_index]
                    break

    # -------- Annotation --------
    for (top, right, bottom, left) in face_locations:
        top *= 4
        right *= 4
        bottom *= 4
        left *= 4

        color = (0, 255, 0) if name != "Inconnu" else (0, 0, 255)

        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.rectangle(frame, (left, bottom - 35), (right, bottom), color, cv2.FILLED)

        cv2.putText(frame, name, (left + 6, bottom - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    face_detected = len(face_locations) > 0
    return name, frame, face_detected