# web_server.py (v1.1)
import os
import re
from flask import Flask, render_template_string, send_from_directory, abort, Response, request
from io import BytesIO

try:
    from docx import Document
except ImportError:
    Document = None

def create_web_app(projects_dir):
    """Creates and configures the Flask application."""
    app = Flask(__name__)
    app.config['PROJECTS_DIR'] = projects_dir

    # Combined HTML template. The file_item logic is now included directly.
    HTML_TEMPLATE = """
    {% macro file_item(file, docx_enabled) %}
    <li class="file-item">
        <span class="file-name">{{ file }}</span>
        <span class="download-links">
            <a href="{{ url_for('download_file', filename=file, format='txt') }}">.txt</a>
            {% if docx_enabled %}
            <a href="{{ url_for('download_file', filename=file, format='docx') }}" class="docx">.docx</a>
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
            .download-links a { font-weight: 400; text-decoration: none; color: #546e7a; margin-left: 1rem; font-size: 0.9rem; padding: 0.3rem 0.6rem; border: 1px solid #b0bec5; border-radius: 20px; transition: all 0.2s; }
            .download-links a:hover { background-color: #546e7a; color: #fff; border-color: #546e7a; }
            .download-links a.docx { color: #4b634c; border-color: #81c784; }
            .download-links a.docx:hover { background-color: #4b634c; color: #fff; border-color: #4b634c; }
            details { margin-bottom: 1rem; border: 1px solid #e0e0e0; border-radius: 4px; }
            summary { font-weight: 700; font-size: 1.2rem; padding: 0.8rem 1.2rem; cursor: pointer; background-color: #f5f5f5; border-radius: 4px 4px 0 0; color: #5d4037; }
            .details-content { padding: 1rem; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>AdaWriter Files</h1>

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
        </div>
    </body>
    </html>
    """

    @app.route('/')
    def index():
        """Lists all .txt files in the projects directory."""
        try:
            all_files = sorted([f for f in os.listdir(app.config['PROJECTS_DIR']) if f.endswith('.txt')], reverse=True)
            categorized_files = {
                'monthly': [f for f in all_files if re.match(r'^\d{4}-\d{2}\.txt$', f)],
                'daily': [f for f in all_files if re.match(r'^\d{4}-\d{2}-\d{2}\.txt$', f)],
                'projects': [f for f in all_files if not re.match(r'^\d{4}-\d{2}(-\d{2})?\.txt$', f)]
            }
            return render_template_string(HTML_TEMPLATE, files=categorized_files, docx_enabled=Document is not None)
        except Exception as e:
            app.logger.error(f"Error reading project directory: {e}", exc_info=True)
            return "Error reading project directory.", 500

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
