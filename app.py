import io
import uuid
import mimetypes
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_file
from werkzeug.utils import secure_filename
from markitdown import MarkItDown

app = Flask(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
UPLOAD_FOLDER = Path(__file__).parent / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)

MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

ALLOWED_EXTENSIONS = {
    # Documents
    ".pdf", ".pptx", ".ppt", ".docx", ".doc", ".xlsx", ".xls",
    # Images
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp",
    # Web / markup
    ".html", ".htm",
    # Text / data
    ".csv", ".json", ".xml", ".txt", ".md",
    # Archives
    ".zip",
    # E-books
    ".epub",
}


def _is_allowed(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def _cleanup(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


# ── Routes ─────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/convert", methods=["POST"])
def convert():
    if "file" not in request.files:
        return jsonify({"error": "No file provided."}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected."}), 400

    original_name = secure_filename(file.filename)
    if not _is_allowed(original_name):
        return jsonify({
            "error": f"Unsupported file type '{Path(original_name).suffix}'. "
                     "Supported: PDF, PPTX, DOCX, XLSX, images, HTML, CSV, JSON, XML, TXT, ZIP, EPUB."
        }), 415

    # Save to a uniquely named temp file so concurrent requests don't collide
    tmp_path = UPLOAD_FOLDER / f"{uuid.uuid4().hex}_{original_name}"
    try:
        file.save(tmp_path)

        md_converter = MarkItDown(enable_plugins=False)
        # convert_local() is preferred for server-side use (avoids URI fetching)
        result = md_converter.convert_local(str(tmp_path))
        markdown_text = result.text_content or ""

        if not markdown_text.strip():
            return jsonify({
                "error": "Conversion produced empty output. "
                         "The file may be empty, password-protected, or unsupported."
            }), 422

        stem = Path(original_name).stem
        return jsonify({
            "markdown": markdown_text,
            "filename": f"{stem}.md",
            "original": original_name,
            "char_count": len(markdown_text),
            # Rough token estimate: ~4 chars per token
            "token_estimate": len(markdown_text) // 4,
        })

    except Exception as exc:
        return jsonify({"error": f"Conversion failed: {str(exc)}"}), 500
    finally:
        _cleanup(tmp_path)


@app.route("/download", methods=["POST"])
def download():
    data = request.get_json(silent=True)
    if not data or "markdown" not in data or "filename" not in data:
        return jsonify({"error": "Invalid request."}), 400

    filename = secure_filename(data["filename"])
    if not filename.endswith(".md"):
        filename += ".md"

    buffer = io.BytesIO(data["markdown"].encode("utf-8"))
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="text/markdown",
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
