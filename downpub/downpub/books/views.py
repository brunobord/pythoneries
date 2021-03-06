# -*- coding: utf-8 -*-
#!/usr/bin/env python3

# Import the subprocess module to launch/communicate with the pandoc tool
import subprocess
import os
import sys
import io
import locale
from datetime import datetime

from flask import Blueprint, request, render_template, \
    flash, g, session, redirect, url_for, send_from_directory, send_file
from flask.ext.babel import gettext, Babel
from werkzeug.utils import secure_filename

from downpub import downpub, db, babel, get_locale
from downpub.books.forms import AddForm, AddCoverForm, EditForm, \
    AddPartForm, EditPartForm
from downpub.books.models import Book, Part
from downpub.books.decorators import requires_login
from downpub.users.models import User

from config import *

mod = Blueprint('books', __name__, url_prefix='/books')


def generate_xml_metadata(book_id):
    pass


@mod.before_request
def before_request():
    """
    pull user's profile from the database before every request are treated
    pull book from book_id if it's set
    """
    g.user = None
    g.user_id = None
    if 'user_id' in session:
        g.user = User.query.get(session['user_id'])
        if not g.user is None:
            g.user_id = session['user_id']
            g.locale = g.user.locale


@mod.route('/list/')
@requires_login
def list():
    """
    List the books the actual user created
    """

    site_title = gettext("Your Books, %(user_name)s !",
        user_name=g.user.name)

    books = Book.query.filter_by(user_id=session['user_id'])\
            .order_by(Book.modified_at.desc()).all()
    return render_template("books/list.html",
        books=books, user=g.user, site_title=site_title)


@mod.route('/add/', methods=['GET', 'POST'])
@requires_login
def add():
    """
    Add the book
    """
    site_title = gettext('Add a book')

    form = AddForm(request.form)

    if not form.validate_on_submit():
        # form initializing when we first show the edit page
        form.language.data = get_locale()

    if form.validate_on_submit():

        title = form.title.data
        subtitle = form.subtitle.data
        editor = form.editor.data
        publisher = form.publisher.data
        displayed_name = form.displayed_name.data
        style = form.style.data
        language = form.language.data
        rights = form.rights.data

        # create an user instance not yet stored in the database
        book = Book(title=title, subtitle=subtitle,
            user_id=session['user_id'],
            cover=None, creation_date=None, style=style,
            editor=editor, publisher=publisher,
            language=language, rights=rights,
            displayed_name=displayed_name, modified_at=None)

        # Insert the record in our database and commit it
        db.session.add(book)
        db.session.commit()

        # flash will display a message to the user
        flash(gettext('That book has been created !'))
        # redirect user to the list of books
        return redirect(url_for('books.list'))

    return render_template("books/add.html",
        form=form, user=g.user, site_title=site_title)


@mod.route('/<book_id>/edit/', methods=['GET', 'POST'])
@requires_login
def edit(book_id):
    """
    Edit the book with book_id
    """

    form = EditForm(request.form)
    book = Book.query.get(book_id)

    # if the current user isn't the author of that book, we redirect to homepage
    if book.user_id != g.user_id:
        flash(gettext("This isn't yours !"))
        return redirect(url_for('books.list'))

    book_title = (book.title[:25] + '...') if len(book.title) > 25 else book.title
    site_title = gettext('Edit the book %(book_title)s',
        book_title=book_title)

    if not form.validate_on_submit():
        # form initializing when we first show the edit page
        form.title.data = book.title
        form.subtitle.data = book.subtitle
        form.editor.data = book.editor
        form.publisher.data = book.publisher
        form.displayed_name.data = book.displayed_name
        form.style.data = book.style
        if book.language is None:
            form.language.data = get_locale()
        else:
            form.language.data = book.language
        form.rights.data = book.rights

    if form.validate_on_submit():
        # get an user instance not yet stored in the database
        book = Book.query.get(book_id)

        # set the new values
        book.title = form.title.data
        book.subtitle = form.subtitle.data
        book.editor = form.editor.data
        book.publisher = form.publisher.data
        book.style = form.style.data
        book.displayed_name = form.displayed_name.data
        book.modified_at = datetime.utcnow()
        book.language = form.language.data
        book.rights = form.rights.data

        # commit
        db.session.commit()

        # flash will display a message to the user
        flash(gettext('That book has been edited !'))

        # redirect user to the list of books
        return redirect(url_for('books.list'))

    return render_template("books/edit.html",
        form=form, book=book, user=g.user, site_title=site_title)


