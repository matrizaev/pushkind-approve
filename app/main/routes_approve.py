from app import db
from flask_login import current_user, login_required
from app.main import bp
from app.models import User, UserRoles, Ecwid, OrderComment, OrderApproval
from flask import render_template, redirect, url_for, flash, jsonify, current_app
from app.main.forms import OrderCommentsForm, OrderApprovalForm, ChangeQuantityForm
from datetime import datetime, timezone
from app.ecwid import EcwidAPIException
from app.email import SendEmail
from app.main.utils import DATE_TIME_FORMAT, role_required, ecwid_required, GetOrderStatus, GetProductApproval, role_required_ajax, ecwid_required_ajax

'''
################################################################################
Consts
################################################################################
'''
_DISALLOWED_ORDERS_ITEM_FIELDS = ['productId', 'id', 'categoryId']
_DISALLOWED_ORDERS_FIELDS = ['vendorOrderNumber', 'customerId', 'privateAdminNotes', 'externalFulfillment', 'createDate', 'externalOrderId']


'''
################################################################################
Approve page
################################################################################
'''

@bp.route('/order/<int:order_id>')
@login_required
@role_required([UserRoles.initiative, UserRoles.validator, UserRoles.approver, UserRoles.admin])
@ecwid_required
def ShowOrder(order_id):
	try:
		json = current_user.hub.EcwidGetStoreOrders(orderNumber = order_id)
		if 'items' not in json or len(json['items']) == 0:
			raise EcwidAPIException('Такой заявки не существует.')
		order = json['items'][0]
		order_email = order['email'].lower()
		owner = User.query.filter(User.email == order_email).first()
		if not owner:
			raise EcwidAPIException('Заявка не принадлежит ни одному из инициаторов.')
		if current_user.role == UserRoles.initiative:
			if order_email != current_user.email:
				raise EcwidAPIException('Вы не являетесь владельцем этой заявки.')
	except EcwidAPIException as e:
		flash('Ошибка API: {}'.format(e))
		return redirect(url_for('main.ShowIndex'))

	order['createDate'] = datetime.strptime(order['createDate'], DATE_TIME_FORMAT)
	order['updateDate'] = datetime.strptime(order['updateDate'], DATE_TIME_FORMAT)
	order['status'] = GetOrderStatus(order)
	if current_user.role in [UserRoles.validator, UserRoles.approver]:
		for product in order['items']:
			product['approval'] = GetProductApproval(order_id, product['id'], current_user.id)
		if current_user.role == UserRoles.approver:
			order['approval'] = not GetProductApproval(order_id, None, current_user.id)
			
	
	order['initiative'] = owner
	try:
		order['privateAdminNotes'] = datetime.strptime(order['privateAdminNotes'], DATE_TIME_FORMAT)
	except (ValueError, KeyError):
		order['privateAdminNotes'] = datetime.now()
	if len(order['orderComments']) > 50:
		order['orderComments'] = order['orderComments'][:50] + '...'
		
	for product in order['items']:
		try:
			dash = product['sku'].index('-')
		except ValueError:
			product['vendor'] = None
			continue
		store = Ecwid.query.filter(Ecwid.store_id == product['sku'][:dash]).first()
		if not store:
			product['vendor'] = None
			continue
		product['vendor'] = store.store_name
		
	comments = OrderComment.query.join(User).filter(OrderComment.order_id == order_id, User.ecwid_id == current_user.ecwid_id).all()
	user_comment = OrderComment.query.filter(OrderComment.order_id == order_id, OrderComment.user_id == current_user.id).first()
	approvals = OrderApproval.query.join(User).filter(OrderApproval.order_id == order_id, User.ecwid_id == current_user.ecwid_id).all()
	
	approval_form = OrderApprovalForm()
	quantity_form = ChangeQuantityForm()
	comment_form = OrderCommentsForm(comment = user_comment.comment if user_comment else None)
	
	return render_template('approve.html',
							order = order,
							comments = comments,
							approvals = approvals,
							comment_form = comment_form,
							approval_form = approval_form,
							quantity_form = quantity_form)


