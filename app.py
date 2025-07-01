from flask import Flask, render_template, request, jsonify, session, redirect
import cv2, torch, pickle, os, io, base64, shutil
import numpy as np
import pandas as pd
from PIL import Image
from facenet_pytorch import MTCNN, InceptionResnetV1
from werkzeug.utils import secure_filename
from datetime import datetime
from flask import send_file
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO
from flask import send_from_directory

app = Flask(__name__)
app.static_folder = 'dataset'
app.secret_key = "rahasia_kunci_super"

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
mtcnn = MTCNN(image_size=160, margin=20, device=device)
resnet = InceptionResnetV1(pretrained='vggface2').eval().to(device)

# Load atau buat embeddings
if os.path.exists("embeddings.pkl"):
    with open("embeddings.pkl", "rb") as f:
        embeddings = pickle.load(f)
else:
    embeddings = {}

attendance = set()
threshold = 0.5
DATASET_DIR = "dataset"
os.makedirs(DATASET_DIR, exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/detect', methods=['POST'])
def detect():
    data = request.json
    image_data = data['image']
    header, encoded = image_data.split(",", 1)
    img_bytes = base64.b64decode(encoded)
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")

    identity = "Tidak Dikenal"

    face = mtcnn(img)  # Deteksi wajah dan crop
    if face is not None:
        # Ekstrak embedding wajah
        embedding = resnet(face.unsqueeze(0).to(device)).detach().cpu().numpy()

        min_dist = float("inf")
        closest_name = None

        # Bandingkan dengan semua embedding dalam database
        for name, db_emb in embeddings.items():
            dist = np.linalg.norm(embedding - db_emb)
            if dist < min_dist:
                min_dist = dist
                closest_name = name

        # Threshold aman agar tidak salah deteksi
        threshold = 0.7  # lebih ketat dari 0.9
        if min_dist < threshold:
            identity = closest_name
            # Simpan ke file presensi jika dikenali
            attendance.add(identity)
            with open("presensi.csv", "a") as f:
                f.write(f"{identity},{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    return jsonify({"identity": identity})


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == 'admin' and request.form['password'] == '1234':
            session['admin'] = True
            return redirect('/dataset')
        else:
            return "<script>alert('Login gagal!');window.location='/login';</script>"
    return render_template("login.html")

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect('/')

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if not session.get('admin'):
        return redirect('/login')

    if request.method == 'POST':
        name = request.form['name']
        file = request.files['image']
        if file and name:
            filename = secure_filename(file.filename)
            person_dir = os.path.join(DATASET_DIR, name)
            os.makedirs(person_dir, exist_ok=True)
            save_path = os.path.join(person_dir, filename)
            file.save(save_path)

            img = Image.open(save_path).convert("RGB")
            face = mtcnn(img)
            if face is not None:
                embedding = resnet(face.unsqueeze(0).to(device)).detach().cpu().numpy()
                embeddings[name] = embedding
                with open("embeddings.pkl", "wb") as f:
                    pickle.dump(embeddings, f)
                return render_template("upload_success.html", name=name)
            else:
                return "<h3>Wajah tidak terdeteksi!</h3><a href='/upload'>Coba lagi</a>"
    return render_template("upload.html")

@app.route('/dataset')
def dataset():
    if not session.get('admin'):
        return redirect('/login')

    names = []
    for name in os.listdir(DATASET_DIR):
        path = os.path.join(DATASET_DIR, name)
        if os.path.isdir(path):
            count = len(os.listdir(path))
            names.append({'name': name, 'count': count})
    return render_template("dataset.html", names=names)

@app.route('/edit/<old_name>', methods=['GET', 'POST'])
def edit_name(old_name):
    if not session.get('admin'):
        return redirect('/login')

    person_dir = os.path.join(DATASET_DIR, old_name)
    image_path = None

    # Cek dan ambil foto pertama dari folder pengguna
    if os.path.exists(person_dir):
        files = os.listdir(person_dir)
        if files:
            image_path = f"/dataset/{old_name}/{files[0]}"

    if request.method == 'POST':
        new_name = request.form['new_name']
        file = request.files.get('new_image')
        old_path = os.path.join(DATASET_DIR, old_name)
        new_path = os.path.join(DATASET_DIR, new_name)
    
        # Rename folder jika nama berubah
        if old_name != new_name:
            if os.path.exists(new_path):
                return f"<script>alert('Nama \"{new_name}\" sudah ada.');window.location='/edit/{old_name}';</script>"
            os.rename(old_path, new_path)

        # Ganti gambar jika ada file baru
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            save_path = os.path.join(new_path, filename)
            file.save(save_path)

            img = Image.open(save_path).convert("RGB")
            face = mtcnn(img)
            if face is not None:
                embedding = resnet(face.unsqueeze(0).to(device)).detach().cpu().numpy()
                embeddings[new_name] = embedding
            else:
                return f"<script>alert('Wajah tidak terdeteksi dari gambar baru!');window.location='/edit/{new_name}';</script>"
        else:
            # Jika tidak ada gambar baru, tetap gunakan embedding lama
            if old_name in embeddings:
                embeddings[new_name] = embeddings.pop(old_name)

        # Simpan kembali embeddings
        with open("embeddings.pkl", "wb") as f:
            pickle.dump(embeddings, f)

        return redirect('/dataset')

    return render_template("edit.html", old_name=old_name, image_path=image_path)

@app.route('/dataset/<path:filename>')
def serve_dataset_image(filename):
    return send_from_directory(DATASET_DIR, filename)

@app.route('/delete/<name>')
def delete_name(name):
    if not session.get('admin'):
        return redirect('/login')

    path = os.path.join(DATASET_DIR, name)
    if os.path.exists(path):
        shutil.rmtree(path)

    if name in embeddings:
        embeddings.pop(name)
        with open("embeddings.pkl", "wb") as f:
            pickle.dump(embeddings, f)

    return redirect('/dataset')


@app.route('/presensi')
def lihat_presensi():
    if not session.get('admin'):
        return redirect('/login')

    try:
        df = pd.read_csv("presensi.csv", names=["Nama", "Waktu"])
        # Pisahkan waktu jadi dua kolom
        df["Tanggal"] = pd.to_datetime(df["Waktu"]).dt.date
        df["Jam"] = pd.to_datetime(df["Waktu"]).dt.time
        data = df.to_dict(orient="records")
    except FileNotFoundError:
        data = []
    return render_template("presensi.html", data=data)

@app.route('/download_presensi_pdf')
def download_presensi_pdf():
    if not session.get('admin'):
        return redirect('/login')

    try:
        df = pd.read_csv("presensi.csv", names=["Nama", "Waktu"])
        df["Tanggal"] = pd.to_datetime(df["Waktu"]).dt.date
        df["Jam"] = pd.to_datetime(df["Waktu"]).dt.time
    except:
        df = pd.DataFrame(columns=["Nama", "Tanggal", "Jam"])

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    p.setFont("Helvetica-Bold", 14)
    p.drawString(200, height - 50, "Rekap Presensi")

    p.setFont("Helvetica", 10)
    y = height - 80
    row_height = 20

    # Header
    p.drawString(50, y, "No")
    p.drawString(100, y, "Nama")
    p.drawString(300, y, "Tanggal")
    p.drawString(400, y, "Jam")
    y -= row_height

    # Isi tabel
    for i, row in df.iterrows():
        if y < 50:
            p.showPage()
            y = height - 80
        p.drawString(50, y, str(i + 1))
        p.drawString(100, y, str(row["Nama"]))
        p.drawString(300, y, str(row["Tanggal"]))
        p.drawString(400, y, str(row["Jam"]))
        y -= row_height

    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="rekap_presensi.pdf", mimetype='application/pdf')


if __name__ == "__main__":
    app.run(debug=True)
