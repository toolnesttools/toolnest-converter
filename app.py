"""ToolNest PDF to Word converter — FastAPI wrapper around pdf2docx.
Upload a PDF, get an editable .docx back. Files are processed in a temp
directory and deleted right after the response. One conversion at a time
(pdf2docx is CPU-heavy; free tiers are small)."""
import os, tempfile, threading, uuid

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from starlette.background import BackgroundTask

MAX_BYTES = 15 * 1024 * 1024  # 15 MB
_lock = threading.Lock()

app = FastAPI(title="ToolNest PDF to Word")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
def home():
    return """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>ToolNest PDF to Word</title></head>
<body style="font-family:Arial,sans-serif;max-width:640px;margin:40px auto;padding:0 16px">
<h2>ToolNest — PDF to Word Converter</h2>
<p>Free, no sign-up. Works best with text-based PDFs (invoices, reports, letters).
Scanned image PDFs have no text layer and will not convert well.</p>
<form action="/convert" method="post" enctype="multipart/form-data">
<input type="file" name="file" accept="application/pdf" required>
<button type="submit" style="margin-left:8px;padding:6px 14px">Convert to Word</button>
</form>
<p style="color:#666;font-size:13px">Your file is converted in memory-isolated temp storage and deleted immediately after download. Max 15 MB.</p>
</body></html>"""


@app.get("/health")
def health():
    return {"ok": True}


def _cleanup(paths):
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


@app.post("/convert")
async def convert(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File too large — the limit is 15 MB.")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "That file is not a PDF.")
    stem = os.path.splitext(os.path.basename(file.filename or "document"))[0] or "document"
    tmpdir = tempfile.mkdtemp(prefix="toolnest-")
    src = os.path.join(tmpdir, "in.pdf")
    dst = os.path.join(tmpdir, stem + ".docx")
    with open(src, "wb") as fh:
        fh.write(data)
    with _lock:
        try:
            from pdf2docx import Converter
            cv = Converter(src)
            cv.convert(dst)
            cv.close()
        except Exception:
            _cleanup([src, dst])
            raise HTTPException(422, "Sorry — this PDF could not be converted. It may be scanned, encrypted, or damaged.")
    return FileResponse(
        dst,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=stem + ".docx",
        background=BackgroundTask(_cleanup, [src, dst]),
    )
