import os
from app import app
import ssl
import threading
import time
import schedule
from datetime import datetime
import pytz
import logging
from services.stock_service import get_top_gainers_losers

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Disable SSL verification warnings for development
import urllib3
urllib3.disable_warnings()

# Function to check if current time is during market hours (9:15 AM - 3:30 PM IST, weekdays)
def is_market_hours():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)

    # Check if it's a weekday (0 = Monday, 6 = Sunday)
    if now.weekday() >= 5:  # Saturday or Sunday
        return False

    # Check if time is between 9:15 AM and 3:30 PM
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

    return market_open <= now <= market_close

# Function to refresh top gainers and losers data
def refresh_top_gainers_losers():
    try:
        if is_market_hours():
            logger.info("Refreshing top gainers and losers data")
            get_top_gainers_losers()  # This will update the cache
            logger.info("Top gainers and losers data refreshed successfully")
        else:
            logger.info("Skipping top gainers/losers refresh - outside market hours")
    except Exception as e:
        logger.error(f"Error refreshing top gainers and losers: {str(e)}")

# Function to run the scheduler in a separate thread
def run_scheduler():
    # Schedule the job to run every 15 minutes
    schedule.every(15).minutes.do(refresh_top_gainers_losers)

    # Run the job once at startup to initialize data
    refresh_top_gainers_losers()

    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

if __name__ == "__main__":
    # Get port from environment variable or default to 5000
    port = int(os.environ.get("PORT", 5000))

    # Start the scheduler in a separate thread
    logger.info("Starting the scheduler for top gainers and losers data")
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("Scheduler thread started")

    # Use waitress on Windows to avoid WinError 10038 socket crashes
    if os.name == 'nt':
        try:
            from waitress import serve
            print(f" * Serving Flask app with Waitress on http://0.0.0.0:{port}")
            serve(app, host='0.0.0.0', port=port, threads=8, channel_timeout=300)
        except ImportError:
            print(" * waitress not installed, falling back to Flask dev server")
            app.run(host='0.0.0.0', port=port)
    else:
        # Check if SSL cert and key are provided
        cert_path = os.environ.get("SSL_CERT_PATH")
        key_path = os.environ.get("SSL_KEY_PATH")

        ssl_context = None
        if cert_path and key_path and os.path.exists(cert_path) and os.path.exists(key_path):
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(cert_path, key_path)

        print(f"Starting server on port {port}")
        if ssl_context:
            print("HTTPS enabled")

        app.run(
            host='0.0.0.0',
            port=port,
            ssl_context=ssl_context
        )
