import pymysql
import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
import pandas as pd
import speech_recognition as sr
from pydub import AudioSegment

app = Flask(__name__)
app.secret_key = "7d441f27d441f27567d441f2b6176a"

UPLOAD_FOLDER = "static/uploads"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

emotion_df = pd.read_csv("keywords_emotions.csv")

ALLOWED_EXTENSIONS = {"wav", "mp3", "ogg", "csv"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    return pymysql.connect(
        host="localhost",
        user="root",
        password="",
        database="Speech_Emotion_Recognition",
        charset="utf8",
        cursorclass=pymysql.cursors.DictCursor
    )

@app.route("/")
def index():
    return render_template("index.html")

#-------------------------------------------ADMIN----------------------------------------------

@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username == "admin" and password == "admin":
            session["admin"] = True
            flash("Login successful!", "success")
            return redirect(url_for("admin_home"))
        else:
            flash("Invalid username or password", "danger")

    return render_template("admin_login.html")

@app.route("/admin_home")
def admin_home():
    return render_template("admin_home.html")

@app.route("/admin_add_dataset", methods=["GET", "POST"])
def admin_add_dataset():

    if request.method == "POST":
        dataset_name = request.form.get("dataset_name")
        file = request.files.get("dataset_file")

        if not dataset_name or not file:
            flash("All fields are required", "danger")
            return redirect(url_for("admin_add_dataset"))

        if file.filename == "":
            flash("No file selected", "danger")
            return redirect(url_for("admin_add_dataset"))

        if not allowed_file(file.filename):
            flash("Only CSV or WAV files are allowed", "danger")
            return redirect(url_for("admin_add_dataset"))

        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(file_path)

        file_type = filename.rsplit(".", 1)[1].lower()

        try:
            connection = get_db_connection()
            with connection.cursor() as cursor:
                sql = """
                    INSERT INTO datasets (dataset_name, file_name, file_type)
                    VALUES (%s, %s, %s)
                """
                cursor.execute(sql, (dataset_name, filename, file_type))
            connection.commit()
            connection.close()

            flash("Dataset uploaded successfully!", "success")

        except Exception as e:
            flash("Database error: " + str(e), "danger")

        return redirect(url_for("admin_add_dataset"))

    return render_template("admin_add_dataset.html")

@app.route("/admin_view_user")
def admin_view_user():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
    users = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("admin_view_user.html", users=users)

#----------------------------------------USER--------------------------------------------------

@app.route("/user_login", methods=["GET", "POST"])
def user_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM users WHERE email=%s AND password=%s",
            (username, password)
        )
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if user:
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            flash("Login successful!", "success")
            return redirect(url_for("user_home"))
        else:
            flash("Invalid login credentials", "danger")

    return render_template("user_login.html")

@app.route("/user_register", methods=["GET", "POST"])
def user_register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        contact = request.form["contact"]
        dob = request.form["dob"]
        gender = request.form["gender"]
        address = request.form["address"]
        password = request.form["password"]

        photo = request.files["photo"]
        photo_filename = secure_filename(photo.filename)

        # Save photo
        photo_path = os.path.join(app.config["UPLOAD_FOLDER"], photo_filename)
        photo.save(photo_path)

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Check if email already exists
            cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
            existing_user = cursor.fetchone()

            if existing_user:
                flash("Email already registered!", "danger")
                return redirect(url_for("user_register"))

            # Insert user data
            sql = """
                INSERT INTO users 
                (name, email, contact, dob, gender, address, password, photo)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """
            cursor.execute(sql, (
                name, email, contact, dob, gender, address, password, photo_filename
            ))

            conn.commit()
            flash("Registration successful! Please login.", "success")
            return redirect(url_for("user_login"))

        except Exception as e:
            flash("Registration failed!", "danger")
            print(e)

        finally:
            cursor.close()
            conn.close()

    return render_template("user_register.html")

@app.route("/user_home")
def user_home():
    return render_template("user_home.html")