@mod.route('/<book_id>/delete/', methods=['GET', 'POST'])
@requires_login
def delete(book_id):
    """
    Delete the book with book_id
    """

    # We get the part to deleter
    book = Book.query.get(book_id)

    # if the current user isn't the author of that book, we redirect to homepage
    if book.user_id != g.user_id:
        flash(gettext("This isn't yours !"))
        return redirect(url_for('books.list'))

    #else we delete the book
    db.session.delete(book)
    # commit
    db.session.commit()

    # flash will display a message to the user
    flash(gettext('That book has been deleted !'))

    # redirect user to the list of books
    return redirect(url_for('books.list'))


@mod.route('/<book_id>/export/<export_format>', methods=['GET', 'POST'])
@requires_login
def export(book_id, export_format):
    """
    Get the chosen book in <export_format> format.
    """

    book = Book.query.get(book_id)

    # if the current user isn't the author of that book, we redirect to homepage
    if book.user_id != g.user_id:
        flash(gettext("This isn't yours !"))
        return redirect(url_for('books.list'))

    # We get all the data we have to pass to pandoc
    book = Book.query.get(book_id)
    parts = Part.query.filter_by(book_id=book_id).order_by(Part.order).all()
    user = User.query.get(book.user_id)

    # Now we check if all needed directories exists
    # If it doesn't we create them
    if not os.path.isdir(EXPORT_DIR + "/" + book_id):
        os.mkdir(EXPORT_DIR + "/" + book_id)

    # we generate the files we'll pass to pandoc, starting with the book
    # composed of the title, the author, then each part in the right order
    # we use io to explicitly fix the encoding to utf8
    export_file = io.open(
        EXPORT_DIR + "/" + book_id + "/book" + book_id + '.md',
        'w', encoding="utf-8"
    )

    # we write the metadata in YAML according to the pandoc documentation
    export_file.write('---\n')
    export_file.write('title:\n')
    export_file.write('- type: main\n')
    export_file.write('  text: "' + book.title + '"\n')
    export_file.write('- type: subtitle\n')
    export_file.write('  text: "' + book.subtitle + '"\n')
    export_file.write('creator:\n')
    export_file.write('- role: author\n')
    if book.displayed_name is None or book.displayed_name.strip() is '':
        export_file.write('  text: "' + user.name + '"\n')
    else:
        export_file.write('  text: "' + book.displayed_name + '"\n')
    export_file.write('- role: editor\n')
    export_file.write('  text: "' + book.editor + '"\n')
    export_file.write('publisher:  "' + book.publisher + '"\n')
    export_file.write('rights:  "' + book.rights + '"\n')
    # those dots mark the end of the yaml metadata block
    export_file.write('...\n\n\n')

    # then, we wrote all the content
    for the_part in parts:
        export_file.write(the_part.content + '\n\n')

    # When we wrote everything, we close the file
    export_file.close()

    if book.style is None:
        book.style = 'default'

    if book.cover is None:
        # Set up the pandoc command and run it
        args = [
            'pandoc', '-S',
            EXPORT_DIR + "/" + book_id + "/book" + book_id + '.md',
            '-s', '--toc',
            '-f', 'markdown',
            '--epub-stylesheet',
                os.path.join(TEMPLATE_DIR, book.style, 'styles.css'),
            '-t', export_format,
            '-o',
                EXPORT_DIR + "/" + book_id + "/book-"
                + book_id + '.' + export_format,
            ]
    else:
        # Set up the pandoc command and run it
        args = [
            'pandoc', '-S',
            EXPORT_DIR + "/" + book_id + "/book" + book_id + '.md',
            '--epub-cover-image', book.cover,
            '-s', '--toc',
            '-f', 'markdown',
            '--epub-stylesheet',
                os.path.join(TEMPLATE_DIR, book.style, 'styles.css'),
            '-t', export_format,
            '-o',
                EXPORT_DIR + "/" + book_id + "/book-"
                + book_id + '.' + export_format,
            ]
    subprocess.call(args)

    # we now send the correct file to the user
    return send_from_directory(
        directory=os.path.join(EXPORT_DIR, book_id),
        filename="book-" + book_id + "." + export_format,
        as_attachment=True)


