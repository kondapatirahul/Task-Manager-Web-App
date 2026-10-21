from flask import Blueprint, request
from flask_login import current_user, login_required
from app import db
from app.models import Category, Task
from app.routes.utils import api_success, api_error

categories_bp = Blueprint('categories', __name__, url_prefix='/api/categories')

@categories_bp.route('', methods=['GET'])
@login_required
def get_categories():
    categories = Category.query.filter_by(user_id=current_user.id).order_by(Category.name.asc()).all()
    return api_success([c.to_dict() for c in categories])

@categories_bp.route('', methods=['POST'])
@login_required
def create_category():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return api_error('Category name is required.', 400)

    if len(name) > 50:
        return api_error('Category name must be 50 characters or less.', 400)

    # Check for duplicate category name for this user
    existing = Category.query.filter_by(user_id=current_user.id, name=name).first()
    if existing:
        return api_error('A category with this name already exists.', 409)

    category = Category(name=name, user_id=current_user.id)
    db.session.add(category)
    db.session.commit()
    return api_success(category.to_dict(), message='Category created successfully', status_code=201)

@categories_bp.route('/<int:cat_id>', methods=['DELETE'])
@login_required
def delete_category(cat_id):
    category = Category.query.filter_by(id=cat_id, user_id=current_user.id).first()
    if not category:
        return api_error('Category not found.', 404)

    # Safe deletion: update associated tasks so their category_id is set to None
    Task.query.filter_by(category_id=category.id, user_id=current_user.id).update(
        {Task.category_id: None},
        synchronize_session='fetch'
    )

    db.session.delete(category)
    db.session.commit()
    return api_success(message='Category deleted and associated tasks unassigned successfully')