@app.route("/user_live_test", methods=["GET", "POST"])
def user_live_test():
    detected_text = ""
    detected_emotions = set()

    if request.method == "POST":
        audio_file = request.files.get("audio")

        if not audio_file:
            flash("No audio received", "danger")
            return redirect(url_for("user_live_test"))

        filename = "live_audio.webm"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        audio_file.save(filepath)

        # Convert WEBM → WAV
        wav_path = filepath.replace(".webm", ".wav")
        sound = AudioSegment.from_file(filepath, format="webm")
        sound = sound.set_channels(1)
        sound = sound.set_frame_rate(16000)
        sound.export(wav_path, format="wav")

        recognizer = sr.Recognizer()

        try:
            with sr.AudioFile(wav_path) as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio_data = recognizer.record(source)

            detected_text = recognizer.recognize_google(audio_data)

            words = detected_text.lower().split()
            for word in words:
                match = emotion_df[emotion_df["keyword"] == word]
                if not match.empty:
                    detected_emotions.add(match.iloc[0]["emotion"])

            # 🔹 SAVE HISTORY TO DB
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO emotion_history (user_id, test_type, detected_text, emotions)
                VALUES (%s, %s, %s, %s)
            """, (
                session["user_id"],
                "Live Voice",
                detected_text,
                ", ".join(detected_emotions)
            ))
            conn.commit()
            cursor.close()
            conn.close()

            flash("Live voice processed successfully!", "success")

        except sr.UnknownValueError:
            flash("Could not understand your voice", "danger")
        except Exception as e:
            flash(str(e), "danger")

    return render_template(
        "user_live_test.html",
        text=detected_text,
        emotions=list(detected_emotions)
    )

@app.route("/user_record_test", methods=["GET", "POST"])
def user_record_test():
    detected_text = ""
    detected_emotions = set()

    if request.method == "POST":
        audio_file = request.files.get("audio")

        if not audio_file or audio_file.filename == "":
            flash("No audio file selected", "danger")
            return redirect(url_for("user_record_test"))

        filename = secure_filename(audio_file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        audio_file.save(filepath)

        ext = filename.rsplit(".", 1)[1].lower()

        # Convert MP3 / OGG → WAV
        if ext in ["mp3", "ogg"]:
            wav_path = filepath.rsplit(".", 1)[0] + ".wav"

            if ext == "mp3":
                sound = AudioSegment.from_mp3(filepath)
            else:
                sound = AudioSegment.from_ogg(filepath)

            sound = sound.set_channels(1)
            sound = sound.set_frame_rate(16000)
            sound.export(wav_path, format="wav")
            filepath = wav_path

        recognizer = sr.Recognizer()

        try:
            with sr.AudioFile(filepath) as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio_data = recognizer.record(source)

            detected_text = recognizer.recognize_google(audio_data)

            words = detected_text.lower().split()
            for word in words:
                match = emotion_df[emotion_df["keyword"] == word]
                if not match.empty:
                    detected_emotions.add(match.iloc[0]["emotion"])

            # 🔹 SAVE HISTORY TO DB
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO emotion_history (user_id, test_type, detected_text, emotions)
                VALUES (%s, %s, %s, %s)
            """, (
                session["user_id"],
                "Recorded Audio",
                detected_text,
                ", ".join(detected_emotions)
            ))
            conn.commit()
            cursor.close()
            conn.close()

            flash("Audio processed successfully!", "success")

        except sr.UnknownValueError:
            flash("Could not understand the audio", "danger")
        except sr.RequestError:
            flash("Speech API unavailable", "danger")
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")

    return render_template(
        "user_record_test.html",
        text=detected_text,
        emotions=list(detected_emotions)
    )

@app.route("/user_view_history")
def user_view_history():

    if "user_id" not in session:
        flash("Please login first", "danger")
        return redirect(url_for("user_login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT test_type, detected_text, emotions, created_at
        FROM emotion_history
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (session["user_id"],))

    history = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("user_view_history.html", history=history)

if __name__ == "__main__":
    app.run(debug=True,port="7777",host="0.0.0.0")