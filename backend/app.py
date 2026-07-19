import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS

load_dotenv(Path(__file__).resolve().parent / '.env')

app = Flask(__name__)
cors_origins = [
    origin.strip()
    for origin in os.getenv('CORS_ALLOWED_ORIGINS', '*').split(',')
    if origin.strip()
]
CORS(app, origins=cors_origins)

from routes.auth import auth_bp
from routes.documents import documents_bp
from routes.health import health_bp
from routes.incidents import incidents_bp

app.register_blueprint(auth_bp, url_prefix='/api')
app.register_blueprint(documents_bp, url_prefix='/api')
app.register_blueprint(health_bp, url_prefix='/api')
app.register_blueprint(incidents_bp, url_prefix='/api')

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG') == '1', host='0.0.0.0', port=5000)
