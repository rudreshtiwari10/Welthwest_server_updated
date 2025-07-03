import os
from app import app
import ssl
from werkzeug.serving import WSGIRequestHandler

# Disable SSL verification warnings for development
import urllib3
urllib3.disable_warnings()

# Custom request handler to suppress binary logging
class CustomRequestHandler(WSGIRequestHandler):
    def log_request(self, code='-', size='-'):
        # Only log if response code indicates an error (4xx or 5xx)
        if isinstance(code, str):
            code = 500
        if code >= 400:
            return super().log_request(code, size)
    
    def log(self, format, *args):
        # Suppress binary logging
        try:
            super().log(format, *args)
        except UnicodeEncodeError:
            pass

if __name__ == "__main__":
    # Get port from environment variable or default to 5000
    port = int(os.environ.get("PORT", 5000))
    
    # Check if SSL cert and key are provided
    cert_path = os.environ.get("SSL_CERT_PATH")
    key_path = os.environ.get("SSL_KEY_PATH")
    
    ssl_context = None
    if cert_path and key_path and os.path.exists(cert_path) and os.path.exists(key_path):
        # Use provided SSL certificate
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(cert_path, key_path)
    else:
        # Use adhoc certificates for development
        try:
            from werkzeug.serving import make_ssl_devcert
            cert_file, key_file = make_ssl_devcert('ssl-cert', host='localhost')
            ssl_context = (cert_file, key_file)
        except ImportError:
            print("Warning: SSL dependencies not installed. Running in HTTP mode.")
            print("To enable HTTPS, install with: pip install pyOpenSSL")
    
    print(f"Starting server on port {port}")
    if ssl_context:
        print("HTTPS enabled")
    else:
        print("Running in HTTP mode")
    
    # Run the app with custom request handler
    app.run(
        host='0.0.0.0',
        port=port,
        ssl_context=ssl_context,
        request_handler=CustomRequestHandler
    ) 