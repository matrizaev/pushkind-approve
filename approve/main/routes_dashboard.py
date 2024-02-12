from flask import render_template
from flask_login import current_user, login_required

from approve.main.routes import bp
from approve.main.utils import role_required
from approve.models import User, UserRoles

################################################################################
# Dahboard page
################################################################################


@bp.route("/dashboard/", methods=["GET"])
@login_required
def show_dashboard_self():
    if current_user.role == UserRoles.admin:
        users = User.query.filter_by(hub_id=current_user.hub_id).all()
    else:
        users = [current_user]
    return render_template("dashboard.html", user=current_user, users=users)


@bp.route("/dashboard/<int:user_id>", methods=["GET", "POST"])
@login_required
@role_required([UserRoles.admin])
def show_dashboard_all(user_id):
    """
    Show the dashboard page
    """
    user = User.query.get_or_404(user_id)
    users = User.query.filter_by(hub_id=current_user.hub_id).all()
    return render_template("dashboard.html", user=user, users=users)