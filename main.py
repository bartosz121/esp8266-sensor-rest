import functools
import os
import datetime as dt
from typing import Dict, Any, Tuple
from flask import Flask, Response, request, json, abort, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_serialize import FlaskSerialize
from sqlalchemy.sql import func

AUTH_KEY = os.environ.get("AUTH_KEY", "secret")
DB_NAME = "database.db"
OP_MAP = {
    "avg": func.avg,
    "max": func.max,
    "min": func.min,
}

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


def raise_http_exception_on_except(code=404, error_msg: str = None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
            except Exception as e:
                nonlocal error_msg  # grab error msg from outer scope FIXME
                if not error_msg:
                    error_msg = f"Error: {str(e)}"
                response = jsonify({"message": error_msg})
                response.status_code = code
                abort(response)
            else:
                return result

        return wrapper

    return decorator


def _db_create_all():
    if "database.db" not in os.listdir():
        db.create_all()


def auth(params) -> bool:
    return params.get("auth_key", None) == AUTH_KEY


@raise_http_exception_on_except(
    code=400,
    error_msg="Cant convert your paramter to python datetime. "
    + "Please use utc timestamp in miliseconds for best results",
)
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
        response = jsonify(
            {
                "message": "'operation' not found in query params. Supported operations: 'avg', 'min', 'max'"
            }
        )
        response.status_code = 400
        abort(response)

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