@bp.route('/comment/<int:order_id>', methods=['POST'])
@login_required
@role_required_ajax([UserRoles.initiative, UserRoles.validator, UserRoles.approver])
def SaveComment(order_id):
	flash_messages = ['Не удалось изменить комментарий.']
	status = False
	form = OrderCommentsForm()
	stripped = ''
	timestamp = datetime.now(tz = timezone.utc)
	if form.validate_on_submit():
		try:
			json = current_user.hub.EcwidGetStoreOrders(orderNumber = order_id)
			if 'items' not in json or len(json['items']) == 0:
				raise EcwidAPIException('Такой заявки не существует.')
			comment = OrderComment.query.filter(OrderComment.order_id == order_id, OrderComment.user_id == current_user.id).first()
			stripped = form.comment.data.strip() if form.comment.data else ''
			if len(stripped) == 0:
				if comment:
					db.session.delete(comment)
			else:
				if not comment:
					comment = OrderComment(user_id = current_user.id, order_id = order_id)
					db.session.add(comment)
				comment.comment = stripped
				comment.timestamp = timestamp
			status = True
			flash_messages = ['Комментарий успешно обновлён.']
			db.session.commit()
		except EcwidAPIException as e:
			flash_messages = ['Ошибка API: {}'.format(e)]
	return jsonify({'status':status, 'flash':flash_messages, 'comment':stripped, 'timestamp':timestamp.timestamp() * 1000})


@bp.route('/approval/<int:order_id>', methods=['POST'])
@login_required
@role_required([UserRoles.validator, UserRoles.approver])
def SaveApproval(order_id):
	form = OrderApprovalForm()
	if form.validate_on_submit():
		try:
			json = current_user.hub.EcwidGetStoreOrders(orderNumber = order_id)
			if 'items' not in json or len(json['items']) == 0:
				raise EcwidAPIException('Такой заявки не существует.')
			order_approval = OrderApproval.query.filter(OrderApproval.order_id == order_id, OrderApproval.user_id == current_user.id, OrderApproval.product_id == None).first()
			if not form.product_id.data:
				if current_user.role != UserRoles.approver:
					return render_template('errors/403.html'),403
				OrderApproval.query.filter(OrderApproval.order_id == order_id, OrderApproval.user_id == current_user.id).delete()
				if not order_approval:
					order_approval = OrderApproval(order_id = order_id, product_id = None, user_id = current_user.id)
					db.session.add(order_approval)
			else:
				product_approval = OrderApproval.query.filter(OrderApproval.order_id == order_id, OrderApproval.user_id == current_user.id, OrderApproval.product_id == form.product_id.data).first()
				if product_approval:
					db.session.delete(product_approval)
				else:
					if order_approval:
						db.session.delete(order_approval)
					product_approval = OrderApproval(order_id = order_id, product_id = form.product_id.data, user_id = current_user.id, product_sku = form.product_sku.data.strip())
					db.session.add(product_approval)
			db.session.commit()
		except EcwidAPIException as e:
			flash('Ошибка API: {}'.format(e))
	return redirect(url_for('main.ShowOrder', order_id = order_id))


@bp.route('/delete/<int:order_id>')
@login_required
@role_required([UserRoles.initiative])
@ecwid_required
def DeleteOrder(order_id):
	try:
		json = current_user.hub.EcwidGetStoreOrders(orderNumber = order_id)
		if 'items' not in json or len(json['items']) == 0:
			raise EcwidAPIException('Такой заявки не существует.')
		order = json['items'][0]
		if current_user.email != order['email'].lower():
			raise EcwidAPIException('Вы не являетесь владельцем этой заявки.')
		json = current_user.hub.EcwidDeleteStoreOrder(order_id = order_id)
		comments = OrderComment.query.join(User).filter(OrderComment.order_id == order_id, User.ecwid_id == current_user.ecwid_id).all()
		approvals = OrderApproval.query.join(User).filter(OrderApproval.order_id == order_id, User.ecwid_id == current_user.ecwid_id).all()
		for approval in approvals:
			db.session.delete(approval)
		for comment in comments:
			db.session.delete(comment)
		db.session.commit()
		flash('Заявка успешно удалена.')
	except EcwidAPIException as e:
		flash('Ошибка API: {}'.format(e))
	return redirect(url_for('main.ShowIndex'))
	
