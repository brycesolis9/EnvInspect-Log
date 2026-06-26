import unittest
import os
import sqlite3
from io import BytesIO
import app
import db

class TestEnvironmentalLogger(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # Point to a test database instead of production
        db.DATABASE_PATH = 'test_inspection_logger.db'
        app.app.config['TESTING'] = True
        app.app.config['WTF_CSRF_ENABLED'] = False
        db.init_db()
        
    @classmethod
    def tearDownClass(cls):
        if os.path.exists('test_inspection_logger.db'):
            try:
                os.remove('test_inspection_logger.db')
            except PermissionError:
                pass # SQLite might still lock it on Windows, which is fine to clean up later

    def setUp(self):
        # Clear tables instead of recreating the file to prevent Windows locking errors
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM InspectionItems")
        cursor.execute("DELETE FROM Inspections")
        conn.commit()
        conn.close()
        self.client = app.app.test_client()

    def test_landing_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Environmental Inspector', response.data)

    def test_initialize_inspection(self):
        # Test GET new inspection page
        response = self.client.get('/inspection/new')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Initialize Inspection', response.data)
        
        # Test POST creation with valid data
        response = self.client.post('/inspection/new', data={
            'site_name': 'Test River Sector',
            'inspection_date': '2026-06-19'
        }, follow_redirects=True)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Log Action Item', response.data)
        self.assertIn(b'Test River Sector', response.data)

    def test_log_item_without_session(self):
        # Without session, should redirect to start page
        response = self.client.get('/inspection/item', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Initialize Inspection', response.data)

    def test_add_inspection_item_ajax(self):
        # Seed an inspection in the database first to satisfy FK constraint
        inspection_id = db.create_inspection("Test River Sector", "2026-06-19")
        
        # Start session with this seeded inspection ID
        with self.client as c:
            with c.session_transaction() as sess:
                sess['inspection_id'] = inspection_id
                sess['site_name'] = 'Test River Sector'
                
            # Create a mock photo and audio
            photo_data = (BytesIO(b'my_mock_photo_content'), 'test_image.jpg')
            audio_data = (BytesIO(b'my_mock_audio_content'), 'test_audio.webm')
            
            # Post AJAX request to log_item
            response = c.post('/inspection/item', data={
                'item_name': 'Eroded Embankment',
                'latitude': '40.7128',
                'longitude': '-74.0060',
                'photos': [photo_data],
                'audio': audio_data,
                'transcript': 'This is a sample audio transcript description.',
                'action': 'add_another'
            }, content_type='multipart/form-data')
            
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertEqual(data['status'], 'success')
            self.assertEqual(data['action'], 'add_another')
            
            # Assert item was recorded in database with the transcript
            items = db.get_inspection_items(inspection_id)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]['item_name'], 'Eroded Embankment')
            self.assertEqual(items[0]['transcript'], 'This is a sample audio transcript description.')

    def test_summaries_routing(self):
        # Seed an inspection
        insp_id = db.create_inspection("East Outfall", "2026-06-18")
        db.add_inspection_item(insp_id, "Trash accumulation", "uploads/mock.jpg", 34.0522, -118.2437, "uploads/mock.webm", status='not yet started', transcript='Sample transcript text here.')
        
        # Test index summaries
        response = self.client.get('/summaries')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'East Outfall', response.data)
        
        # Test detail page
        response = self.client.get(f'/summaries/{insp_id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'East Outfall', response.data)
        self.assertIn(b'Trash accumulation', response.data)
        self.assertIn(b'Sample transcript text here.', response.data)

    def test_update_item_status(self):
        # Seed inspection and item
        insp_id = db.create_inspection("South Shore", "2026-06-17")
        item_id = db.add_inspection_item(insp_id, "Chemical waste", "uploads/waste.jpg", 10.0, 20.0, "uploads/waste.webm")
        
        # Verify initial status is 'not yet started'
        items = db.get_inspection_items(insp_id)
        self.assertEqual(items[0]['status'], 'not yet started')
        
        # POST to status update route
        response = self.client.post(f'/item/{item_id}/status', data={
            'status': 'in progress'
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'success')
        
        # Verify status is now 'in progress'
        items = db.get_inspection_items(insp_id)
        self.assertEqual(items[0]['status'], 'in progress')

    def test_delete_inspection_report(self):
        # Create actual temp files in static/uploads to check physical deletion
        os.makedirs(app.UPLOAD_FOLDER, exist_ok=True)
        photo_filename = "test_delete_photo.jpg"
        audio_filename = "test_delete_audio.webm"
        photo_path = os.path.join(app.UPLOAD_FOLDER, photo_filename)
        audio_path = os.path.join(app.UPLOAD_FOLDER, audio_filename)
        
        with open(photo_path, 'w') as f:
            f.write("mock_photo")
        with open(audio_path, 'w') as f:
            f.write("mock_audio")
            
        self.assertTrue(os.path.exists(photo_path))
        self.assertTrue(os.path.exists(audio_path))
        
        # Seed DB
        insp_id = db.create_inspection("Temporary Site", "2026-06-19")
        db.add_inspection_item(
            inspection_id=insp_id,
            item_name="Erosion point",
            photo_filepath=f"uploads/{photo_filename}",
            latitude=1.0,
            longitude=2.0,
            audio_filepath=f"uploads/{audio_filename}"
        )
        
        # POST delete report
        response = self.client.post(f'/summaries/{insp_id}/delete', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        # Assert database rows are deleted
        self.assertIsNone(db.get_inspection(insp_id))
        self.assertEqual(len(db.get_inspection_items(insp_id)), 0)
        
        # Assert files are deleted from disk
        self.assertFalse(os.path.exists(photo_path))
        self.assertFalse(os.path.exists(audio_path))

    def test_delete_individual_item(self):
        # Create temp files
        os.makedirs(app.UPLOAD_FOLDER, exist_ok=True)
        photo_filename = "test_delete_item_photo.jpg"
        audio_filename = "test_delete_item_audio.webm"
        photo_path = os.path.join(app.UPLOAD_FOLDER, photo_filename)
        audio_path = os.path.join(app.UPLOAD_FOLDER, audio_filename)
        
        with open(photo_path, 'w') as f:
            f.write("mock")
        with open(audio_path, 'w') as f:
            f.write("mock")
            
        # Seed DB
        insp_id = db.create_inspection("Keep Site", "2026-06-19")
        item_id = db.add_inspection_item(
            inspection_id=insp_id,
            item_name="Erosion",
            photo_filepath=f"uploads/{photo_filename}",
            latitude=1.0,
            longitude=2.0,
            audio_filepath=f"uploads/{audio_filename}"
        )
        
        # POST delete individual item
        response = self.client.post(f'/item/{item_id}/delete', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        # Verify parent report remains, but item is deleted
        self.assertIsNotNone(db.get_inspection(insp_id))
        self.assertEqual(len(db.get_inspection_items(insp_id)), 0)
        
        # Verify files are deleted
        self.assertFalse(os.path.exists(photo_path))
        self.assertFalse(os.path.exists(audio_path))

if __name__ == '__main__':
    unittest.main()
