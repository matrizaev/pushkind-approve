import enum
import json
from time import time
from datetime import datetime, timezone
from json.decoder import JSONDecodeError
from hashlib import md5

import jwt
from flask import current_app
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.sql import func
from sqlalchemy.types import TypeDecorator
from sqlalchemy.sql import expression

from app import db
from app import login
from app.utils import get_filter_timestamps


class EventType(enum.IntEnum):
    commented = 0
    approved = 1
    disapproved = 2
    quantity = 3
    duplicated = 4
    purchased = 5
    exported = 6
    merged = 7
    dealdone = 8
    income_statement = 9
    cashflow_statement = 10
    site = 11
    measurement = 12
    splitted = 13
    project = 14
    notification = 15

    def __str__(self):
        pretty = [
            'комментарий',
            'согласование',
            'замечание',
            'изменение',
            'клонирование',
            'отправлено поставщику',
            'экспорт в 1С',
            'объединение',
            'законтрактовано',
            'изменение',
            'изменение',
            'изменение',
            'изменение',
            'разделение',
            'изменение',
            'уведомление'
        ]
        return pretty[self.value]

    def color(self):
        colors = [
            'warning',
            'success',
            'danger',
            'primary',
            'dark',
            'dark',
            'dark',
            'dark',
            'dark',
            'primary',
            'primary',
            'primary',
            'primary',
            'dark',
            'primary',
            'dark'
        ]
        return colors[self.value]


class UserRoles(enum.IntEnum):
    default = 0
    admin = 1
    initiative = 2
    validator = 3
    purchaser = 4
    supervisor = 5
    vendor = 6

    def __str__(self):
        pretty = [
            'Без роли',
            'Администратор',
            'Инициатор',
            'Валидатор',
            'Закупщик',
            'Наблюдатель',
            'Поставщик'
        ]
        return pretty[self.value]


class OrderStatus(enum.IntEnum):
    new = 0
    not_approved = 1
    partly_approved = 2
    approved = 3
    modified = 4
    cancelled = 5

    def __str__(self):
        pretty = [
            'Новая',
            'Отклонена',
            'В работе',
            'Согласована',
            'Исправлена',
            'Отменена'
        ]
        return pretty[self.value]

    def color(self):
        colors = [
            'white',
            'danger',
            'warning',
            'success',
            'secondary',
            'secondary'
        ]
        return colors[self.value]


@login.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class Vendor(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    hub_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(128), nullable=False)
    enabled = db.Column(        
        db.Boolean,
        nullable=False,
        default=True,
        server_default=expression.true()
    )
    hub = db.relationship('Vendor')
    positions = db.relationship('Position', backref='hub')
    categories = db.relationship('Category', backref='hub')
    settings = db.relationship('AppSettings', backref='hub')
    projects = db.relationship('Project', backref='hub')
    orders = db.relationship('Order', backref='hub')