@bp.route('/duplicate/<int:order_id>')
@login_required
@role_required([UserRoles.initiative])
@ecwid_required
def DuplicateOrder(order_id):
	try:
		json = current_user.hub.EcwidGetStoreOrders(orderNumber = order_id)
		if 'items' not in json or len(json['items']) == 0:
			raise EcwidAPIException('Такой заявки не существует.')
		order = json['items'][0]
		if current_user.email != order['email'].lower():
			raise EcwidAPIException('Вы не являетесь владельцем этой заявки.')
		for key in _DISALLOWED_ORDERS_FIELDS:
			order.pop(key, None)
		for product in order['items']:
			for key in _DISALLOWED_ORDERS_ITEM_FIELDS:
				product.pop(key, None)
		json = current_user.hub.EcwidSetStoreOrder(order)
		if 'id' not in json:
			raise EcwidAPIException('Не удалось дулировать заявку.')
		flash('Заявка успешно дублирована с внутренним номером {}.'.format(json['id']))
	except EcwidAPIException as e:
		flash('Ошибка API: {}'.format(e))
	return redirect(url_for('main.ShowOrder', order_id = order_id))


@bp.route('/quantity/<int:order_id>', methods=['POST'])
@login_required
@role_required([UserRoles.initiative])
@ecwid_required
def SaveQuantity(order_id):
	new_total = ''
	form = ChangeQuantityForm()
	if form.validate_on_submit():
		try:
			json = current_user.hub.EcwidGetStoreOrders(orderNumber = order_id)
			if 'items' not in json or len(json['items']) == 0:
				raise EcwidAPIException('Такой заявки не существует.')
			order = json['items'][0]
			if current_user.email != order['email'].lower():
				raise EcwidAPIException('Вы не являетесь автором заявки.')
			for i, product in enumerate(order['items']):
				if form.product_id.data == product['id']:
					order['total'] += (form.product_quantity.data - product['quantity'])*product['price']
					if order['total'] < 0:
						order['total'] = 0
					new_total = '{:,.2f}'.format(order['total'])
					product['quantity'] = form.product_quantity.data
					index = i
					break
			else:
				index = None
				flash('Указанный товар не найден в заявке.')
			if index != None:
				approvals = OrderApproval.query.join(User).filter(OrderApproval.order_id == order_id, User.ecwid_id == current_user.ecwid_id).all()
				for approval in approvals:
					db.session.delete(approval)
				if form.product_quantity.data == 0:
					order['items'].pop(index)
				if len(order['items']) == 0:
					json = current_user.hub.EcwidDeleteStoreOrder(order_id = order_id)
					comments = OrderComment.query.join(User).filter(OrderComment.order_id == order_id, User.ecwid_id == current_user.ecwid_id).all()
					for comment in comments:
						db.session.delete(comment)
					flash('Заявка удалена, вернитесь на главную страницу.')
				else:
					json = current_user.hub.EcwidUpdateStoreOrder(order_id, order)
					message = 'Количество {} было изменено в заявке.'.format(product['sku'])
					flash(message)
					comment = OrderComment.query.filter(OrderComment.order_id == order_id, OrderComment.user_id == current_user.id).first()
					if not comment:
						comment = OrderComment(user_id = current_user.id, order_id = order_id)
						db.session.add(comment)
					comment.comment = message
				db.session.commit()
		except EcwidAPIException as e:
			flash('Ошибка API: {}'.format(e))
			db.session.rollback()
	else:
		for error in form.product_id.errors + form.product_quantity.errors:
			flash(error)
	return redirect(url_for('main.ShowOrder', order_id = order_id))

	
