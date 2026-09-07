import os
import webbrowser
from threading import Timer

os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')

from app import create_app

app = create_app()

def open_browser():
    webbrowser.open("http://127.0.0.1:5000")

if __name__ == '__main__':
    # Only open browser once (if reloader is active, only open in the main reloaded process)
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        Timer(1.0, open_browser).start()
        
    app.run(host='127.0.0.1', port=5000, debug=True)
