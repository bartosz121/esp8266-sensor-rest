import os
from flask import Flask, Response, request, json
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_serialize import FlaskSerialize
from sqlalchemy.sql import func

AUTH_KEY = os.environ.get("AUTH_KEY", "secret")
DB_NAME = "database.db"

app = Flask(__name__)
CORS(app)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_NAME}"
db = SQLAlchemy(app)
fs_mixin = FlaskSerialize(db)


def _db_create_all():
    if "database.db" not in os.listdir():
        db.create_all()


def auth(params) -> bool:
    return params.get("auth_key", None) == AUTH_KEY


class SensorData(db.Model, fs_mixin):
    __fs_order_by_field__ = "timestamp"

    id = db.Column(db.Integer, primary_key=True)
    temp = db.Column(db.Float, nullable=False)
    timestamp = db.Column(
        db.DateTime(timezone=True),
        default=func.utcnow,
        nullable=False,
    )

    def __repr__(self):
        return f"<SensorData #{self.id}, {self.temp}, {self.timestamp.strftime('%Y/%m/%d %H:%M:%S')}>"

    def __fs_verify__(self, create=False):
        if not getattr(self, "temp", None):
            raise AttributeError("Missing temp value")
        return True


@app.route("/", methods=["GET"])
def home():
    return SensorData.query.order_by(SensorData.timestamp.desc()).first().fs_as_json


@app.route("/data", methods=["GET"])
def get_data():
    return SensorData.fs_get_delete_put_post()


@app.route("/upload", methods=["POST"])
def sensor_data():
    if not auth(request.args):
        return Response(
            json.dumps({"msg": "Unauthorized"}), status=401, mimetype="application/json"
        )

    if request.headers.get("Content-Type") == "application/json":
        try:
            new_item = SensorData.fs_request_create_form()
        except AttributeError as e:
            return Response(
                json.dumps({"msg": f"Error: {str(e)}"}),
                status=500,
                mimetype="application/json",
            )
        else:
            return new_item.fs_as_json

    return Response(
        json.dumps({"msg": "Content-type not supported. json only"}),
        status=400,
        mimetype="application/json",
    )
