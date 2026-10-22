from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectMultipleField, SubmitField
from wtforms.validators import DataRequired, Length, Regexp, EqualTo
from tmdb import GENRES

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3,max=40), Regexp(r'^[A-Za-z0-9_]+$', message='Use letters, numbers and underscores.')])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=10,max=128)])
    confirm = PasswordField('Confirm password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Create account')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(max=40)])
    password = PasswordField('Password', validators=[DataRequired(), Length(max=128)])
    submit = SubmitField('Sign in')

class PreferenceForm(FlaskForm):
    genres = SelectMultipleField('Favourite genres (Ctrl/Cmd + click to select several)', choices=[(str(k),v) for k,v in GENRES.items()])
    submit = SubmitField('Save preferences')