@mod.route('/<book_id>/cover_add', methods=['GET', 'POST'])
@requires_login
def cover_add(book_id):
    """
    Add a cover to the book
    """

    form = AddCoverForm(request.form)

    # we get the book
    book = Book.query.get(book_id)

    # if the current user isn't the author of that book, we redirect to homepage
    if book.user_id != g.user_id:
        flash(gettext("This isn't yours !"))
        return redirect(url_for('books.list'))

    # now we set the page's title
    book_title = (book.title[:25] + '...') if len(book.title) > 25 else book.title
    site_title = gettext("Upload a cover for the book %(book_title)s", book_title=book_title)

    if form.validate_on_submit() and 'cover' in request.files:

        #we save the file, and get the name back
        cover = request.files['cover']
        if cover and allowed_file(cover.filename) \
            and cover.content_length < downpub.config['MAX_CONTENT_LENGTH']:

            # We test the file extension to recreate a file with the same one
            if "png" in cover.filename:
                file_extension = "png"
            if "jpg" in cover.filename:
                file_extension = "jpg"
            if "jpeg" in cover.filename:
                file_extension = "jpeg"
            if "gif" in cover.filename:
                file_extension = "gif"

            # we save the file
            cover.save(os.path.join(
                downpub.config['UPLOAD_FOLDER'],
                book_id + '.' + file_extension)
            )
            book.cover = os.path.join(
                downpub.config['UPLOAD_FOLDER'], book_id + '.' + file_extension
            )

            # Insert the record in our database and commit it
            db.session.commit()

            # flash will display a message to the user
            flash(gettext("That book's cover has been added !"))

            # redirect user to the 'book' page
            return redirect(url_for('books.list'))

        elif cover.content_length < downpub.config['MAX_CONTENT_LENGTH']:
            # flash will display a message to the user
            flash(gettext(
                "That picture's filesize is too big, max allowed size is %(size)s MB",
                size=round(downpub.config['MAX_CONTENT_LENGTH'], 1)
            ))

            # redirect user to the 'book' page
            return redirect(url_for('books.list'))

        elif not allowed_file(cover.filename):
            # flash will display a message to the user
            flash(gettext("That filetype is not allowed !"))

            # redirect user to the 'book' page
            return redirect(url_for('books.list'))

    else:
        if book.cover is None:
            return render_template("books/cover_add.html",
                form=form, book=book, user=g.user, site_title=site_title)
        else:
            # flash will display a message to the user
            flash(gettext(
                "That book already has a cover, "
                "delete it first to upload a new one !"
            ))
            # redirect user to the list of books
            return redirect(url_for('books.list'))


@mod.route('/<book_id>/cover_delete', methods=['GET', 'POST'])
@requires_login
def cover_delete(book_id):
    """
    Delete the book's cover
    """
    # create an user instance not yet stored in the database
    book = Book.query.get(book_id)

    # if the current user isn't the author of that book, we redirect to homepage
    if book.user_id != g.user_id:
        flash(gettext("This isn't yours !"))
        return redirect(url_for('books.list'))

    if not book.cover is None:

        # we try to delete all kind of extension type
        if os.path.exists(book.cover):
            os.remove(book.cover)

        # Empty the record in our database and commit it
        book.cover = None
        db.session.commit()

        # flash will display a message to the user
        flash(gettext("That book's cover has been deleted !"))
        # redirect user to the 'book' page
        return redirect(url_for('books.list'))

    else:
        # flash will display a message to the user
        flash(gettext("That book has no cover already !"))
        # redirect user to the list of books
        return redirect(url_for('books.list'))


