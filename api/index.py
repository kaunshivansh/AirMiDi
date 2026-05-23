import os
from flask import Flask, render_template

# Get the absolute path to the directory containing this file
base_dir = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, 
            template_folder=os.path.join(base_dir, "../templates"),
            static_folder=os.path.join(base_dir, "../static"))

@app.route('/')
def home():
    return render_template('index.html')

# For local testing
if __name__ == '__main__':
    app.run(debug=True, port=5000)
