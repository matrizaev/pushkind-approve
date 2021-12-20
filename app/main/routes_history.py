from app import db
from flask_login import current_user, login_required
from app.main import bp
from app.models import UserRoles, Order, OrderEvent, EventType
from flask import render_template, request
from app.main.utils import ecwid_required, role_forbidden
from datetime import datetime as dt
from app.utils import GetFilterTimestamps

'''
################################################################################
Responibility page
################################################################################
'''


@bp.route('/history/', methods=['GET', 'POST'])
@login_required
@role_forbidden([UserRoles.default])
@ecwid_required
def ShowHistory():
    dates = GetFilterTimestamps()
    filter_from = request.args.get('from', default=dates['recently'], type=int)
    dates['сегодня'] = dates.pop('daily')
    dates['неделя'] = dates.pop('weekly')
    dates['месяц'] = dates.pop('monthly')
    dates['квартал'] = dates.pop('quarterly')
    dates['год'] = dates.pop('annually')
    dates['недавно'] = dates.pop('recently')
    events = OrderEvent.query.filter(OrderEvent.timestamp > dt.fromtimestamp(filter_from))
    events = events.join(Order).filter_by(hub_id=current_user.hub_id).order_by(OrderEvent.timestamp.desc()).all()
    return render_template('history.html', events=events, EventType=EventType, filter_from=filter_from, dates=dates)
