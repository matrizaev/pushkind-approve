from datetime import datetime, timezone

from flask import flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app import db
from app.main import bp
from app.main.forms import CreateOrderForm
from app.main.utils import GetNewOrderNumber, SendEmailNotification, role_required
from app.models import (
    Category,
    Order,
    OrderLimit,
    OrderStatus,
    Product,
    Project,
    Site,
    UserRoles,
    Vendor,
)


@bp.route("/shop/")
@login_required
@role_required([UserRoles.initiative, UserRoles.purchaser, UserRoles.admin])
def ShopCategories():
    projects = Project.query
    if current_user.role != UserRoles.admin:
        projects = projects.filter_by(enabled=True)
    projects = projects.filter_by(hub_id=current_user.hub_id)
    projects = projects.order_by(Project.name).all()
    limits = OrderLimit.query.filter_by(hub_id=current_user.hub_id).all()
    categories = Category.query.filter_by(hub_id=current_user.hub_id).all()
    return render_template(
        "shop_categories.html", projects=projects, limits=limits, categories=categories
    )


@bp.route("/shop/<int:cat_id>", defaults={"vendor_id": None})
@bp.route("/shop/<int:cat_id>/<int:vendor_id>")
@login_required
@role_required([UserRoles.initiative, UserRoles.purchaser, UserRoles.admin])
def ShopProducts(cat_id, vendor_id):
    category = Category.query.filter_by(id=cat_id, hub_id=current_user.hub_id).first()
    if category is None:
        return redirect(url_for("main.ShopCategories"))
    products = Product.query.filter_by(cat_id=cat_id)
    if vendor_id is not None:
        products = products.filter_by(vendor_id=vendor_id)
    products = products.join(Vendor).filter_by(enabled=True)
    products = products.order_by(Product.name).all()
    vendor_ids = {p.vendor_id for p in products}
    vendors = Vendor.query.filter(Vendor.id.in_(vendor_ids)).all()
    return render_template(
        "shop_products.html",
        category=category,
        vendors=vendors,
        products=products,
        vendor_id=vendor_id,
    )


@bp.route("/shop/cart", methods=["GET", "POST"])
@login_required
@role_required([UserRoles.initiative, UserRoles.purchaser, UserRoles.admin])
def ShopCart():
    form = CreateOrderForm()
    if form.submit.data:
        if form.validate_on_submit():
            products = Product.query.filter(
                Product.id.in_(p["product"] for p in form.cart.data)
            ).all()
            if len(products) == 0:
                flash("Заявка не может быть пуста.")
                return render_template("shop_cart.html", form=form)
            site = Site.query.filter_by(
                id=form.site_id.data, project_id=form.project_id.data
            ).first()
            if site is None:
                flash("Такой площадки не существует.")
                return redirect(url_for("main.ShopCart"))
            order_products = []
            order_vendors = []
            categories = []
            products = {p.id: p for p in products}
            for cart_item in form.cart.data:
                product = products[cart_item["product"]]
                if product is None:
                    continue
                categories.append(product.cat_id)
                order_vendors.append(product.vendor)
                order_product = {
                    "id": product.id,
                    "sku": product.sku,
                    "price": product.price,
                    "name": product.name,
                    "imageUrl": product.image,
                    "categoryId": product.cat_id,
                    "vendor": product.vendor.name,
                    "category": product.category.name,
                    "quantity": cart_item["quantity"],
                    "selectedOptions": [{"value": product.measurement}],
                }
                if cart_item["text"] is not None:
                    order_product["selectedOptions"].append(
                        {"value": cart_item["text"]}
                    )
                order_products.append(order_product)
            order_number = GetNewOrderNumber()
            now = datetime.now(tz=timezone.utc)
            categories = Category.query.filter(Category.id.in_(categories)).all()
            cashflow_id, income_id = max(
                (c.cashflow_id, c.income_id) for c in categories
            )
            order = Order(
                number=order_number,
                initiative_id=current_user.id,
                create_timestamp=int(now.timestamp()),
                site_id=site.id,
                hub_id=current_user.hub_id,
                products=order_products,
                vendors=list(set(order_vendors)),
                total=sum([p["quantity"] * p["price"] for p in order_products]),
                status=OrderStatus.new,
                cashflow_id=cashflow_id,
                income_id=income_id,
            )
            db.session.add(order)
            order.categories = categories
            db.session.commit()
            order.update_positions()
            flash("Заявка успешно создана.")
            SendEmailNotification("new", order)
            return redirect(url_for("main.ShowIndex"))
        else:
            flash("Что-то пошло не так.")
    return render_template("shop_cart.html", form=form)