class JsonType(TypeDecorator):
    impl = db.String()

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
        return None

    def process_result_value(self, value, dialect):
        try:
            result = json.loads(value)
            return result
        except (JSONDecodeError, TypeError):
            return None


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    email = db.Column(db.String(128), index=True, unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    role = db.Column(
        db.Enum(UserRoles),
        index=True,
        nullable=False,
        default=UserRoles.default,
        server_default='default'
    )
    name = db.Column(db.String(128), nullable=True)
    phone = db.Column(db.String(128), nullable=True)
    position_id = db.Column(
        db.Integer,
        db.ForeignKey('position.id', ondelete='SET NULL'),
        nullable=True
    )
    location = db.Column(db.String(128), nullable=True)
    hub_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=True)
    email_new = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=expression.true()
    )
    email_modified = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=expression.true()
    )
    email_disapproved = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=expression.true()
    )
    email_approved = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=expression.true()
    )
    email_comment = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=expression.true()
    )
    last_seen = db.Column(db.DateTime, nullable=True)
    note = db.Column(db.String(), nullable=True)
    registered = db.Column(db.DateTime, nullable=True)
    birthday = db.Column(db.Date, nullable=True)
    categories = db.relationship('Category', secondary='user_category', backref='users')
    projects = db.relationship('Project', secondary='user_project', backref='users')
    events = db.relationship('OrderEvent', cascade='all, delete-orphan', backref='user')
    approvals = db.relationship(
        'OrderApproval',
        cascade='all, delete-orphan',
        backref='user', lazy='dynamic'
    )
    orders = db.relationship('Order', backref='initiative')
    hub = db.relationship('Vendor', foreign_keys=[hub_id])

    @property
    def projects_list(self):
        return [p.id for p in self.projects]

    @property
    def categories_list(self):
        return [c.id for c in self.categories]

    def __hash__(self):
        return self.id

    def __eq__(self, another):
        return isinstance(another, User) and self.id == another.id

    def __repr__(self):
        return json.dumps(self.to_dict())

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def get_avatar(self, size):
        digest = md5(self.email.lower().encode('utf-8')).hexdigest()
        return f'https://www.gravatar.com/avatar/{digest}?d=identicon&s={size}'

    def to_dict(self):
        data = {'id': self.id,
                'email': self.email,
                'phone': self.phone if self.phone is not None else '',
                'note': self.note,
                'birthday': self.birthday.isoformat() if self.birthday is not None else '',
                'role': self.role.name,
                'role_id': int(self.role),
                'position': self.position.name if self.position is not None else '',
                'name': self.name if self.name is not None else '',
                'hub_id': self.hub_id,
                'location': self.location if self.location is not None else '',
                'email_new': self.email_new,
                'email_modified': self.email_modified,
                'email_disapproved': self.email_disapproved,
                'email_approved': self.email_approved,
                'email_comment': self.email_comment,
                'projects': self.projects_list,
                'categories': self.categories_list}
        return data

    def get_jwt_token(self, expires_in=600):
        return jwt.encode(
            {
                'user_id': self.id,
                'exp': time() + expires_in
            },
            current_app.config['SECRET_KEY'],
            algorithm='HS256'
        )

    @staticmethod
    def verify_jwt_token(token):
        try:
            user_id = jwt.decode(
                token,
                current_app.config['SECRET_KEY'],
                algorithms=['HS256']
            )['user_id']
        except:
            return None
        return User.query.get(user_id)


class Position(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    name = db.Column(db.String(128), nullable=False, index=True)
    hub_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=False)
    users = db.relationship('User', backref='position')
    approvals = db.relationship('OrderPosition', cascade='all, delete-orphan', backref='position')


class OrderApproval(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, index=True, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    remark = db.Column(db.String(128), nullable=True)

    def __bool__(self):
        return self.product_id is None


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    name = db.Column(db.String(128), nullable=False, index=True)
    children = db.Column(JsonType(), nullable=False)
    hub_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=False)
    responsible = db.Column(db.String(128), nullable=True)
    functional_budget = db.Column(db.String(128), nullable=True)
    income_id = db.Column(  # БДР
        db.Integer,
        db.ForeignKey('income_statement.id', ondelete='SET NULL'),
        nullable=True
    )
    cashflow_id = db.Column(  # БДДС
        db.Integer,
        db.ForeignKey('cashflow_statement.id', ondelete='SET NULL'),
        nullable=True
    )
    code = db.Column(db.String(128), nullable=True)
    image = db.Column(db.String(128), nullable=True)
    income_statement = db.relationship('IncomeStatement')
    cashflow_statement = db.relationship('CashflowStatement')

    def __repr__(self):
        return json.dumps(self.to_dict())

    def to_dict(self):
        data = {
            'id': self.id,
            'name': self.name,
            'children': self.children,
            'responsible': self.responsible,
            'functional_budget': self.responsible,
            'income_id': self.income_id,
            'cashflow_id': self.cashflow_id,
            'code': self.code
        }
        return data

    def __hash__(self):
        return self.id

    def __eq__(self, another):
        return isinstance(another, Category) and self.id == another.id


class AppSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    hub_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=False, unique=True)
    notify_1C = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=expression.true()
    )
    email_1C = db.Column(db.String(128), nullable=True)
    order_id_bias = db.Column(db.Integer, nullable=False, default=0, server_default='0')


class OrderEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.now(tz=timezone.utc),
        server_default=func.datetime('now')
    )
    type = db.Column(db.Enum(EventType), nullable=False, default=EventType.commented)
    data = db.Column(db.String(), nullable=True)


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    name = db.Column(db.String(128), nullable=False, index=True)
    hub_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=False)
    sites = db.relationship('Site', cascade='all, delete-orphan', backref='project')
    enabled = db.Column(db.Boolean, nullable=False, default=True,
                        server_default=expression.true(), index=True)
    uid = db.Column(db.String(128), nullable=True)

    def __repr__(self):
        return json.dumps(self.to_dict())

    def to_dict(self):
        data = {
            'id': self.id,
            'name': self.name,
            'uid': self.uid,
            'enabled': self.enabled,
            'sites': [site.to_dict() for site in self.sites]
        }
        return data


class Site(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    name = db.Column(db.String(128), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    orders = db.relationship('Order', backref='site')
    uid = db.Column(db.String(128), nullable=True)

    def to_dict(self):
        data = {
            'id': self.id,
            'project_id': self.project_id,
            'name': self.name,
            'uid': self.uid
        }
        return data


OrderRelationship = db.Table(
    'order_relationship',
    db.Model.metadata,
    db.Column('order_id', db.Integer, db.ForeignKey('order.id'), primary_key=True),
    db.Column('child_id', db.Integer, db.ForeignKey('order.id'), primary_key=True)
)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    number = db.Column(db.String(128), nullable=False)
    initiative_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    create_timestamp = db.Column(db.Integer, nullable=False)
    products = db.Column(JsonType(), nullable=False)
    total = db.Column(db.Float, nullable=False)
    status = db.Column(
        db.Enum(OrderStatus),
        nullable=False,
        default=OrderStatus.new,
        server_default='new'
    )
    site_id = db.Column(db.Integer, db.ForeignKey('site.id', ondelete='SET NULL'), nullable=True)
    income_id = db.Column(  # БДР
        db.Integer,
        db.ForeignKey('income_statement.id', ondelete='SET NULL'),
        nullable=True
    )
    cashflow_id = db.Column(  # БДДС
        db.Integer,
        db.ForeignKey('cashflow_statement.id', ondelete='SET NULL'),
        nullable=True
    )
    hub_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=False)
    purchased = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=expression.false()
    )
    exported = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=expression.false()
    )
    dealdone = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=expression.false()
    )
    over_limit = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=expression.false()
    )
    dealdone_responsible_name = db.Column(db.String(128))
    dealdone_responsible_comment = db.Column(db.String(128))
    categories = db.relationship('Category', secondary='order_category')
    vendors = db.relationship('Vendor', secondary='order_vendor')
    events = db.relationship('OrderEvent', cascade='all, delete-orphan', backref='order')
    positions = db.relationship('Position', secondary='order_position')
    approvals = db.relationship('OrderPosition', backref='order')
    user_approvals = db.relationship('OrderApproval', backref='order')
    children = db.relationship(
        'Order',
        secondary=OrderRelationship,
        primaryjoin=id == OrderRelationship.c.order_id,
        secondaryjoin=id == OrderRelationship.c.child_id
    )
    parents = db.relationship(
        'Order',
        secondary=OrderRelationship,
        primaryjoin=id == OrderRelationship.c.child_id,
        secondaryjoin=id == OrderRelationship.c.order_id
    )
    income_statement = db.relationship('IncomeStatement')
    cashflow_statement = db.relationship('CashflowStatement')

    def UpdateOrderStatus(self):
        if self.site is None or self.site.project.enabled is False:
            return
        approved = [p.approved for p in self.approvals]
        if all(approved):
            self.status = OrderStatus.approved
            return
        disapproved = (
            OrderApproval.query
            .filter(
                OrderApproval.order_id == self.id,
                OrderApproval.product_id != None
            )
            .all()
        )
        if len(disapproved) > 0:
            self.status = OrderStatus.not_approved
            return
        self.status = OrderStatus.partly_approved
        return

    @property
    def categories_list(self):
        return [c.id for c in self.categories]

    def validators(self, position_id=None):
        if self.site is None or len(self.categories) == 0:
            return []
        validators = (
            User.query
            .filter_by(role=UserRoles.validator)
            .join(UserCategory)
            .filter(UserCategory.category_id.in_(self.categories_list))
            .join(UserProject)
            .filter(UserProject.project_id == self.site.project_id)
            .join(Position).join(OrderPosition)
            .filter_by(order_id=self.id)
        )
        if position_id is not None:
            validators = validators.filter_by(position_id=position_id)
        return validators.all()

    @property
    def purchasers(self):
        if self.site is None or len(self.categories) == 0:
            return []
        purchasers = (
            User.query
            .filter_by(role=UserRoles.purchaser)
            .join(UserCategory)
            .filter(UserCategory.category_id.in_(self.categories_list))
            .join(UserProject)
            .filter(UserProject.project_id == self.site.project_id)
        )
        return purchasers.all()

    @property
    def reviewers(self):
        result = User.query.filter_by(id=self.initiative_id).all()
        if self.site is None or len(self.categories) == 0:
            return result
        result += self.validators() + self.purchasers
        return result

    @classmethod
    def UpdateOrdersPositions(cls, hub_id, order_id=None, update_status=False):

        # Query orders from the hub
        orders = Order.query.filter(Order.hub_id == hub_id, Order.status != OrderStatus.approved)
        # Filter by order_id if specified
        if order_id is not None:
            orders = orders.filter_by(id=order_id)

        for order in orders.all():
            # Orders with no site and categories binding have no responsible positions
            if order.site is None or len(order.categories) == 0:
                continue
            # Query positions which have validators with the same project
            # and categories bindings as the order
            # Update the order's responsible positions
            order.positions = (
                Position.query
                .filter_by(hub_id=hub_id)
                .join(User).filter(User.role == UserRoles.validator)
                .join(UserCategory, User.id == UserCategory.user_id)
                .filter(UserCategory.category_id.in_(order.categories_list))
                .join(UserProject, User.id == UserProject.user_id)
                .filter(UserProject.project_id == order.site.project_id)
                .all()
            )

            # Update those which have users approved the order

            for position in order.approvals:
                approval = (
                    OrderApproval.query
                    .filter(OrderApproval.order_id == order.id, OrderApproval.product_id == None)
                    .join(User)
                    .filter(User.position_id == position.position_id)
                    .first()
                )
                if approval is not None:
                    position.approved = True
                    position.user = approval.user
                else:
                    position.approved = False
                    position.user = None
            if update_status is True:
                order.UpdateOrderStatus()
        db.session.commit()

    @property
    def create_date(self):
        return datetime.fromtimestamp(self.create_timestamp, tz=timezone.utc)

    @create_date.setter
    def create_date(self, dt):
        self.create_timestamp = int(dt.timestamp())


