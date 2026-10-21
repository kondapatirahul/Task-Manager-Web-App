from flask import Blueprint, request, jsonify, session
from app import db
from app.models import Category

categories_bp = Blueprint('categories', __name__, url_prefix='/api/categories')

@categories_bp.route('', methods=['GET'])
def get_categories():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401
    cats = Category.query.filter_by(user_id=uid).all()
    return jsonify([{'id': c.id, 'name': c.name} for c in cats])

@categories_bp.route('', methods=['POST'])
def create_category():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    cat = Category(name=data['name'], user_id=uid)
    db.session.add(cat)
    db.session.commit()
    return jsonify({'id': cat.id, 'name': cat.name}), 201

@categories_bp.route('/<int:cat_id>', methods=['DELETE'])
def delete_category(cat_id):
    uid = session.get('user_id')
    cat = Category.query.filter_by(id=cat_id, user_id=uid).first_or_404()
    db.session.delete(cat)
    db.session.commit()
    return jsonify({'message': 'Deleted'})
