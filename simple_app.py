from flask import Flask, jsonify
import os

app = Flask(__name__)

@app.route('/')
def index():
    return 'PDF PayPal System - Test Application'

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

# Gunicorn用のアプリケーションオブジェクト
application = app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
