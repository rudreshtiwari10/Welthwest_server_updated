from app import app
import os
import logging
from werkzeug.serving import run_simple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Make app variable available for gunicorn
application = app

def run_server(host='127.0.0.1', port=8000, debug=False):
    """
    Run the Flask server with proper error handling
    """
    try:
        logger.info(f"Starting Stock Market Data API on http://{host}:{port}")
        logger.info(f"Debug mode: {'ON' if debug else 'OFF'}")
        logger.info("Press CTRL+C to stop the server")
        
        # Use run_simple instead of app.run for better Windows compatibility
        run_simple(
            hostname=host,
            port=port,
            application=app,
            use_reloader=debug,
            use_debugger=debug,
            threaded=True
        )
    except OSError as e:
        if e.winerror == 10048:  # Port already in use
            logger.error(f"Port {port} is already in use. Please try a different port.")
        elif e.winerror == 10038:  # Socket error
            logger.error("Socket error occurred. Please restart the server.")
        else:
            logger.error(f"OS Error: {str(e)}")
    except KeyboardInterrupt:
        logger.info("Server shutting down...")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    debug = app.config.get('DEBUG', False)
    
    # Use localhost instead of 0.0.0.0 for Windows
    host = '127.0.0.1' if os.name == 'nt' else '0.0.0.0'
    
    run_server(host=host, port=port, debug=debug) 