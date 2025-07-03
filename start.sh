#!/bin/bash
export PORT=5000
gunicorn wsgi:application --bind 0.0.0.0:5000 