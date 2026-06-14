import os
import uuid
import json
import shutil
import threading
import zlib
import subprocess
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory

# CRC-64 ECMA-182 polynomial
POLY_64 = 0x42F0E1EBA9EA3693
crc64_table = []
for i in range(256):
    crc = i
    for j in range(8):
        if crc & 1:
            crc = (crc >> 1) ^ POLY_64
        else:
            crc >>= 1
    crc64_table.append(crc)

def crc64(data: bytes) -> int:
    crc = 0xFFFFFFFFFFFFFFFF
    for byte in data:
        crc = (crc >> 8) ^ crc64_table[(crc ^ byte) & 0xFF]
    return crc ^ 0xFFFFFFFFFFFFFFFF

app = Flask(__name__)

UPLOAD_FOLDER = '/data/uploads'
OUTPUT_FOLDER = '/data/outputs'
STATUS_FILE = '/data/status.json'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Helper to load status
def load_status():
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

# Helper to save status
def save_status(status):
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(status, f, indent=2)
    except Exception:
        pass

# Initialize status lock
status_lock = threading.Lock()

def update_job(job_id, field, value):
    with status_lock:
        status = load_status()
        if job_id not in status:
            status[job_id] = {}
        status[job_id][field] = value
        save_status(status)

def run_conversion(job_id, input_path):
    update_job(job_id, 'state', 'converting')
    
    uuid_dir = os.path.join(OUTPUT_FOLDER, job_id)
    os.makedirs(uuid_dir, exist_ok=True)
    
    # Check if file has video/audio streams using ffprobe
    has_video = False
    has_audio = False
    try:
        probe_cmd = [
            'ffprobe', '-v', 'error', '-select_streams', 'v', 
            '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', input_path
        ]
        video_streams = subprocess.check_output(probe_cmd).decode().strip()
        has_video = 'video' in video_streams
    except Exception:
        pass

    try:
        probe_cmd = [
            'ffprobe', '-v', 'error', '-select_streams', 'a', 
            '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', input_path
        ]
        audio_streams = subprocess.check_output(probe_cmd).decode().strip()
        has_audio = 'audio' in audio_streams
    except Exception:
        pass

    log_output = []
    converted_files = []
    
    try:
        # 1. Video conversions (if video is present)
        if has_video:
            update_job(job_id, 'progress', 'Converting 720p Video...')
            v720_path = os.path.join(uuid_dir, 'video_720p.mp4')
            cmd = [
                'ffmpeg', '-y', '-i', input_path, 
                '-vf', 'scale=-2:720', 
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-c:a', 'aac', '-b:a', '128k', v720_path
            ]
            subprocess.run(cmd, check=True)
            converted_files.append('video_720p.mp4')
            
            update_job(job_id, 'progress', 'Converting 1080p Video...')
            v1080_path = os.path.join(uuid_dir, 'video_1080p.mp4')
            cmd = [
                'ffmpeg', '-y', '-i', input_path, 
                '-vf', 'scale=-2:1080', 
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-c:a', 'aac', '-b:a', '192k', v1080_path
            ]
            subprocess.run(cmd, check=True)
            converted_files.append('video_1080p.mp4')
        else:
            log_output.append("No video stream found.")

        # 2. Audio conversions (if audio is present, otherwise extract from video)
        if has_audio or has_video:
            # 48kbps
            update_job(job_id, 'progress', 'Converting 48kbps Audio...')
            a48_path = os.path.join(uuid_dir, 'audio_48k.mp3')
            cmd = ['ffmpeg', '-y', '-i', input_path, '-vn', '-c:a', 'libmp3lame', '-b:a', '48k', a48_path]
            subprocess.run(cmd, check=True)
            converted_files.append('audio_48k.mp3')

            # 96kbps
            update_job(job_id, 'progress', 'Converting 96kbps Audio...')
            a96_path = os.path.join(uuid_dir, 'audio_96k.mp3')
            cmd = ['ffmpeg', '-y', '-i', input_path, '-vn', '-c:a', 'libmp3lame', '-b:a', '96k', a96_path]
            subprocess.run(cmd, check=True)
            converted_files.append('audio_96k.mp3')

            # 128kbps
            update_job(job_id, 'progress', 'Converting 128kbps Audio...')
            a128_path = os.path.join(uuid_dir, 'audio_128k.mp3')
            cmd = ['ffmpeg', '-y', '-i', input_path, '-vn', '-c:a', 'libmp3lame', '-b:a', '128k', a128_path]
            subprocess.run(cmd, check=True)
            converted_files.append('audio_128k.mp3')
        else:
            log_output.append("No audio/video stream found for audio encoding.")

        # Clean up source file to save space
        try:
            os.remove(input_path)
        except Exception:
            pass

        update_job(job_id, 'state', 'completed')
        update_job(job_id, 'progress', '100%')
        update_job(job_id, 'files', converted_files)
        update_job(job_id, 'logs', log_output)
        
    except Exception as e:
        update_job(job_id, 'state', 'failed')
        update_job(job_id, 'progress', f'Error: {str(e)}')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload/chunk', methods=['POST'])
def upload_chunk():
    job_id = request.form.get('job_id')
    chunk_index = int(request.form.get('chunk_index', 0))
    total_chunks = int(request.form.get('total_chunks', 10))
    client_crc = int(request.form.get('crc', 0))
    filename = request.form.get('filename')
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    
    chunk_data = file.read()
    
    # Calculate CRC64 and verify
    server_crc = crc64(chunk_data)
    if server_crc != client_crc:
        return jsonify({'error': f'CRC mismatch on chunk {chunk_index}. Expected {client_crc}, got {server_crc}'}), 400
        
    # Save chunk to temp file
    chunk_filename = f"{job_id}_chunk_{chunk_index}"
    chunk_path = os.path.join(UPLOAD_FOLDER, chunk_filename)
    with open(chunk_path, 'wb') as f:
        f.write(chunk_data)
        
    # Check if all chunks are uploaded
    all_chunks_exist = True
    for i in range(total_chunks):
        if not os.path.exists(os.path.join(UPLOAD_FOLDER, f"{job_id}_chunk_{i}")):
            all_chunks_exist = False
            break
            
    if all_chunks_exist:
        # Merge all chunks
        final_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_{filename}")
        with open(final_path, 'wb') as outfile:
            for i in range(total_chunks):
                chunk_file = os.path.join(UPLOAD_FOLDER, f"{job_id}_chunk_{i}")
                with open(chunk_file, 'rb') as infile:
                    shutil.copyfileobj(infile, outfile)
                # Remove chunk file
                os.remove(chunk_file)
                
        # Initialize job status
        with status_lock:
            status = load_status()
            status[job_id] = {
                'id': job_id,
                'filename': filename,
                'state': 'pending',
                'progress': 'Waiting...',
                'files': [],
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            save_status(status)
            
        # Start conversion in background
        threading.Thread(target=run_conversion, args=(job_id, final_path)).start()
        return jsonify({'status': 'upload_complete', 'job_id': job_id})
        
    return jsonify({'status': 'chunk_received', 'chunk_index': chunk_index})

@app.route('/jobs', methods=['GET'])
def list_jobs():
    return jsonify(load_status())

@app.route('/download/<job_id>/<filename>')
def download(job_id, filename):
    safe_dir = os.path.join(OUTPUT_FOLDER, job_id)
    return send_from_directory(safe_dir, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
