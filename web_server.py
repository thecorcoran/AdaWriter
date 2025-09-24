# web_server.py (v1.1)
import os
import re
import shutil
from flask import Flask, render_template_string, send_from_directory, abort, Response, request, redirect, url_for, flash
from io import BytesIO

try:
    # Werkzeug is a dependency of Flask, so this should be available.
    from werkzeug.utils import secure_filename
    from docx import Document
except ImportError:
    Document = None

def create_web_app(projects_dir, archive_dir, trash_dir):
    """Creates and configures the Flask application."""
    app = Flask(__name__)
    app.config['PROJECTS_DIR'] = projects_dir
    app.config['ARCHIVE_DIR'] = archive_dir
    app.config['TRASH_DIR'] = trash_dir
    app.secret_key = os.urandom(24) # Needed for flashing messages
    app.config['ALLOWED_EXTENSIONS'] = {'txt', 'docx'}

    # Combined HTML template. The file_item logic is now included directly.
    HTML_TEMPLATE = """
    {% macro file_item(file, docx_enabled) %}
    <li class="file-item">
        <span class="file-name">{{ file }}</span>
        <span class="download-links">
            <a href="{{ url_for('download_file', filename=file, format='txt') }}">.txt</a>
            <a href="{{ url_for('edit_file', filename=file) }}" class="edit">Edit</a>
            <a href="{{ url_for('archive_file', filename=file) }}" class="archive">Archive</a>
            <a href="{{ url_for('delete_file', filename=file) }}" class="delete" onclick="return confirm('Are you sure you want to delete this file? It will be moved to the trash.');">Delete</a>
            {% if docx_enabled %}
            <a href="{{ url_for('download_file', filename=file, format='docx') }}" class="docx">.docx</a>
            {% endif %}
        </span>
    </li>
    {% endmacro %}

    {% macro restore_item(file, source) %}
    <li class="file-item">
        <span class="file-name">{{ file }}</span>
        <span class="download-links">
            <a href="{{ url_for('restore_file', source=source, filename=file) }}" class="restore">Restore</a>
            {% if source == 'trash' %}
            <a href="{{ url_for('delete_permanently', filename=file) }}" class="delete" onclick="return confirm('This will permanently delete the file. Are you absolutely sure?');">Delete Permanently</a>
            {% endif %}
        </span>
    </li>
    {% endmacro %}

    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>AdaWriter Files</title>
        <link href="https://fonts.googleapis.com/css2?family=Lora:wght@400;700&display=swap" rel="stylesheet">
        <style>
            body { font-family: 'Lora', serif; line-height: 1.7; background-color: #fdfdfa; color: #3a3a3a; margin: 0; padding: 1rem; background-image: url('data:image/svg+xml,%3Csvg width="60" height="60" viewBox="0 0 60 60" xmlns="http://www.w3.org/2000/svg"%3E%3Cg fill="none" fill-rule="evenodd"%3E%3Cg fill="%23e8e6e1" fill-opacity="0.4"%3E%3Cpath d="M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z"/%3E%3C/g%3E%3C/g%3E%3C/svg%3E'); }
            .container { max-width: 800px; margin: 2rem auto; background: #fff; padding: 2rem 3rem; border-radius: 4px; box-shadow: 0 5px 15px rgba(0,0,0,0.07); border: 1px solid #e5e5e5; }
            h1 { font-size: 2.8rem; color: #2a2a2a; margin-bottom: 1rem; text-align: center; font-weight: 700; }
            h2 { font-size: 1.6rem; color: #5d4037; border-bottom: 1px solid #d7ccc8; padding-bottom: 0.5rem; margin-top: 2.5rem; font-weight: 700; }
            .file-list { list-style-type: none; padding: 0; }
            .file-item { background: #fafafa; padding: 0.9rem 1.5rem; border-radius: 4px; margin-bottom: 0.7rem; display: flex; justify-content: space-between; align-items: center; transition: background-color 0.2s; border-left: 4px solid #bcaaa4; }
            .file-item:hover { background-color: #f5f5f5; }
            .file-name { font-weight: 400; color: #4e4e4e; font-size: 1.1rem; }
            .download-links { display: flex; flex-wrap: wrap; justify-content: flex-end; }
            .download-links a { font-weight: 400; text-decoration: none; color: #546e7a; margin-left: 0.5rem; margin-top: 0.25rem; font-size: 0.9rem; padding: 0.3rem 0.6rem; border: 1px solid #b0bec5; border-radius: 20px; transition: all 0.2s; }
            .download-links a:hover { background-color: #546e7a; color: #fff; border-color: #546e7a; }
            .download-links a.docx { color: #4b634c; border-color: #81c784; }
            .download-links a.docx:hover { background-color: #4b634c; color: #fff; border-color: #4b634c; }
            .download-links a.restore { color: #00897b; border-color: #4db6ac; }
            .download-links a.restore:hover { background-color: #00897b; color: #fff; border-color: #00897b; }
            .download-links a.edit { color: #f57c00; border-color: #ffb74d; }
            .download-links a.edit:hover { background-color: #f57c00; color: #fff; border-color: #f57c00; }
            .download-links a.archive { color: #3f51b5; border-color: #7986cb; }
            .download-links a.archive:hover { background-color: #3f51b5; color: #fff; border-color: #3f51b5; }
            .download-links a.delete { color: #c62828; border-color: #ef9a9a; }
            .download-links a.delete:hover { background-color: #c62828; color: #fff; border-color: #c62828; }
            details { margin-bottom: 1rem; border: 1px solid #e0e0e0; border-radius: 4px; }
            summary { font-weight: 700; font-size: 1.2rem; padding: 0.8rem 1.2rem; cursor: pointer; background-color: #f5f5f5; border-radius: 4px 4px 0 0; color: #5d4037; }
            .upload-form { margin-top: 2.5rem; padding: 1.5rem; background: #f9f9f9; border: 1px dashed #ccc; border-radius: 4px; text-align: center; }
            .upload-form input[type="file"] { border: 1px solid #ccc; padding: 0.5rem; border-radius: 4px; }
            .upload-form input[type="submit"] { background-color: #5d4037; color: white; padding: 0.6rem 1.2rem; border: none; border-radius: 4px; cursor: pointer; font-family: 'Lora', serif; font-size: 1rem; transition: background-color 0.2s; }
            .upload-form input[type="submit"]:hover { background-color: #4e342e; }
            .flash-message { padding: 1rem; background-color: #e8f5e9; color: #2e7d32; border-left: 5px solid #4caf50; margin-bottom: 1rem; border-radius: 4px; }
            .flash-message.error { background-color: #ffebee; color: #c62828; border-left-color: #f44336; }
            .details-content { padding: 1rem; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>AdaWriter Files</h1>
            
            {% with messages = get_flashed_messages(with_categories=true) %}
              {% if messages %}{% for category, message in messages %}<div class="flash-message {{ category }}">{{ message }}</div>{% endfor %}{% endif %}
            {% endwith %}

            <h2>Journals</h2>
            <details>
                <summary>Monthly Summaries</summary>
                <div class="details-content">
                    <ul class="file-list">
                        {% for file in files.monthly %}
                            {{ file_item(file, docx_enabled) }}
                        {% else %}<li>No monthly journals found.</li>{% endfor %}
                    </ul>
                </div>
            </details>
            <details>
                <summary>Daily Entries</summary>
                <div class="details-content">
                    <ul class="file-list">
                        {% for file in files.daily %}
                            {{ file_item(file, docx_enabled) }}
                        {% else %}<li>No daily entries found.</li>{% endfor %}
                    </ul>
                </div>
            </details>

            <h2>Projects</h2>
            <ul class="file-list">
                {% for file in files.projects %}
                    {{ file_item(file, docx_enabled) }}
                {% else %}
                    <li>No project files found.</li>
                {% endfor %}
            </ul>

            <div class="upload-form">
                <h2>Upload New File</h2>
                <form method="post" enctype="multipart/form-data" action="{{ url_for('upload_file') }}">
                    <input type="file" name="file" accept=".txt,.docx">
                    <input type="submit" value="Upload">
                </form>
            </div>
        </div>

        <div class="container">
            <h2>Management</h2>
            <details>
                <summary>Archived Files</summary>
                <div class="details-content">
                    <ul class="file-list">
                        {% for file in files.archived %}{{ restore_item(file, 'archive') }}{% else %}<li>No archived files.</li>{% endfor %}
                    </ul>
                </div>
            </details>
            <details>
                <summary>Trash</summary>
                <div class="details-content">
                    <ul class="file-list">
                        {% for file in files.trashed %}{{ restore_item(file, 'trash') }}{% else %}<li>Trash is empty.</li>{% endfor %}
                    </ul>
                </div>
            </details>
        </div>
    </body>
    </html>
    """

    EDITOR_TEMPLATE = """
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Edit {{ filename }}</title>
        <link href="https://fonts.googleapis.com/css2?family=Lora:wght@400;700&family=Source+Code+Pro&display=swap" rel="stylesheet">
        <style>
            body { font-family: 'Lora', serif; line-height: 1.7; background-color: #fdfdfa; color: #3a3a3a; margin: 0; padding: 1rem; }
            .container { max-width: 800px; margin: 2rem auto; background: #fff; padding: 2rem 3rem; border-radius: 4px; box-shadow: 0 5px 15px rgba(0,0,0,0.07); border: 1px solid #e5e5e5; }
            h1 { font-size: 2.2rem; color: #2a2a2a; margin-bottom: 1.5rem; font-weight: 700; }
            textarea { width: 100%; height: 60vh; font-family: 'Source Code Pro', monospace; font-size: 1rem; line-height: 1.6; padding: 1rem; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
            .actions { margin-top: 1.5rem; text-align: right; }
            .actions a, .actions input { text-decoration: none; display: inline-block; padding: 0.7rem 1.5rem; border-radius: 4px; font-family: 'Lora', serif; font-size: 1rem; transition: background-color 0.2s; }
            .actions a { background-color: #f1f1f1; color: #333; border: 1px solid #ccc; margin-right: 0.5rem; }
            .actions a:hover { background-color: #e0e0e0; }
            .actions input { background-color: #5d4037; color: white; border: none; cursor: pointer; }
            .actions input:hover { background-color: #4e342e; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Editing: {{ filename }}</h1>
            <form method="post">
                <textarea name="content">{{ content }}</textarea>
                <div class="actions"><a href="{{ url_for('index') }}">Cancel</a><input type="submit" value="Save Changes"></div>
            </form>
        </div>
    </body>
    </html>
    """

    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

    @app.route('/')
    def index():
        """Lists all .txt files in the projects directory."""
        def get_files(directory):
            return sorted([f for f in os.listdir(directory) if f.endswith('.txt')], reverse=True)

        try:
            all_files = get_files(app.config['PROJECTS_DIR'])
            categorized_files = {
                'monthly': [f for f in all_files if re.match(r'^\d{4}-\d{2}\.txt$', f)],
                'daily': [f for f in all_files if re.match(r'^\d{4}-\d{2}-\d{2}\.txt$', f)],
                'projects': [f for f in all_files if not re.match(r'^\d{4}-\d{2}(-\d{2})?\.txt$', f)],
                'archived': get_files(app.config['ARCHIVE_DIR']),
                'trashed': get_files(app.config['TRASH_DIR'])
            }
            return render_template_string(HTML_TEMPLATE, files=categorized_files, docx_enabled=Document is not None)
        except Exception as e:
            app.logger.error(f"Error reading project directory: {e}", exc_info=True)
            return "Error reading project directory.", 500

    def _move_file(filename, dest_dir):
        """Safely moves a file from the projects dir to a destination."""
        try:
            safe_projects_dir = os.path.abspath(app.config['PROJECTS_DIR'])
            safe_dest_dir = os.path.abspath(dest_dir)
            os.makedirs(safe_dest_dir, exist_ok=True)

            src_path = os.path.abspath(os.path.join(safe_projects_dir, filename))
            if not src_path.startswith(safe_projects_dir):
                abort(403) # Path traversal attempt

            if os.path.exists(src_path):
                shutil.move(src_path, os.path.join(safe_dest_dir, filename))
                return True
        except Exception as e:
            app.logger.error(f"Error moving file {filename} to {dest_dir}: {e}", exc_info=True)
        return False

    @app.route('/archive/<path:filename>')
    def archive_file(filename):
        """Moves a file to the archive directory."""
        if _move_file(filename, app.config['ARCHIVE_DIR']):
            flash(f"'{filename}' archived successfully.", 'success')
        else:
            flash(f"Error archiving '{filename}'.", 'error')
        return redirect(url_for('index'))

    @app.route('/delete/<path:filename>')
    def delete_file(filename):
        """Moves a file to the trash directory."""
        if _move_file(filename, app.config['TRASH_DIR']):
            flash(f"'{filename}' moved to trash.", 'success')
        else:
            flash(f"Error deleting '{filename}'.", 'error')
        return redirect(url_for('index'))

    @app.route('/restore/<source>/<path:filename>')
    def restore_file(source, filename):
        """Moves a file from archive or trash back to the projects directory."""
        if source == 'archive':
            src_dir = app.config['ARCHIVE_DIR']
        elif source == 'trash':
            src_dir = app.config['TRASH_DIR']
        else:
            abort(404)

        dest_dir = app.config['PROJECTS_DIR']
        src_path = os.path.abspath(os.path.join(src_dir, filename))
        dest_path = os.path.abspath(os.path.join(dest_dir, filename))

        # Security check
        if not src_path.startswith(os.path.abspath(src_dir)):
            abort(403)

        try:
            shutil.move(src_path, dest_path)
            flash(f"'{filename}' restored successfully.", 'success')
        except Exception as e:
            app.logger.error(f"Error restoring file {filename}: {e}", exc_info=True)
            flash(f"Error restoring '{filename}'.", 'error')
        return redirect(url_for('index'))

    @app.route('/upload', methods=['POST'])
    def upload_file():
        if 'file' not in request.files:
            flash('No file part in request.', 'error')
            return redirect(url_for('index'))
        file = request.files['file']
        if file.filename == '':
            flash('No selected file.', 'error')
            return redirect(url_for('index'))
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['PROJECTS_DIR'], filename))
            flash(f"'{filename}' uploaded successfully.", 'success')
        else:
            flash('Invalid file type. Only .txt and .docx files are allowed.', 'error')
        return redirect(url_for('index'))

    @app.route('/edit/<path:filename>', methods=['GET', 'POST'])
    def edit_file(filename):
        """Displays an editor for a file and saves changes."""
        try:
            safe_projects_dir = os.path.abspath(app.config['PROJECTS_DIR'])
            file_path = os.path.abspath(os.path.join(safe_projects_dir, filename))

            if not file_path.startswith(safe_projects_dir):
                abort(403)

            if request.method == 'POST':
                new_content = request.form.get('content', '')
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                flash(f"'{filename}' saved successfully.", 'success')
                return redirect(url_for('index'))

            # GET request
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return render_template_string(EDITOR_TEMPLATE, filename=filename, content=content)

        except FileNotFoundError:
            abort(404)
        except Exception as e:
            app.logger.error(f"Error in edit_file for {filename}: {e}", exc_info=True)
            flash(f"An error occurred while handling '{filename}'.", 'error')
            return redirect(url_for('index'))

    @app.route('/delete_permanently/<path:filename>')
    def delete_permanently(filename):
        """Permanently deletes a file from the trash directory."""
        try:
            safe_trash_dir = os.path.abspath(app.config['TRASH_DIR'])
            file_path = os.path.abspath(os.path.join(safe_trash_dir, filename))

            # Security check to prevent path traversal
            if not file_path.startswith(safe_trash_dir):
                abort(403)

            if os.path.exists(file_path):
                os.remove(file_path)
                flash(f"'{filename}' permanently deleted.", 'success')
            else:
                flash(f"'{filename}' not found in trash.", 'error')
        except Exception as e:
            app.logger.error(f"Error permanently deleting file {filename}: {e}", exc_info=True)
            flash(f"Error permanently deleting '{filename}'.", 'error')
        return redirect(url_for('index'))

    @app.route('/download/<path:filename>')
    def download_file(filename):
        """Serves a specific file for download."""
        file_format = request.args.get('format', 'txt')
        try:
            # Security: Ensure the path is safe and within the projects directory
            safe_dir = os.path.abspath(app.config['PROJECTS_DIR'])
            file_path = os.path.abspath(os.path.join(safe_dir, filename))
            
            if not file_path.startswith(safe_dir):
                abort(403) # Path traversal attempt

            if file_format == 'docx' and Document is not None:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                document = Document()
                document.add_paragraph(content)
                
                buffer = BytesIO()
                document.save(buffer)
                buffer.seek(0)
                
                return Response(
                    buffer,
                    mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    headers={'Content-Disposition': f'attachment;filename={os.path.splitext(filename)[0]}.docx'}
                )
            else: # Default to txt
                return send_from_directory(
                    directory=safe_dir, path=filename, as_attachment=True
                )
        except FileNotFoundError:
            abort(404)
        except Exception as e:
            app.logger.error(f"Error serving file {filename}: {e}", exc_info=True)
            return "Error serving file.", 500

    return app

if __name__ == '__main__':
    # This part is for testing purposes only.
    # The actual server is started from ada_writer.py.
    print("This script is not meant to be run directly.")
    print("It is imported by ada_writer.py to start the web server.")
    # You could add test logic here if needed, e.g., creating a dummy projects folder
    # and running the app for local testing.
    # test_projects_dir = 'test_projects'
    # os.makedirs(test_projects_dir, exist_ok=True)
    # with open(os.path.join(test_projects_dir, 'test.txt'), 'w') as f:
    #     f.write('hello world')
    # test_app = create_web_app(test_projects_dir)
    # test_app.run(debug=True)
