from flask import Flask, render_template

app = Flask(__name__,
            template_folder='../react-app/build',
            static_folder='../react-app/build',
            static_url_path='')

@app.route("/")
def index():
    return render_template("index.html")

app.run(debug=True)
