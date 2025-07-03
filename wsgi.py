from app import app
import os
from flask import jsonify

# Add a root route for Render's health check
@app.route('/', methods=['GET', 'HEAD'])
def root():
    """
    Root endpoint for Render's health check
    Returns a simple JSON response
    """
    return jsonify({"status": "healthy", "message": "Indian Stock Market API is running"}), 200

# Make sure the app binds to the correct port and host
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

# For gunicorn
application = app 