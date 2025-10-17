from flask import Flask, jsonify, render_template, send_from_directory, Response, stream_with_context, request
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
    try:
        data = request.json or {}
        api_key = data.get('api_key', '').strip()
        
        # Ustaw klucz API z UI, lub użyj z .env
        if api_key:
            os.environ['GOOGLE_API_KEY'] = api_key
            logger.info("Using API key from UI")
        
        scraper = NewsScraper()
        # Config-driven scraping
        scraper.scrape_from_config()
        scraper.enrich_with_gemini()
        scraper.save_to_json()
        return jsonify(scraper.news_items)
    except Exception as e:
        logger.error(f"Scrape error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/export', methods=['POST'])
def export_to_txt():
    """Export current news items to TXT format and download"""
    try:
        data = request.json or []
        if not data:
            return jsonify({'error': 'Brak danych do exportu'}), 400
        
        # Format: Title | Date | Original Content | AI Content | Link
        txt_content = "EXPORT AKTUALNOŚCI\n"
        txt_content += "=" * 80 + "\n\n"
        
        for idx, item in enumerate(data, 1):
            txt_content += f"{idx}. {item.get('tytuł', 'Brak tytułu')}\n"
            txt_content += f"   Data: {item.get('data', '—')}\n"
            txt_content += f"   Link: {item.get('link', '—')}\n"
            txt_content += f"\n   Treść (AI):\n   {item.get('gemini_tresc', item.get('treść', '—')).replace(chr(10), chr(10) + '   ')}\n"
            txt_content += "\n" + "-" * 80 + "\n\n"
        
        # Create filename with date
        from datetime import datetime as dt
        filename = f"aktualnosci_{dt.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        return Response(
            txt_content,
            mimetype='text/plain',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return jsonify({'error': 'Błąd podczas exportu'}), 500


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


