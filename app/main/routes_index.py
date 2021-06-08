from app import db
from flask_login import current_user, login_required
from app.main import bp
from app.models import UserRoles, OrderStatus, Project, OrderEvent, EventType, Order, Site, Category, OrderCategory
from flask import render_template, flash, request, redirect, url_for
from app.main.utils import ecwid_required, role_forbidden, role_required
from datetime import datetime, timedelta, timezone
from app.main.forms import MergeOrdersForm

'''
################################################################################
Index page
################################################################################
'''

def GetDateTimestamps():
	now = datetime.now(tz = timezone.utc)
	today = datetime(now.year, now.month, now.day)
	week = today - timedelta(days = today.weekday())
	month = datetime(now.year, now.month, 1)
	recently = today - timedelta(days = 42)
	dates = {'сегодня':int(today.timestamp()), 'неделя':int(week.timestamp()), 'месяц':int(month.timestamp()), 'недавно':int(recently.timestamp())}
	return dates

@bp.route('/')
@bp.route('/index/')
@login_required
@role_forbidden([UserRoles.default])
@ecwid_required
def ShowIndex():

	dates = GetDateTimestamps()
	filter_from = request.args.get('from', default = 0, type = int)
	filter_approval = request.args.get('approval', default = None, type = str)
	filter_project = request.args.get('project', default=None, type=int)
	filter_category = request.args.get('category', default=None, type=int)

	if filter_approval not in [status.name for status in OrderStatus]:
		filter_approval = None

	orders = Order.query

	if current_user.role == UserRoles.initiative:
		orders = orders.filter(Order.initiative_id == current_user.id)

	if filter_approval is not None:
		orders = orders.filter(Order.status == filter_approval)

	if filter_from > 0:
		orders = orders.filter(Order.create_timestamp > filter_from)

	if filter_category is not None or current_user.role in [UserRoles.purchaser, UserRoles.validator]:
		orders = orders.join(OrderCategory)
		if filter_category is not None:
			orders = orders.filter(OrderCategory.category_id == filter_category)
		if current_user.role in [UserRoles.purchaser, UserRoles.validator]:
			orders = orders.filter(OrderCategory.category_id.in_([cat.id for cat in current_user.categories]))

	if filter_project is not None or current_user.role in [UserRoles.purchaser, UserRoles.validator]:
		orders = orders.join(Site)
		if filter_project is not None:
			orders = orders.filter(Site.project_id == filter_project)
		if current_user.role in [UserRoles.purchaser, UserRoles.validator]:
			orders = orders.filter(Site.project_id.in_([p.id for p in current_user.projects]))

	orders = orders.order_by(Order.create_timestamp.desc()).all()
	projects = Project.query.filter_by(hub_id = current_user.hub.id).all()
	categories = Category.query.filter_by(hub_id = current_user.hub.id).all()
	form = MergeOrdersForm()
	return render_template('index.html',
							orders = orders, dates = dates, projects = projects,categories = categories,
							filter_from = filter_from,
							filter_approval = filter_approval,
							filter_project = filter_project,
							filter_category = filter_category,
							OrderStatus = OrderStatus,
							form = form)


@bp.route('/orders/merge/', methods=['POST'])
@login_required
@role_required([UserRoles.admin, UserRoles.initiative, UserRoles.purchaser])
@ecwid_required
def MergeOrders():
	form = MergeOrdersForm()
	if form.validate_on_submit():
		orders_list = form.orders.data
		if not isinstance(orders_list, list) or len(orders_list) < 2:	
			flash('Некорректный список заявок.')
			return redirect(url_for('main.ShowIndex'))
			
		orders = list()

		orders = Order.query.filter(Order.id.in_(orders_list), Order.hub_id == current_user.hub_id)
		if current_user.role == UserRoles.initiative:
			orders = orders.filter(Order.initiative_id == current_user.id)
			
		orders = orders.all()
		
		if len(orders) < 2:
			flash('Некорректный список заявок.')
			return redirect(url_for('main.ShowIndex'))
		
		for order in orders[1:]:
			if  order.site_id != orders[0].site_id or \
				order.income_statement != orders[0].income_statement or \
				order.cash_flow_statement != orders[0].cash_flow_statement:
					flash('Нельзя объединять заявки с разными объектами, БДДР или БДДС.')
					return redirect(url_for('main.ShowIndex'))
					
		products = dict()
		categories = list()
		for order in orders:
			categories += [cat.id for cat in order.categories]
			for product in order.products:
				if 'selectedOptions' in product and len(product['selectedOptions']) > 1:
					product_id = product['sku'] + ''.join(sorted([k['value'] for k in product['selectedOptions']]))
				else:
					product_id = product['sku']
				if product_id not in products:
					products[product_id] = dict()
					products[product_id]['sku'] = product['sku']
					products[product_id]['id'] = abs(hash(product_id))
					products[product_id]['name'] = product['name']
					products[product_id]['price'] = product['price']
					products[product_id]['quantity'] = product['quantity']
					if 'selectedOptions' in product:
						products[product_id]['selectedOptions'] = product['selectedOptions']
					products[product_id]['categoryId'] = product['categoryId']
					products[product_id]['imageUrl'] = product['imageUrl']
					if 'vendor' in product:
						products[product_id]['vendor'] = product['vendor']
				else:
					products[product_id]['quantity'] += product['quantity']
		order = Order()
		order.initiative = current_user
	
		now = datetime.now(tz = timezone.utc)
	
		order.products = [products[sku] for sku in products.keys()]
		order.total = sum([product['quantity']*product['price'] for product in order.products])
		order.income_statement = orders[0].income_statement
		order.cash_flow_statement = orders[0].cash_flow_statement
		order.site = orders[0].site
		order.status = OrderStatus.new
		order.create_timestamp = int(now.timestamp())
		
		order.id = now.strftime('_%y%j%H%M%S')
		order.hub_id = current_user.hub_id
		order.categories = Category.query.filter(Category.id.in_(categories), Category.hub_id == current_user.hub_id).all()
		
		db.session.add(order)
		
		message = 'Заявка объединена из заявок'
		
		for o in orders:
			message += ' <a href={}>{}</a>'.format(url_for('main.ShowOrder', order_id = o.id), o.id)
			message2 = 'Заявка объединена в заявку <a href={}>{}</a>'.format(url_for('main.ShowOrder', order_id = order.id), order.id)
			event = OrderEvent(user_id = current_user.id, order_id = o.id, type=EventType.duplicated, data=message2, timestamp = datetime.now(tz = timezone.utc))
			db.session.add(event)
			
		event = OrderEvent(user_id = current_user.id, order_id = order.id, type=EventType.duplicated, data=message, timestamp = datetime.now(tz = timezone.utc))
		db.session.add(event)
		
		db.session.commit()
		
		Order.UpdateOrdersPositions(current_user.hub_id)
		
		flash(f'Объединено заявок: {len(orders)}. Идентификатор новой заявки {order.id}')		

	else:
		for error in form.orders.errors:
			flash(error)
	return redirect(url_for('main.ShowIndex'))
