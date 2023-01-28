import datetime as dt
import functools
import os
from logging.config import dictConfig
from typing import Any, Dict, Tuple

from flask import Flask, Response, json, jsonify, request
from flask.wrappers import Response
from flask_cors import CORS
from flask_serialize import FlaskSerialize
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func


class TimestampConversionError(Exception):
    pass


AUTH_KEY = os.environ.get("AUTH_KEY", "secret")
DB_NAME = "database.db"
OP_MAP = {
    "avg": func.avg,
    "max": func.max,
    "min": func.min,
}

dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "[%(asctime)s] [%(process)d] [%(levelname)s] in %(module)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S %z",
            }
        },
        "handlers": {
            "wsgi": {
                "class": "logging.StreamHandler",
                "stream": "ext://flask.logging.wsgi_errors_stream",
                "formatter": "default",
            }
        },
        "root": {"level": "DEBUG", "handlers": ["wsgi"]},
    }
)

app = Flask(__name__)
CORS(app)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_NAME}"
db = SQLAlchemy(app)
fs_mixin = FlaskSerialize(db)


def get_query_params(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(params=request.args)

    return wrapper


def _db_create_all():
    if "database.db" not in os.listdir():
        db.create_all()


def auth(params) -> bool:
    return params.get("auth_key", None) == AUTH_KEY


def js_timestamp_to_python_dt(js_timestamp: str):
    timestamp = int(js_timestamp)
    return dt.datetime.utcfromtimestamp(timestamp / 1000)


def get_dates_from_params(params: Dict[str, Any]) -> Tuple[dt.datetime, dt.datetime]:
    """
    To be used in routes, gets start and end date from request params or default -> 1 day from request time
    """
    start = dt.datetime.utcnow() - dt.timedelta(days=1)
    end = dt.datetime.utcnow()

    if params.get("start"):
        start = js_timestamp_to_python_dt(params["start"])

    if params.get("end"):
        end = js_timestamp_to_python_dt(params["end"])

    return start, end


def get_dates_from_params(params: Dict[str, Any]) -> Tuple[dt.datetime, dt.datetime]:
    """
    To be used in routes, gets start and end date from request params or default -> 1 day from request time
    """
    start = dt.datetime.utcnow() - dt.timedelta(days=1)
    end = dt.datetime.utcnow()

    if params.get("start"):
        start = js_timestamp_to_python_dt(params["start"])

    if params.get("end"):
        end = js_timestamp_to_python_dt(params["end"])

    return start, end


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


#################################################################################################################


@app.after_request
def after_request_logging(response: Response):
    app.logger.debug(f"Response: {response}")
    app.logger.debug(f"Json: {response.json}")
    return response


@app.errorhandler(TimestampConversionError)
def handle_timestamp_error(e: Exception):
    return (
        jsonify(
            {
                "message": "Cant convert your paramter to python datetime. Please use utc timestamp in miliseconds for best results"
            }
        ),
        400,
    )


@app.route("/", methods=["GET"])
def home():
    return SensorData.query.order_by(SensorData.timestamp.desc()).first().fs_as_json


@app.route("/health", methods=["GET"])
def healthcheck():
    return jsonify({"status": "ok"})


@app.route("/data", methods=["GET"])
@get_query_params
def get_data(params: Dict[str, Any], *args, **kwargs):
    """
    By default without any query params return data from last 24h
    `start` and `end` should be passed as utc timestamps in miliseconds
    """
    start, end = get_dates_from_params(params)

    items = SensorData.query.filter(
        SensorData.timestamp >= start, SensorData.timestamp <= end
    )

    return SensorData.fs_json_list(items)


@app.route("/data/calculate", methods=["GET"])
@get_query_params
def get_data_average(params: Dict[str, Any], *args, **kwargs):
    start, end = get_dates_from_params(params)
    op_param = params.get("operation", None)

    if op_param not in OP_MAP.keys():
        return (
            jsonify(
                {
                    "message": "'operation' not found in query params. Supported operations: 'avg', 'min', 'max'"
                }
            ),
            400,
        )

    f = OP_MAP[op_param]

    result = (
        SensorData.query.filter(
            SensorData.timestamp >= start, SensorData.timestamp <= end
        )
        .with_entities(f(SensorData.temp))
        .scalar()
    )

    return jsonify({"result": result})


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
