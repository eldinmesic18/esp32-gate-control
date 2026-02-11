from flask import Flask, render_template, Response, request, jsonify, redirect, url_for
import cv2
import threading
import time
import database
import markdown
import os

app = Flask(__name__)

# Initialize DB
database.init_db()

# Global variables
camera_url = "http://192.168.1.100:81/stream"  # Placeholder URL, user needs to update this
frame = None
lock = threading.Lock()

def capture_frames():
    global frame
    cap = cv2.VideoCapture(camera_url)
    while True:
        success, img = cap.read()
        if success:
            with lock:
                frame = img
        else:
            time.sleep(0.1)
            # Try to reconnect
            cap.release()
            cap = cv2.VideoCapture(camera_url)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/manage')
def manage():
    plates = database.get_all_plates()
    return render_template('manage.html', plates=plates)

@app.route('/add_plate', methods=['POST'])
def add_plate_route():
    plate = request.form.get('plate')
    if plate:
        database.add_plate(plate.upper()) # Helper function needed in database.py
    return redirect(url_for('manage'))

@app.route('/delete_plate', methods=['POST'])
def delete_plate_route():
    plate_id = request.form.get('plate_id')
    if plate_id:
        database.remove_plate(plate_id)
    return redirect(url_for('manage'))

@app.route('/docs')
def list_docs():
    docs_path = os.path.join(app.root_path, 'docs')
    files = [f for f in os.listdir(docs_path) if f.endswith('.md')]
    return render_template('docs_list.html', files=files)

@app.route('/docs/<filename>')
def view_doc(filename):
    docs_path = os.path.join(app.root_path, 'docs')
    filepath = os.path.join(docs_path, filename)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            html_content = markdown.markdown(content)
        return render_template('doc_view.html', content=html_content, title=filename)
    return "File not found", 404

def generate_frames():
    global frame
    while True:
        with lock:
            if frame is None:
                continue
            ret, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # Start the frame capture thread
    # t = threading.Thread(target=capture_frames)
    # t.daemon = True
    # t.start()
    
    app.run(host='0.0.0.0', port=5000, debug=True)