@mod.route('/<book_id>/cover')
def cover_get(book_id):
    """
    Return the cover uploaded for that book with book_id or nothing
    """
    book = Book.query.get(book_id)

    # if the current user isn't the author of that book, we redirect to homepage
    if book.user_id != g.user_id:
        flash(gettext("This isn't yours !"))
        return redirect(url_for('books.list'))

    if book.cover is None:
        return None
    else:
        return send_file(book.cover)


@mod.route('/<book_id>/parts/', methods=['GET', 'POST'])
@requires_login
def parts_list(book_id):
    """
    List the parts (ordered by order field) from the book with book_id
    """

    parts = Part.query.filter_by(book_id=book_id).order_by(Part.order).all()
    book = Book.query.get(book_id)

    book_title = (book.title[:25] + '...') if len(book.title) > 25 else book.title

    # if the current user isn't the author of that book, we redirect to homepage
    if book.user_id != g.user_id:
        flash(gettext("This isn't yours !"))
        return redirect(url_for('books.list'))

    site_title = gettext('Parts of your book %(book_title)s',
        book_title=book_title)

    return render_template("books/parts_list.html",
        parts=parts, session=session, user=g.user,
        book=book, site_title=site_title)


@mod.route('/<book_id>/order_part/<part_id>/order/<order_value>', methods=['GET', 'POST'])
@requires_login
def order_part(book_id, part_id, order_value):
    """
    Change the order the part from the book with book_id
    """

    book = Book.query.get(book_id)
    part = Part.query.get(part_id)

    # we get both orders
    previous_order = part.order
    new_order = order_value

    # if we can find an existing part of this book with which to switch, we do
    if Part.query.filter_by(book_id=book_id, order=new_order).count() >= 1:
        # we get the actual order of the part we're editing
        # we switch the order of the part we're editing
        # with the one in that position
        part.order = new_order
        part_to_replace = Part.query.filter_by(book_id=book_id, order=new_order).first()
        part_to_replace.order = previous_order

        # then we commit
        db.session.commit()


        # we redirect to the parts list with a message
        flash(
            gettext('Order of the part %(part_title)s of your book %(book_title)s has been updated !',
            book_title=book.title, part_title=part.title))
        return redirect(url_for('books.parts_list', book_id=book_id))
    else:
        # if we can't find any part to switch with, this either means we
        # try to put a part which is already the first/last one
        flash(
            gettext('Order of the part %(part_title)s of your book %(book_title)s has no need to be updated !',
            book_title=book.title, part_title=part.title))
        return redirect(url_for('books.parts_list', book_id=book_id))


