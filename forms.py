from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, BooleanField, SelectField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Optional
from models import User

class LoginForm(FlaskForm):
    username = StringField('Username or Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(), 
        Length(min=3, max=20, message='Username must be between 3 and 20 characters')
    ])
    email = StringField('Email', validators=[DataRequired(), Email()])
    full_name = StringField('Full Name', validators=[
        DataRequired(),
        Length(min=2, max=100, message='Full name must be between 2 and 100 characters')
    ])
    phone_number = StringField('Phone Number', validators=[
        Optional(),
        Length(min=10, max=20, message='Phone number must be between 10 and 20 characters')
    ])
    location = StringField('Location', validators=[
        Optional(),
        Length(max=100, message='Location must be less than 100 characters')
    ])
    bio = TextAreaField('Bio', validators=[
        Optional(),
        Length(max=500, message='Bio must be less than 500 characters')
    ])
    profile_photo = FileField('Profile Photo', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')
    ])
    smtp_server = StringField('SMTP Server', validators=[Optional()])
    smtp_port = StringField('SMTP Port', validators=[Optional()])
    smtp_username = StringField('SMTP Username', validators=[Optional()])
    smtp_password = PasswordField('SMTP Password', validators=[Optional()])
    imap_server = StringField('IMAP Server', validators=[Optional()])
    imap_port = StringField('IMAP Port', validators=[Optional()])
    use_tls = BooleanField('Use TLS/SSL', default=True)
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(min=6, message='Password must be at least 6 characters long')
    ])
    password2 = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match')
    ])
    submit = SubmitField('Register')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Username already taken. Please choose a different one.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email already registered. Please choose a different one.')

class ProfileForm(FlaskForm):
    full_name = StringField('Full Name', validators=[
        DataRequired(),
        Length(min=2, max=100)
    ])
    phone_number = StringField('Phone Number', validators=[
        Optional(),
        Length(min=10, max=20)
    ])
    location = StringField('Location', validators=[
        Optional(),
        Length(max=100)
    ])
    bio = TextAreaField('Bio', validators=[
        Optional(),
        Length(max=500)
    ])
    profile_photo = FileField('Profile Photo', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')
    ])
    smtp_server = StringField('SMTP Server', validators=[Optional()])
    smtp_port = StringField('SMTP Port', validators=[Optional()])
    smtp_username = StringField('SMTP Username', validators=[Optional()])
    smtp_password = PasswordField('SMTP Password', validators=[Optional()])
    imap_server = StringField('IMAP Server', validators=[Optional()])
    imap_port = StringField('IMAP Port', validators=[Optional()])
    use_tls = BooleanField('Use TLS/SSL')
    submit = SubmitField('Update Profile')

class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[
        DataRequired(),
        Length(min=6, message='Password must be at least 6 characters long')
    ])
    new_password2 = PasswordField('Confirm New Password', validators=[
        DataRequired(),
        EqualTo('new_password', message='Passwords must match')
    ])
    submit = SubmitField('Change Password')

class AdminUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    full_name = StringField('Full Name', validators=[DataRequired()])
    active = BooleanField('Active')
    is_admin = BooleanField('Admin')
    is_verified = BooleanField('Verified')
    submit = SubmitField('Update User')

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    submit = SubmitField('Send Reset Link')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[
        DataRequired(),
        Length(min=6, message='Password must be at least 6 characters long')
    ])
    password2 = PasswordField('Confirm New Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match')
    ])
    submit = SubmitField('Reset Password')

class TwoFactorSetupForm(FlaskForm):
    code = StringField('Authenticator Code', validators=[
        DataRequired(),
        Length(min=6, max=6, message='Code must be exactly 6 digits')
    ])
    submit = SubmitField('Enable 2FA')

class TwoFactorVerifyForm(FlaskForm):
    code = StringField('Authentication Code', validators=[
        DataRequired(),
        Length(min=6, max=8, message='Enter your 6-digit code or 8-character backup code')
    ])
    submit = SubmitField('Verify')

class APITokenForm(FlaskForm):
    name = StringField('Token Name', validators=[
        DataRequired(),
        Length(min=1, max=100, message='Name must be between 1 and 100 characters')
    ])
    submit = SubmitField('Generate Token')
