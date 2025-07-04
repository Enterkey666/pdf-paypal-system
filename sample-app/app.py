from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def index():
    return 'PDF PayPal System - Test Application'

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
