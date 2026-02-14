from app import app
import os
import logging

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
    Run the Flask server with proper error handling.
    Uses waitress on Windows to avoid WinError 10038 socket crashes.
    """
    try:
        logger.info(f"Starting Stock Market Data API on http://{host}:{port}")
        logger.info(f"Debug mode: {'ON' if debug else 'OFF'}")
        logger.info("Press CTRL+C to stop the server")

        # Use waitress on Windows to avoid WinError 10038
        if os.name == 'nt' and not debug:
            try:
                from waitress import serve
                logger.info("Using Waitress WSGI server (Windows)")
                serve(app, host=host, port=port, threads=8, channel_timeout=300)
                return
            except ImportError:
                logger.warning("waitress not installed, falling back to werkzeug")

        # Fallback: werkzeug dev server
        from werkzeug.serving import run_simple
        run_simple(
            hostname=host,
            port=port,
            application=app,
            use_reloader=debug,
            use_debugger=debug,
            threaded=True
        )
    except OSError as e:
        if hasattr(e, 'winerror') and e.winerror == 10048:
            logger.error(f"Port {port} is already in use. Please try a different port.")
        elif hasattr(e, 'winerror') and e.winerror == 10038:
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
