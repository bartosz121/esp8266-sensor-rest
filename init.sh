#!/bin/bash

python -c 'from main import _db_create_all;_db_create_all()'

gunicorn -c gunicorn_config.py