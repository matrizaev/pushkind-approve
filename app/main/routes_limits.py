from flask_login import login_required, current_user
from flask import render_template, flash, redirect, url_for, request

from app import db
from app.main import bp
from app.models import UserRoles, OrderLimit, Project, CashflowStatement
from app.models import OrderLimitsIntervals
from app.main.utils import role_forbidden
from app.main.forms import AddLimitForm


@bp.route('/limits/', methods=['GET'])
@bp.route('/limits/show', methods=['GET'])
@login_required
@role_forbidden([UserRoles.default, UserRoles.vendor])
def ShowLimits():
    filter_from = request.args.get('from', default=None, type=int)
    try:
        filter_from = OrderLimitsIntervals(filter_from)
    except ValueError:
        filter_from = None

    projects = Project.query
    if current_user.role != UserRoles.admin:
        projects = projects.filter_by(enabled=True)
    projects = projects.filter_by(hub_id=current_user.hub_id)
    projects = projects.order_by(Project.name).all()

    cashflows = CashflowStatement.query.filter_by(hub_id=current_user.hub_id)
    cashflows = cashflows.order_by(CashflowStatement.name).all()

    form = AddLimitForm()
    form.project.choices = [(p.id, p.name) for p in projects]
    form.cashflow.choices = [(c.id, c.name) for c in cashflows]
    form.process()

    limits = OrderLimit.query.filter_by(hub_id=current_user.hub_id)
    if filter_from is not None:
        limits = limits.filter_by(interval=filter_from)
    limits = limits.all()

    return render_template(
        'limits.html',
        limits=limits,
        intervals=OrderLimitsIntervals,
        filter_from=filter_from,
        form=form
    )


@bp.route('/limits/add', methods=['POST'])
@login_required
@role_forbidden([UserRoles.default, UserRoles.vendor, UserRoles.supervisor])
def AddLimit():
    projects = Project.query
    if current_user.role != UserRoles.admin:
        projects = projects.filter_by(enabled=True)
    projects = projects.filter_by(hub_id=current_user.hub_id)
    projects = projects.all()

    cashflows = CashflowStatement.query.filter_by(hub_id=current_user.hub_id)
    cashflows = cashflows.order_by(CashflowStatement.name).all()

    form = AddLimitForm()
    form.project.choices = [(p.id, p.name) for p in projects]
    form.cashflow.choices = [(c.id, c.name) for c in cashflows]

    if form.validate_on_submit():
        limit = OrderLimit(
            hub_id = current_user.hub_id,
            value = form.value.data,
            interval = form.interval.data,
            cashflow_id = form.cashflow.data,
            project_id = form.project.data
        )
        db.session.add(limit)
        db.session.commit()
        flash('Лимит успешно добавлен.')
    else:
        for error in (
            form.interval.errors +
            form.value.errors +
            form.project.errors +
            form.cashflow.errors
        ):
            flash(error)
    OrderLimit.update_current(
        current_user.hub_id,
        form.project.data,
        form.cashflow.data
    )
    return redirect(url_for('main.ShowLimits'))


@bp.route('/limits/remove/<int:limit_id>', methods=['GET'])
@login_required
@role_forbidden([UserRoles.default, UserRoles.vendor, UserRoles.supervisor])
def RemoveLimit(limit_id):
    limit = OrderLimit.query.filter_by(hub_id=current_user.hub_id, id=limit_id).first()
    if limit is not None:
        db.session.delete(limit)
        db.session.commit()
        flash('Лимит успешно удалён.')
    else:
        flash('Лимит не найден.')
    return redirect(url_for('main.ShowLimits'))