class OrderCategory(db.Model):
    __tablename__ = 'order_category'
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), primary_key=True)


class OrderVendor(db.Model):
    __tablename__ = 'order_vendor'
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), primary_key=True)


class OrderPosition(db.Model):
    __tablename__ = 'order_position'
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), primary_key=True)
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'), primary_key=True)
    approved = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=expression.false()
    )
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    timestamp = db.Column(db.DateTime, nullable=True)
    user = db.relationship('User')


class UserCategory(db.Model):
    __tablename__ = 'user_category'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), primary_key=True)


class UserProject(db.Model):
    __tablename__ = 'user_project'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), primary_key=True)


class IncomeStatement(db.Model):
    __tablename__ = 'income_statement'
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    name = db.Column(db.String(128), nullable=False, index=True)
    hub_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=False)

    def __repr__(self):
        return json.dumps(self.to_dict())

    def to_dict(self):
        data = {'id': self.id, 'name': self.name}
        return data


class CashflowStatement(db.Model):
    __tablename__ = 'cashflow_statement'
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    name = db.Column(db.String(128), nullable=False, index=True)
    hub_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=False)

    def __repr__(self):
        return json.dumps(self.to_dict())

    def to_dict(self):
        data = {'id': self.id, 'name': self.name}
        return data


class OrderLimitsIntervals(enum.IntEnum):
    daily = 0
    weekly = 1
    monthly = 2
    quarterly = 3
    annually = 4
    all_time = 5

    def __str__(self):
        pretty = [
            'День',
            'Неделя',
            'Месяц',
            'Квартал',
            'Год',
            'Всё время'
        ]
        return pretty[self.value]