@mod.route('/<book_id>/add_part/', methods=['GET', 'POST'])
@requires_login
def add_part(book_id):
    """
    Add a part to the book with book_id
    """

    form = AddPartForm(request.form)
    book = Book.query.get(book_id)

    # if the current user isn't the author of that book, we redirect to homepage
    if book.user_id != g.user_id:
        flash(gettext("This isn't yours !"))
        return redirect(url_for('books.list'))

    book_title = (book.title[:25] + '...') if len(book.title) > 25 else book.title
    site_title = gettext('Add a part to your book %(book_title)s',
        book_title=book_title)

    # we define in a constant the default content for parts
    DEFAULT_PART_CONTENT = gettext("""# Chapter 1 - Introducing Downpub

This is a demo text which contains _examples_ on __how__ to use ___Markdown___ syntax to format your book.

## SubChapter 1 - Text Formatting, almost WYSIWYG

In this section, we'll have a look at making text **bold**, *italic* and etc. If you haven't realised by now, there is a very simple toolbar presented above the editor. Try selecting text in this editor and press any one of those buttons.

1. Item1
1. Item2
1. Item3

![Even my cat can be in your epub !](https://farm3.staticflickr.com/2756/4290352584_9d92fedfe2_z_d.jpg)


- Item1
- Item2
- Item3

### Example source code

```
print('Holy code of doom and destruction')
```


Take a peek at those buttons and see how they work !

Don't hesitate to export the book in epub or watch the preview to see what you wrote looks like.""")
    part_content = DEFAULT_PART_CONTENT

    if form.validate_on_submit():
        # create an user instance not yet stored in the database
        # we init order with the max order for this book plus one
        # or 1 if we can't find any
        max_order = Part.query.filter_by(book_id=book_id).order_by(Part.order.desc()).first()
        if max_order is not None:
            order = max_order.order + 1
        else:
            order = 1

        part = Part(book_id=book_id, title=form.title.data,
        content=form.content.data, order=order)
        # Insert the record in our database and commit it
        db.session.add(part)
        db.session.commit()

        # flash will display a message to the user
        flash(gettext(
            'The part %(part_title)s of your book %(book_title)s has been added !',
            part_title=part.title, book_title=book.title
        ))

        # redirect user to the parts list of the book
        return redirect(url_for('books.parts_list', book_id=book_id))

    return render_template("books/add_part.html",
        form=form, session=session, book=book, user=g.user,
        part=None, site_title=site_title, part_content=part_content)


@mod.route('/<book_id>/edit_part/<part_id>/', methods=['GET', 'POST'])
@requires_login
def edit_part(book_id, part_id):
    """
    Edit the part with part_id in the book with book_id
    """
    form = EditPartForm(request.form)
    book = Book.query.get(book_id)
    part = Part.query.get(part_id)

    # if the current user isn't the author of that book, we redirect to homepage
    if book.user_id != g.user_id:
        flash(gettext("This isn't yours !"))
        return redirect(url_for('books.list'))

    part_title = (part.title[:25] + '...') if len(part.title) > 25 else part.title
    book_title = (book.title[:25] + '...') if len(book.title) > 25 else book.title

    site_title = gettext(
        'Edit the part %(part_title)s of your book %(book_title)s',
        part_title=part_title, book_title=book_title
    )

    if not form.validate_on_submit():
        # form initializing when we first show the edit page
        form.title.data = part.title
        form.content.data = part.content

    if form.validate_on_submit():
        # get an user instance not yet stored in the database
        part = Part.query.get(part_id)

        # set the new values
        part.title = form.title.data
        part.content = form.content.data

        # commit
        db.session.commit()

        # flash will display a message to the user
        flash(gettext(
            'The part %(part_title)s of your book %(book_title)s has been edited !',
            part_title=part.title, book_title=book.title
        ))

        # redirect user to the parts list of the book
        return redirect(url_for('books.parts_list', book_id=book_id))

    return render_template("books/edit_part.html",
        form=form, part=part, book=book, session=session,
        user=g.user, site_title=site_title, part_content=part.content)


@mod.route('/<book_id>/del_part/<part_id>/', methods=['GET', 'POST'])
@requires_login
def del_part(book_id, part_id):
    """
    Delete the part with part_id in the book with book_id
    """

    # We get the part to delete
    part = Part.query.get(part_id)
    book = Book.query.get(book_id)

    # if the current user isn't the author of that book, we redirect to homepage
    if book.user_id != g.user_id:
        flash(gettext("This isn't yours !"))
        return redirect(url_for('books.list'))

    part_title = part.title

    # then we delete it
    db.session.delete(part)
    db.session.commit()

    # flash will display a message to the user
    flash(gettext(
        'The part %(part_title)s of your book %(book_title)s has been deleted !',
        part_title=part_title, book_title=book.title
    ))

    # parts = Part.query.filter_by(book_id=book_id).all()
    # book = Book.query.get(book_id)
    # redirect user to the parts list of the book
    return redirect(url_for('books.parts_list', book_id=book_id))


