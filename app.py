from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import os
import uuid
from werkzeug.utils import secure_filename
import db

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()  # Generates a random session secret key on startup

# Set upload folder
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Standard allowed extensions
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_AUDIO_EXTENSIONS = {'webm', 'ogg', 'wav', 'mp3', 'm4a', '3gp'}

def allowed_file(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set

def delete_item_media(item):
    """Deletes all media files (photos, audio) associated with an item from disk."""
    if item['photo_filepath']:
        photo_paths = item['photo_filepath'].split(',')
        for path in photo_paths:
            photo_path = os.path.join('static', path.strip())
            if os.path.exists(photo_path):
                try:
                    os.remove(photo_path)
                except Exception as e:
                    print(f"Error removing photo file {photo_path}: {e}")
                    
    if item['audio_filepath']:
        audio_path = os.path.join('static', item['audio_filepath'])
        if os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except Exception as e:
                print(f"Error removing audio file {audio_path}: {e}")

# Initialize the database on startup
db.init_db()

@app.route('/')
def index():
    """Landing Page."""
    return render_template('landing.html')

@app.route('/inspection/new', methods=['GET', 'POST'])
def init_inspection():
    """Step 1: Prompt for site name and date to initialize inspection."""
    if request.method == 'POST':
        site_name = request.form.get('site_name', '').strip()
        inspection_date = request.form.get('inspection_date', '').strip()
        
        if not site_name or not inspection_date:
            flash("Please enter both a Site Name and Date.", "danger")
            return redirect(url_for('init_inspection'))
        
        # Create inspection entry
        inspection_id = db.create_inspection(site_name, inspection_date)
        
        # Set session variable to link future items
        session['inspection_id'] = inspection_id
        session['site_name'] = site_name
        
        return redirect(url_for('log_item'))
        
    return render_template('init_inspection.html')

@app.route('/inspection/item', methods=['GET', 'POST'])
def log_item():
    """Step 2: Capture action items (photo, geolocation, voice notes)."""
    inspection_id = session.get('inspection_id')
    site_name = session.get('site_name')
    
    if not inspection_id:
        flash("No active inspection session. Please start a new inspection.", "warning")
        return redirect(url_for('init_inspection'))
    
    if request.method == 'POST':
        # Retrieve form data
        item_name = request.form.get('item_name', '').strip()
        latitude_str = request.form.get('latitude', '').strip()
        longitude_str = request.form.get('longitude', '').strip()
        status = request.form.get('status', 'not yet started').strip()
        transcript = request.form.get('transcript', '').strip()
        action = request.form.get('action', 'add_another')  # 'add_another' or 'complete'
        
        # Convert coordinates to Float/None
        try:
            latitude = float(latitude_str) if latitude_str else None
        except ValueError:
            latitude = None
            
        try:
            longitude = float(longitude_str) if longitude_str else None
        except ValueError:
            longitude = None

        if not item_name:
            return jsonify({'status': 'error', 'message': 'Item name is required.'}), 400
            
        # File Handling
        photo_files = request.files.getlist('photos')
        audio_file = request.files.get('audio')
        
        photo_paths = []
        audio_path_db = None
        
        # Save photo files (up to 5)
        for photo_file in photo_files[:5]:
            if photo_file and photo_file.filename:
                if allowed_file(photo_file.filename, ALLOWED_IMAGE_EXTENSIONS):
                    ext = os.path.splitext(secure_filename(photo_file.filename))[1]
                    if not ext:
                        ext = '.jpg'
                    photo_filename = f"photo_{uuid.uuid4().hex}{ext}"
                    photo_file.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_filename))
                    photo_paths.append(f"uploads/{photo_filename}")
                else:
                    return jsonify({'status': 'error', 'message': 'Invalid photo format.'}), 400
                    
        # Join photo file paths with a comma
        photo_path_db = ",".join(photo_paths) if photo_paths else None
                
        # Save audio file
        if audio_file and audio_file.filename:
            # MediaRecorder sends blob, typically webm or similar
            ext = os.path.splitext(secure_filename(audio_file.filename))[1]
            if not ext:
                ext = '.webm'
            audio_filename = f"audio_{uuid.uuid4().hex}{ext}"
            audio_file.save(os.path.join(app.config['UPLOAD_FOLDER'], audio_filename))
            audio_path_db = f"uploads/{audio_filename}"
            
        # Add to database
        db.add_inspection_item(
            inspection_id=inspection_id,
            item_name=item_name,
            photo_filepath=photo_path_db,
            latitude=latitude,
            longitude=longitude,
            audio_filepath=audio_path_db,
            status=status,
            transcript=transcript
        )
        
        # If complete, clear active session logger details
        if action == 'complete':
            session.pop('inspection_id', None)
            session.pop('site_name', None)
            
        return jsonify({
            'status': 'success',
            'message': 'Inspection item recorded successfully.',
            'action': action,
            'inspection_id': inspection_id
        })
        
    return render_template('log_item.html', site_name=site_name)

