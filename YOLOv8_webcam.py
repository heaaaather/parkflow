from ultralytics import YOLO
import cv2
import math
import easyocr
import time
import os
from flask import send_file
import torch

# Directory to save ROI text
ROI_DIR = './static/roi/'
os.makedirs(ROI_DIR, exist_ok=True)

def preprocess_image(img):
    # Convert image to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Apply Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Perform adaptive thresholding to binarize the image
    _, thresholded = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    return thresholded

# Define a directory to save the images
IMAGE_DIR = './static/images/'
os.makedirs(IMAGE_DIR, exist_ok=True)

def save_image(image, filename):
    filepath = os.path.join(IMAGE_DIR, filename)
    cv2.imwrite(filepath, image)

def object_detection():
    cap = cv2.VideoCapture(1)
    model = YOLO('../models/CustomLPR.pt')
    reader = easyocr.Reader(['en'])  # Initialize EasyOCR with English language support

    crop_interval = 2  # Interval in seconds before cropping the next image
    last_crop_time = time.time()  # Initialize the last crop time
    detected_plates = set()  # Set to store detected plates
    image_count = 0

    while True:
        success, img = cap.read()

        current_time = time.time()

        if current_time - last_crop_time >= crop_interval:
            last_crop_time = current_time  # Update the last crop time

            results = model(img, stream=True)

            for r in results:
                boxes = r.boxes

                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0]
                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

                    # Extract license plate region
                    license_plate = img[y1:y2, x1:x2]

                    # Hash the cropped plate for comparison
                    plate_hash = hash(license_plate.tostring())

                    # Check if the plate is new
                    if plate_hash not in detected_plates:
                        detected_plates.add(plate_hash)  # Add the plate hash to set
                        # Preprocess license plate image
                        processed_plate = preprocess_image(license_plate)

                        # Save original and processed images
                        save_image(license_plate, f'original_image_{image_count}.jpg')
                        save_image(processed_plate, f'processed_image_{image_count}.jpg')
                        image_count += 1

                        # Perform text extraction using EasyOCR on the preprocessed plate
                        extracted_text = reader.readtext(processed_plate)

                        # Display extracted text
                        if extracted_text:
                            text = extracted_text[0][1]  # Assuming only one text is extracted
                            # Remove spaces and capitalize letters
                            text = text.replace(" ", "").upper()
                        else:
                            text = "No text detected"

                        print("Extracted Text:", text)

                        # Save extracted text to a file
                        with open(os.path.join(ROI_DIR, 'roi_text.txt'), 'w') as roi_file:
                            roi_file.write(text)

        ret, frame = cv2.imencode('.jpg', img)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame.tobytes() + b'\r\n')