@mod.route('/<book_id>/export_part/<part_id>/format/<export_format>',
    methods=['GET', 'POST'])
@requires_login
def export_part(part_id, book_id, export_format):
    """
    Get the chosen part of the book with book_id in <export_format> format.
    """

    book = Book.query.get(book_id)

    # if the current user isn't the author of that book, we redirect to homepage
    if book.user_id != g.user_id:
        flash(gettext("This isn't yours !"))
        return redirect(url_for('books.list'))

    if os.path.exists(
        EXPORT_DIR + "/" + book_id + "/book-" + book_id
        + '-part-' + part_id + "." + export_format):
        # we now send the correct file to the user
        return send_from_directory(
            directory=EXPORT_DIR + "/" + book_id + "/",
            filename="book-" + book_id + '-part-'
                + part_id + "." + export_format,
            as_attachment=True)
    else:
        # We get all the data we have to pass to pandoc
        book = Book.query.get(book_id)
        part = Part.query.get(part_id)

        user = User.query.get(book.user_id)

        # Now we check if all needed directories exists
        # if it doesn't we create them
        if not os.path.isdir(EXPORT_DIR + "/" + book_id):
            os.mkdir(EXPORT_DIR + "/" + book_id)

        # we generate the files we'll pass to pandoc, starting with the book
        # composed of the title, the author, then each part in the right order
        # we use io to explicitly fix the encoding to utf8
        export_file = io.open(
            EXPORT_DIR + "/" + book_id + "/book-"
            + book_id + '-part-' + part_id + '.md',
            'w', encoding="utf-8"
        )

        # we write the metadata in YAML according to the pandoc documentation
        export_file.write('---\n')
        export_file.write('title:\n')
        export_file.write('- type: main\n')
        export_file.write('  text: "' + book.title + '"\n')
        export_file.write('- type: subtitle\n')
        export_file.write('  text: "' + book.subtitle + '"\n')
        export_file.write('creator:\n')
        export_file.write('- role: author\n')
        if book.displayed_name is None or book.displayed_name.strip() is '':
            export_file.write('  text: "' + user.name + '"\n')
        else:
            export_file.write('  text: "' + book.displayed_name + '"\n')
        export_file.write('- role: editor\n')
        export_file.write('  text: "' + book.editor + '"\n')
        export_file.write('publisher:  "' + book.publisher + '"\n')
        export_file.write('rights:  "' + book.rights + '"\n')
        # those dots mark the end of the yaml metadata block
        export_file.write('...\n\n\n')

        export_file.write(part.content + '\n\n')

        # When we wrote everything, we close the file
        export_file.close()

        # If there isn't a cover
        if book.cover is None:
            # Set up the pandoc and run it
            args = [
                'pandoc', '-S', EXPORT_DIR + "/" + book_id + "/book-"
                    + book_id + '-part-' + part_id + '.md',
                '-s', '--toc',
                '-f', 'markdown',
                '-t', export_format,
                '-o', EXPORT_DIR + "/" + book_id + "/book-"
                    + book_id + '-part-' + part_id + "." + export_format
                ]
        # If there is one, we add it to the pandoc call
        else:
            # Set up the pandoc and run it
            args = [
                'pandoc', '-S', EXPORT_DIR + "/" + book_id + "/book-"
                    + book_id + '-part-' + part_id + '.md',
                '--epub-cover-image', book.cover,
                '-s', '--toc',
                '-f', 'markdown',
                '-t', export_format,
                '-o', EXPORT_DIR + "/" + book_id + "/book-"
                    + book_id + '-part-' + part_id + "." + export_format
                ]

        try:
            subprocess.call(args)
        except:
            return redirect(url_for('500'))

        # we now send the correct file to the user
        return send_from_directory(
            directory=EXPORT_DIR + "/" + book_id + "/",
            filename="book-" + book_id + '-part-'
                + part_id + "." + export_format,
            as_attachment=True)


def allowed_file(filename):
    """
    Check if the uploaded file has the right extension
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS