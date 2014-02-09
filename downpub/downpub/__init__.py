#!/usr/bin/env python
# -*- coding: utf-8 -*-

from flask import Flask, render_template, g, session, request
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.babel import Babel, gettext
from config import LANGUAGES
from flask.ext.script import Manager
from flask.ext.migrate import Migrate, MigrateCommand


downpub = Flask(__name__)
downpub.config.from_object('config')

db = SQLAlchemy(downpub)
babel = Babel(downpub)

migrate = Migrate(downpub, db)

manager = Manager(downpub)
manager.add_command('db', MigrateCommand)


@babel.localeselector
def get_locale():
    """
    Initialize locales
    """
    return request.accept_languages.best_match(list(LANGUAGES.keys()))

from downpub.users.models import User


@downpub.before_request
def before_request():
    """
    pull user's profile from the database before every request are treated
    """
    g.user = None
    if 'user_id' in session:
        g.user = User.query.get(session['user_id'])


@downpub.errorhandler(404)
def not_found(error):
    return render_template('404.html', user=g.user), 404


@downpub.route('/')
def index():
    return render_template("index.html", user=g.user)


from downpub.users.views import mod as usersModule
from downpub.books.views import mod as booksModule
downpub.register_blueprint(usersModule)
downpub.register_blueprint(booksModule)
