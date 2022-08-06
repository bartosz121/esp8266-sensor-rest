import os
import pytz
from datetime import datetime
from flask import Flask, Response, request, json
from flask_sqlalchemy import SQLAlchemy
from flask_serialize import FlaskSerialize

# AUTH_KEY = os.environ["AUTH_KEY"]
AUTH_KEY = "secret"
DB_NAME = "database.db"
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_NAME}"
db = SQLAlchemy(app)
fs_mixin = FlaskSerialize(db)


def get_datetime_now_with_timezone() -> datetime:
    return datetime.now(pytz.timezone("Europe/Warsaw"))


def auth(params) -> bool:
    return params.get("auth_key", None) == AUTH_KEY


class SensorData(db.Model, fs_mixin):
    __fs_order_by_field_desc__ = "timestamp"

    id = db.Column(db.Integer, primary_key=True)
    temp = db.Column(db.Float, nullable=False)
    timestamp = db.Column(
        db.DateTime(timezone=True),
        default=get_datetime_now_with_timezone,
        nullable=False,
    )

    def __repr__(self):
        return f"<SensorData #{self.id}, {self.temp}, {self.timestamp.strftime('%Y/%m/%d %H:%M:%S')}>"

    def __fs_verify__(self, create=False):
        if not getattr(self, "temp", False):
            raise AttributeError("Missing temp value")
        return True


@app.route("/", methods=["GET"])
def home():
    last = SensorData.query.first()
    return SensorData.fs_json_get(last.id)


@app.route("/data", methods=["GET"])
def get_data():
    return SensorData.fs_get_delete_put_post()


@app.route("/upload", methods=["POST"])
def send_data():
    if auth(request.args):
        if request.headers.get("Content-Type") == "application/json":
            try:
                new_item = SensorData.fs_request_create_form()
            except AttributeError as e:
                post_error_msg = {"msg": f"Error: {str(e)}"}
                return Response(
                    json.dumps(post_error_msg), status=500, mimetype="application/json"
                )
            else:
                return new_item.fs_as_json

        wrong_content_type_msg = {"msg": "Content-type not supported. json only"}
        return Response(
            json.dumps(wrong_content_type_msg), status=400, mimetype="application/json"
        )

    unauthorized_msg = {"msg": "Unauthorized"}
    return Response(
        json.dumps(unauthorized_msg), status=401, mimetype="application/json"
    )
