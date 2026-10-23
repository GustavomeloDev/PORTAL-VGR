from flask import Blueprint, jsonify, redirect, url_for

core_bp = Blueprint(
    'core',
    __name__,
    static_folder='static',
    url_prefix='/core',
)

@core_bp.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

@core_bp.route('/', methods=['GET'])
def index():
    return redirect(url_for('login.view_login'))
