from flask_login import current_user, login_required
from flask import render_template

from app.main import bp
from app.models import UserRoles, Project, Category, User, UserProject, UserCategory
from app.main.utils import role_forbidden


################################################################################
# Responibility page
################################################################################


@bp.route('/help/', methods=['GET', 'POST'])
@login_required
@role_forbidden([UserRoles.default, UserRoles.vendor])
def ShowHelp():
    project_responsibility = {}
    projects = Project.query.filter_by(hub_id=current_user.hub_id).join(UserProject)
    projects = projects.join(User).filter_by(role=UserRoles.validator).order_by(Project.name).all()

    for project in projects:
        project_responsibility[project.name] = {'users': project.users, 'positions': set()}
        for user in project.users:
            position = user.position.name if user.position else 'не указана'
            project_responsibility[project.name]['positions'].add(position)

    category_responsibility = {}
    categories = Category.query.filter_by(hub_id=current_user.hub_id).join(UserCategory)
    categories = categories.join(User).filter_by(role=UserRoles.validator).order_by(Category.name)
    categories = categories.all()

    for category in categories:
        category_responsibility[category.name] = {'users': category.users, 'positions': set()}
        for user in category.users:
            position = user.position.name if user.position else 'не указана'
            category_responsibility[category.name]['positions'].add(position)

    return render_template(
        'help.html',
        projects=project_responsibility,
        categories=category_responsibility
    )
