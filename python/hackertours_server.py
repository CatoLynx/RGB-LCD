from flask import Flask, request, render_template_string
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import check_password_hash

from local_secrets import HT_USERS

app = Flask(__name__)
auth = HTTPBasicAuth()

@auth.verify_password
def verify_password(username, password):
    if username in HT_USERS and \
            check_password_hash(HT_USERS.get(username), password):
        return username

filename = "/tmp/hackertours.txt"

# HTML template for the webpage
html = """
<!doctype html>
<html>
    <head>
        <title>Hackertours Schedule</title>
    </head>
    <body>
        <form method="POST">
            <textarea name="content" rows="30" cols="50">{{ content }}</textarea><br>
            <input type="submit" value="Save">
        </form>
    </body>
</html>
"""

@app.route('/ht-schedule', methods=['GET', 'POST'])
@auth.login_required
def index():
    content = ''
    if request.method == 'POST':
        # Update the file with the contents of the textbox
        content = request.form['content']
        with open(filename, 'w') as file:
            file.write(content)
    else:
        # Load the content of the file into the textbox
        try:
            with open(filename, 'r') as file:
                content = file.read()
        except FileNotFoundError:
            pass

    return render_template_string(html, content=content)

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0')