@bp.route('/process/<int:order_id>')
@login_required
@role_required([UserRoles.approver])
@ecwid_required
def ProcessHubOrder(order_id):

	try:
		json = current_user.hub.EcwidGetStoreOrders(orderNumber = order_id)
		if 'items' not in json or len(json['items']) == 0:
			raise EcwidAPIException('Такой заявки не существует.')
	except EcwidAPIException as e:
		flash('Ошибка API: {}'.format(e))
		return redirect(url_for('main.ShowIndex'))

	order = json['items'][0]
	
	for key in _DISALLOWED_ORDERS_FIELDS:
		order.pop(key, None)
	for product in order['items']:
		for key in _DISALLOWED_ORDERS_ITEM_FIELDS:
			product.pop(key, None)
			
	stores = Ecwid.query.filter(Ecwid.ecwid_id == current_user.ecwid_id).all()
	got_orders = {}
	for store in stores:
		products = list()
		total = 0
		for product in order['items']:
			try:
				dash = product['sku'].index('-')
			except ValueError:
				continue
			if product['sku'][:dash] == str(store.store_id):
				product_new = product.copy()
				product_new['sku'] = product_new['sku'][dash+1:]
				products.append(product_new)
				total += product_new['price'] * product_new['quantity']
		if len(products) == 0:
			continue
		items = order['items']
		order['items'] = products
		order['subtotal'] = total
		order['total'] = total
		order['email'] = current_user.email
		result = store.EcwidSetStoreOrder(order)
		if 'id' not in result:
			flash('Не удалось отправить заявку поставщику {}.'.format(store.store_id))
		else:
			try:
				profile = store.EcwidGetStoreProfile()
				got_orders[profile['account']['accountName']] = result['id']
			except:
				got_orders[store.store_id] = result['id']
		order['items'] = items

	if len(got_orders) > 0:
		vendor_str = ', '.join(f'{vendor}: #{order}' for vendor,order in got_orders.items())
		try:
			current_user.hub.EcwidUpdateStoreOrder(order_id, {'externalOrderId':vendor_str, 'externalFulfillment':True, 'privateAdminNotes': datetime.now(tz = timezone.utc).strftime(DATE_TIME_FORMAT)})
		except EcwidAPIException as e:
			flash('Ошибка API: {}'.format(e))
			flash('Не удалось сохранить информацию о передаче поставщикам.')
		flash('Заявка была отправлена поставщикам: {}.'.format(vendor_str))
	else:
		flash('Не удалось перезаказать данные товары у зарегистрованных поставщиков.')

	return redirect(url_for('main.ShowOrder', order_id = order_id))
	
	
@bp.route('/notify/<int:order_id>')
@login_required
@role_required_ajax([UserRoles.initiative])
@ecwid_required_ajax
def NotifyApprovers(order_id):
	try:
		json = current_user.hub.EcwidGetStoreOrders(orderNumber = order_id)
		if 'items' not in json or len(json['items']) == 0:
			raise EcwidAPIException('Такой заявки не существует.')
		order = json['items'][0]
		if current_user.email != order['email'].lower():
			raise EcwidAPIException('Вы не являетесь автором заявки.')
	except EcwidAPIException as e:
		flash('Ошибка API: {}'.format(e))
		return redirect(url_for('main.ShowIndex'))
	approvers = User.query.filter(User.role.in_([UserRoles.approver, UserRoles.validator]), User.ecwid_id == current_user.ecwid_id).all()
	SendEmail('Уведомление о заявке #{}.'.format(order['vendorOrderNumber']),
			   sender=current_app.config['MAIL_USERNAME'],
			   recipients=[approver.email for approver in approvers],
			   text_body=render_template('email/notify.txt', order=order),
			   html_body=render_template('email/notify.html', order=order))
	flash('Уведомление успешно выслано')
	return redirect(url_for('main.ShowOrder', order_id = order_id))