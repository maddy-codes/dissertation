from werkzeug.utils import secure_filename
import os
import secrets


def calculate_variance_percentage(val1, val2):
    base_value = val2
    if val2 == 0:
        base_value = 1
    percentage = (abs(val1) - abs(val2)) / abs(base_value)
    return percentage * 100


def save_systematic_output(name, lines):
    with open(f"{name.strip()}.txt", "a+") as f:
        counter = 1
        for i in lines:
            f.write(str(counter) + ". ")
            f.write(i)
            f.write("\n")
            f.write("\n")
            counter += 1


def save_uploaded_file(file, upload_folder: str) -> str:
    """Save uploaded file to the specified folder."""
    filename = secure_filename(secrets.token_urlsafe(16) + "_" + file.filename)
    file_path = os.path.join(upload_folder, filename)
    file.save(file_path)
    return file_path
