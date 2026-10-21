from flask import Blueprint, request, jsonify, g
from app import db
from app.models import Category
from app.routes.auth import login_required

categories_bp = Blueprint('categories', __name__, url_prefix='/api/categories')

@categories_bp.route('', methods=['GET'])
@login_required
def get_categories():
    uid = g.current_user.id
    cats = Category.query.filter_by(user_id=uid).all()
    return jsonify([{'id': c.id, 'name': c.name} for c in cats])

@categories_bp.route('', methods=['POST'])
@login_required
def create_category():
    uid = g.current_user.id
    if not request.is_json:
        return jsonify({'error': 'Content-Type must be application/json'}), 415
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required'}), 400

    name = data.get('name')
    if not isinstance(name, str) or not name.strip() or len(name) > 50:
        return jsonify({'error': 'Name must be between 1 and 50 characters'}), 400

    cat = Category(name=name, user_id=uid)
    db.session.add(cat)
    db.session.commit()
    return jsonify({'id': cat.id, 'name': cat.name}), 201

@categories_bp.route('/<int:cat_id>', methods=['DELETE'])
@login_required
def delete_category(cat_id):
    uid = g.current_user.id
    cat = Category.query.filter_by(id=cat_id, user_id=uid).first_or_404()
    db.session.delete(cat)
    db.session.commit()
    return jsonify({'message': 'Deleted'})