class OrderLimit(db.Model):
    __tablename__ = 'order_limit'
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    hub_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=False)
    value = db.Column(db.Float, nullable=False, default=0.0, server_default='0.0')
    current = db.Column(db.Float, nullable=False, default=0.0, server_default='0.0')
    cashflow_id = db.Column(
        db.Integer,
        db.ForeignKey('cashflow_statement.id', ondelete='CASCADE'),
        nullable=False
    )
    project_id = db.Column(
        db.Integer,
        db.ForeignKey('project.id', ondelete='CASCADE'),
        nullable=False
    )
    interval = db.Column(
        db.Enum(OrderLimitsIntervals),
        index=True,
        nullable=False,
        default=OrderLimitsIntervals.monthly,
        server_default='monthly'
    )
    cashflow_statement = db.relationship('CashflowStatement')
    project = db.relationship('Project')

    @classmethod
    def update_current(cls, hub_id, project_id=None, cashflow_id=None):
        limits = OrderLimit.query.filter_by(hub_id=hub_id)

        if project_id is not None and cashflow_id is not None:
            limits = limits.filter_by(
                project_id=project_id,
                cashflow_id=cashflow_id
            )

        limits = limits.all()

        filters = get_filter_timestamps()
        for limit in limits:
            orders = Order.query

            if limit.interval == OrderLimitsIntervals.daily:
                orders = orders.filter(Order.create_timestamp > filters['daily'])
            elif limit.interval == OrderLimitsIntervals.weekly:
                orders = orders.filter(Order.create_timestamp > filters['weekly'])
            elif limit.interval == OrderLimitsIntervals.monthly:
                orders = orders.filter(Order.create_timestamp > filters['monthly'])
            elif limit.interval == OrderLimitsIntervals.quarterly:
                orders = orders.filter(Order.create_timestamp > filters['quarterly'])
            elif limit.interval == OrderLimitsIntervals.annually:
                orders = orders.filter(Order.create_timestamp > filters['annually'])

            orders = orders.filter(Order.cashflow_id == limit.cashflow_id)
            orders = orders.join(Site)
            orders = orders.filter(Site.project_id == limit.project_id).all()
            limit.current = sum(
                o.total for o in orders if o.status == OrderStatus.approved
            )
            if limit.current > 0.95 * limit.value:
                for order in orders:
                    order.over_limit = order.status != OrderStatus.approved

        db.session.commit()


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=False)
    name = db.Column(db.String(128), nullable=False, index=True)
    sku = db.Column(db.String(128), nullable=False, index=True)
    price = db.Column(db.Float, nullable=False)
    image = db.Column(db.String(128), nullable=True)
    measurement = db.Column(db.String(128), nullable=True)
    cat_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    description = db.Column(db.String(), nullable=True)
    input_required =  db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=expression.false()
    )
    vendor = db.relationship('Vendor', backref='products')
    category = db.relationship('Category')
