from app import app
import os

# Make app variable available for gunicorn
application = app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    debug = app.config.get('DEBUG', False)
    print(f"Starting Stock Market Data API on port {port}")
    print(f"Debug mode: {'ON' if debug else 'OFF'}")
    print("Press CTRL+C to stop the server")
    app.run(host='0.0.0.0', port=port, debug=debug) 