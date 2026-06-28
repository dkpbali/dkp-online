"""
routes.py  –  Flask Blueprint untuk modul Kendaraan
Daftarkan ke app utama:
    from kendaraan_module.backend.routes import kendaraan_bp
    app.register_blueprint(kendaraan_bp)
"""
import base64, io
from flask import Blueprint, request, jsonify, send_file
from .generate_ba   import generate
from .xlsx_reader   import get_peminjaman, list_peminjaman, list_service

kendaraan_bp = Blueprint("kendaraan", __name__, url_prefix="/api/kendaraan")


# ── GET /api/kendaraan/peminjaman  → list semua peminjaman ────────
@kendaraan_bp.route("/peminjaman")
def api_list_peminjaman():
    return jsonify(list_peminjaman())


# ── GET /api/kendaraan/service  → list semua service ─────────────
@kendaraan_bp.route("/service")
def api_list_service():
    return jsonify(list_service())


# ── POST /api/kendaraan/generate-ba  → download .docx ────────────
@kendaraan_bp.route("/generate-ba", methods=["POST"])
def api_generate_ba():
    """
    Body JSON:
    {
        "no_ba"      : "BA/001/2025",       ← wajib; lookup otomatis dari xlsx
        "ttd_base64" : "data:image/png;base64,..."  ← opsional
    }

    Atau kirim data manual (tanpa lookup xlsx):
    {
        "NO_BA":           "BA/001/2025",
        "NAMA_PEMINJAM":   "I Wayan Sudana",
        "NIP_NIK":         "1985...",
        "TUJUAN":          "Rapat",
        "NAMA_KENDARAAN":  "Toyota Kijang Innova",
        "NO_POLISI":       "DK 1234 AB",
        "JENIS_PEMINJAMAN":"Tugas Dinas",
        "TANGGAL_PINJAM":  "02/06/2025",
        "KONDISI_KEMBALI": "Baik",
        "JABATAN":         "Tugas Dinas",
        "ttd_base64":      "..."
    }
    """
    body = request.get_json(force=True)

    # Decode TTD
    ttd_bytes = None
    raw_b64 = body.get("ttd_base64", "")
    if raw_b64:
        raw = raw_b64.split(",", 1)[-1]   # strip "data:image/png;base64,"
        ttd_bytes = base64.b64decode(raw)

    # Ambil data: prioritas lookup xlsx, fallback pakai body langsung
    no_ba = body.get("no_ba") or body.get("NO_BA")
    if no_ba and not body.get("NAMA_PEMINJAM"):
        try:
            data = get_peminjaman(no_ba)
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
    else:
        data = {k: v for k, v in body.items() if k != "ttd_base64"}

    docx_bytes = generate(data=data, ttd=ttd_bytes)

    safe = (no_ba or "BA").replace("/", "-")
    return send_file(
        io.BytesIO(docx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=f"BA_{safe}.docx",
    )
