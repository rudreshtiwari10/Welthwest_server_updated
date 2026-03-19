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


# Start news intelligence pipeline scheduler in master process (runs once)
def when_ready(server):
    import threading
    import time
    import schedule
    import logging

    logger = logging.getLogger('news_pipeline')

    def run_news_pipeline():
        try:
            from app import mongo
            from services.news_intelligence import NewsIntelligence
            pipeline = NewsIntelligence(mongo.db)
            results = pipeline.run_pipeline(max_articles=10)
            logger.info(f"Pipeline complete: {results.get('published', 0)} published, {results.get('failed', 0)} failed")
        except Exception as e:
            logger.error(f"News pipeline error: {e}")

    def scheduler_loop():
        schedule.every(30).minutes.do(run_news_pipeline)
        time.sleep(120)  # Wait 2 min before first run
        run_news_pipeline()
        while True:
            schedule.run_pending()
            time.sleep(60)

    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()
    logger.info("News pipeline scheduler started") 