from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectMultipleField, SubmitField, BooleanField, HiddenField, RadioField, TextAreaField
from wtforms.validators import DataRequired, Length, Regexp, EqualTo
from tmdb import GENRES


def normalize_username(value):
    return value.strip().lower() if isinstance(value, str) else value


class RegisterForm(FlaskForm):
    next_url = HiddenField()
    username = StringField('Username', filters=[normalize_username], validators=[
        DataRequired(message='Choose a username.'),
        Length(min=3, max=40, message='Use 3–40 characters for your username.'),
        Regexp(r'^[a-z0-9_]+$', message='Use letters, numbers and underscores only.'),
    ])
    password = PasswordField('Password', validators=[
        DataRequired(message='Enter a password.'),
        Length(min=10, max=128, message='Use a password with 10–128 characters.'),
    ])
    confirm = PasswordField('Confirm password', validators=[
        DataRequired(message='Re-enter your password.'),
        EqualTo('password', message='Your passwords do not match.'),
    ])
    submit = SubmitField('Create account')


class LoginForm(FlaskForm):
    next_url = HiddenField()
    username = StringField('Username', filters=[normalize_username], validators=[
        DataRequired(message='Enter your CineCompass username.'),
        Length(max=40, message='Username must be at most 40 characters.'),
        Regexp(r'^[a-z0-9_]+$', message='Enter your username using letters, numbers and underscores.'),
    ])
    password = PasswordField('Password', validators=[
        DataRequired(message='Enter your password.'),
        Length(max=128, message='Password must be at most 128 characters.'),
    ])
    remember = BooleanField('Keep me signed in on this device')
    submit = SubmitField('Sign in')


class PreferenceForm(FlaskForm):
    genres = SelectMultipleField('Favourite genres (Ctrl/Cmd + click to select several)', choices=[(str(k), v) for k, v in GENRES.items()])
    submit = SubmitField('Save preferences')


class MovieReviewForm(FlaskForm):
    # Integer coercion plus choice validation rejects fractional/out-of-range stars.
    rating = RadioField('Your rating', coerce=int, choices=[(n, str(n)) for n in range(1,6)],
                        validators=[DataRequired(message='Choose a rating from 1 to 5 stars.')])
    body = TextAreaField('Your review (optional)', filters=[lambda value: value.strip() if value else ''],
                         validators=[Length(max=3000, message='Keep your review within 3,000 characters.')])
    submit = SubmitField('Publish rating & review')
