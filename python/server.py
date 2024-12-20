from flask import Flask, request, render_template
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

import os
import pathlib
import time
import traceback

from PIL import Image

from local_secrets import USERS


app = Flask(__name__)
auth = HTTPBasicAuth()


@auth.verify_password
def verify_password(username, password):
    if username in USERS and \
            check_password_hash(USERS.get(username), password):
        return username


@app.route("/ht-schedule", methods=["GET", "POST"])
@auth.login_required
def ht_schedule():
    ht_filename = "/tmp/hackertours.txt"
    content = ""
    if request.method == "POST":
        # Update the file with the contents of the textbox
        content = request.form['content']
        with open(ht_filename, 'w') as file:
            file.write(content)
    else:
        # Load the content of the file into the textbox
        try:
            with open(ht_filename, 'r') as file:
                content = file.read()
        except FileNotFoundError:
            pass
    return render_template("ht_schedule.html", content=content)


@app.route("/img-upload", methods=["GET", "POST"])
def img_upload():
    message = ""
    image = None
    pending_path = pathlib.Path("/tmp/img_upload/pending")
    pending_path.mkdir(parents=True, exist_ok=True)
    if request.method == "POST":
        file = request.files['image']
        try:
            img = Image.open(file.stream)
            img = img.convert("1")
            img.thumbnail((264, 64))
            result = Image.new("1", (264, 64), "black")
            result.paste(img)
            filename = time.strftime("%Y-%m-%d_%H-%M-%S_") + secure_filename(file.filename)
            new_path = (pending_path/filename).with_suffix(".png").resolve()
            if pending_path in new_path.parents:
                result.save(new_path.as_posix())
                image = new_path.name
            img.close()
            result.close()
        except:
            traceback.print_exc()
            message = "Invalid image!"
        else:
            message = "Upload successful!"
    return render_template("img_upload.html", message=message, image=image)


@app.route("/img-review", methods=["GET", "POST"])
@auth.login_required
def img_review():
    pending_path = pathlib.Path("/tmp/img_upload/pending")
    approved_path = pathlib.Path("/tmp/img_upload/approved")
    pending_path.mkdir(parents=True, exist_ok=True)
    approved_path.mkdir(parents=True, exist_ok=True)
    if request.method == "POST":
        action = request.form['action']
        filename = request.form['filename']
        full_path = (pending_path/filename).resolve()
        if pending_path in full_path.parents:
            if action == 'Approve':
                new_path = (approved_path/filename).resolve()
                os.rename(full_path.as_posix(), new_path.as_posix())
            elif action == 'Reject':
                os.remove(full_path.as_posix())
    files = os.listdir(pending_path.as_posix())
    images = [{'filename': name} for name in files]
    return render_template("img_review.html", images=images)


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0')
