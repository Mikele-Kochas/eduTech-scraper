from flask import Flask, jsonify, render_template, send_from_directory, Response, stream_with_context
import os
import json
from news_scraper import NewsScraper
import logging
import time
from queue import Queue, Empty

app = Flask(__name__)

# ===== Log streaming (SSE) =====
log_queue: Queue[str] = Queue(maxsize=1000)


class QueueLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            try:
                log_queue.put_nowait(msg)
            except Exception:
                # if full, drop oldest by getting once
                try:
                    _ = log_queue.get_nowait()
                except Exception:
                    pass
                try:
                    log_queue.put_nowait(msg)
                except Exception:
                    pass
        except Exception:
            pass


# attach handler to root logger
_root_logger = logging.getLogger()
_queue_handler = QueueLogHandler()
_queue_handler.setLevel(logging.INFO)
_queue_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
_root_logger.addHandler(_queue_handler)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/run', methods=['POST'])
def run_scrape():
    scraper = NewsScraper()
    # Config-driven scraping
    scraper.scrape_from_config()
    scraper.enrich_with_gemini()
    # Return JSON directly without writing to disk
    return jsonify(scraper.news_items)


@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


@app.route('/api/logs/stream')
def logs_stream():
    def event_stream():
        # send initial hello
        yield 'retry: 2000\n\n'
        while True:
            try:
                msg = log_queue.get(timeout=2.0)
                yield f'data: {msg}\n\n'
            except Empty:
                # keep-alive
                yield ': ping\n\n'
    return Response(stream_with_context(event_stream()), mimetype='text/event-stream')


if __name__ == '__main__':
    # Disable debugger/reloader to avoid restarts while Playwright loads
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False, use_reloader=False)


