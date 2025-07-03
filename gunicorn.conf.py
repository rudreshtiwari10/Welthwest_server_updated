import os

port = int(os.environ.get("PORT", 5000))
bind = f"0.0.0.0:{port}"
workers = 4
threads = 2
timeout = 120
preload_app = True

# Access log - records incoming HTTP requests
accesslog = "-"

# Error log - records Gunicorn server errors
errorlog = "-"

# Whether to send Flask output to the error log
capture_output = True

# How verbose the Gunicorn error logs should be
loglevel = "info" 