@app.route('/summaries')
def summaries():
    """Summary Mode Index: Lists completed inspections grouped by Site Name."""
    all_inspections = db.get_all_inspections()
    
    # Group by site name in a dictionary mapping site_name -> list of inspection rows
    grouped_inspections = {}
    for insp in all_inspections:
        site = insp['site_name']
        if site not in grouped_inspections:
            grouped_inspections[site] = []
        grouped_inspections[site].append(insp)
        
    return render_template('summaries.html', grouped_inspections=grouped_inspections)

@app.route('/summaries/<int:inspection_id>')
def detail(inspection_id):
    """Summary Mode Detail: View inspection info, coordinates on Leaflet, and photos/voice notes."""
    inspection = db.get_inspection(inspection_id)
    if not inspection:
        flash("Inspection not found.", "danger")
        return redirect(url_for('summaries'))
        
    items = db.get_inspection_items(inspection_id)
    
    # Format items to serializable dict for Leaflet script injection
    items_list = []
    for item in items:
        items_list.append({
            'id': item['id'],
            'item_name': item['item_name'],
            'photo_filepath': item['photo_filepath'],
            'latitude': item['latitude'],
            'longitude': item['longitude'],
            'audio_filepath': item['audio_filepath'],
            'status': item['status'],
            'transcript': item['transcript']
        })
        
    return render_template('detail.html', inspection=inspection, items=items, items_json=items_list)

@app.route('/clear_session')
def clear_session():
    """Clears the active session and redirects to homepage."""
    session.pop('inspection_id', None)
    session.pop('site_name', None)
    flash("Active inspection session cleared.", "info")
    return redirect(url_for('index'))

@app.route('/summaries/<int:inspection_id>/add_item')
def resume_inspection(inspection_id):
    """Resumes an inspection session to add items to an existing summary."""
    inspection = db.get_inspection(inspection_id)
    if not inspection:
        flash("Inspection not found.", "danger")
        return redirect(url_for('summaries'))
    
    session['inspection_id'] = inspection['id']
    session['site_name'] = inspection['site_name']
    return redirect(url_for('log_item'))

@app.route('/item/<int:item_id>/status', methods=['POST'])
def update_status(item_id):
    """AJAX endpoint to update the status of an inspection item."""
    status = request.form.get('status', '').strip()
    valid_statuses = {'logged and completed', 'in progress', 'not yet started'}
    if status not in valid_statuses:
        return jsonify({'status': 'error', 'message': 'Invalid status value.'}), 400
        
    db.update_item_status(item_id, status)
    return jsonify({'status': 'success', 'message': 'Status updated successfully.'})

@app.route('/summaries/<int:inspection_id>/delete', methods=['POST'])
def delete_report(inspection_id):
    """Deletes the inspection report and cleans up uploaded media files."""
    inspection = db.get_inspection(inspection_id)
    if not inspection:
        flash("Inspection not found.", "danger")
        return redirect(url_for('summaries'))
        
    items = db.get_inspection_items(inspection_id)
    
    # Delete files from disk
    for item in items:
        delete_item_media(item)
                    
    # Delete from database
    db.delete_inspection(inspection_id)
    flash(f"Inspection report for '{inspection['site_name']}' has been deleted.", "success")
    return redirect(url_for('summaries'))

@app.route('/item/<int:item_id>/delete', methods=['POST'])
def delete_item(item_id):
    """Deletes an individual inspection item and cleans up its media files."""
    item = db.get_inspection_item(item_id)
    
    if not item:
        flash("Item not found.", "danger")
        return redirect(url_for('summaries'))
        
    inspection_id = item['inspection_id']
    
    # Delete files from disk
    delete_item_media(item)
                
    # Delete database record
    db.delete_inspection_item(item_id)
    
    flash("Inspection item deleted successfully.", "success")
    return redirect(url_for('detail', inspection_id=inspection_id))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
