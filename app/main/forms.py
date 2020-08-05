from flask_wtf import FlaskForm
from wtforms import SubmitField, IntegerField, StringField, SelectField, TextAreaField, FormField, Form
from wtforms.validators import DataRequired, Length
from app.models import UserRoles

class EcwidSettingsForm(FlaskForm):
	partners_key  = StringField('Ключ partners_key', [DataRequired()])
	client_id     = StringField('Ключ client_id', [DataRequired()])
	client_secret = StringField('Ключ client_secret', [DataRequired()])
	store_id      = IntegerField('ID магазина', [DataRequired()])
	submit1       = SubmitField('Сохранить')

class UserSettings(Form):
	full_name  = StringField('Имя', [DataRequired()])
	phone = StringField('Телефон', [DataRequired()])
	location = StringField('Расположение', [DataRequired()])

class UserRolesForm(FlaskForm):
	user_id = SelectField('Идентификатор пользователя', coerce = int)
	role = SelectField('Роль', coerce = int,
						choices = [
							(int(UserRoles.default), str(UserRoles.default)),
							(int(UserRoles.initiative), str(UserRoles.initiative)),
							(int(UserRoles.validator), str(UserRoles.validator)),
							(int(UserRoles.approver), str(UserRoles.approver)),
							(int(UserRoles.admin), str(UserRoles.admin)),
						])
	about_user = FormField(UserSettings, [DataRequired()])
	submit2 = SubmitField('Сохранить')
	
class UserSettingsForm(FlaskForm):
	about_user = FormField(UserSettings, [DataRequired()])
	submit3 = SubmitField('Сохранить')
	
class OrderCommentsForm(FlaskForm):
	comment  = TextAreaField('Комментарий', [Length(max = 128)])
	submit = SubmitField('Сохранить')
	
class OrderApprovalForm(FlaskForm):
	product_id    = IntegerField('Идентификатор товара')
	product_sku   = StringField('Артикул товара', [DataRequired()])
	submit = SubmitField('Сохранить')