from flask import jsonify

def api_success(data=None, message=None, status_code=200):
    payload = {'ok': True}
    if data is not None:
        payload['data'] = data
    if message:
        payload['message'] = message
    return jsonify(payload), status_code

def api_error(message, status_code=400):
    return jsonify({'ok': False, 'error': message}), status_code
