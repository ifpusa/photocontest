from flask import Flask

app = Flask(__name__)

from app.blueprints.photovote import bp 

app.register_blueprint(bp, url_prefix='/contest')