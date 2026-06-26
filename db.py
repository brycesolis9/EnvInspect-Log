import sqlite3

DATABASE_PATH = 'inspection_logger.db'

def get_db_connection():
    """Establishes a connection to the SQLite database with Row factory."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    """Initializes the database schema if the tables do not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create Inspections parent table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Inspections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_name TEXT NOT NULL,
            inspection_date TEXT NOT NULL
        )
    ''')
    
    # Create InspectionItems child table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS InspectionItems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inspection_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            photo_filepath TEXT,
            latitude REAL,
            longitude REAL,
            audio_filepath TEXT,
            status TEXT DEFAULT 'not yet started',
            transcript TEXT,
            FOREIGN KEY (inspection_id) REFERENCES Inspections (id) ON DELETE CASCADE
        )
    ''')
    
    # Run migrations in case table was created without these columns
    try:
        cursor.execute("ALTER TABLE InspectionItems ADD COLUMN status TEXT DEFAULT 'not yet started';")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE InspectionItems ADD COLUMN transcript TEXT;")
    except sqlite3.OperationalError:
        pass
        
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

def create_inspection(site_name, inspection_date):
    """Inserts a new inspection and returns its ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO Inspections (site_name, inspection_date) VALUES (?, ?)",
        (site_name, inspection_date)
    )
    conn.commit()
    inspection_id = cursor.lastrowid
    conn.close()
    return inspection_id

def add_inspection_item(inspection_id, item_name, photo_filepath, latitude, longitude, audio_filepath, status='not yet started', transcript=None):
    """Inserts a new inspection item and returns its ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO InspectionItems (inspection_id, item_name, photo_filepath, latitude, longitude, audio_filepath, status, transcript)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (inspection_id, item_name, photo_filepath, latitude, longitude, audio_filepath, status, transcript)
    )
    conn.commit()
    item_id = cursor.lastrowid
    conn.close()
    return item_id

def get_all_inspections():
    """Retrieves all inspections sorted by site name and date."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Inspections ORDER BY site_name ASC, inspection_date DESC")
    inspections = cursor.fetchall()
    conn.close()
    return inspections

def get_inspection(inspection_id):
    """Retrieves a single inspection by its ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Inspections WHERE id = ?", (inspection_id,))
    inspection = cursor.fetchone()
    conn.close()
    return inspection

def get_inspection_items(inspection_id):
    """Retrieves all items associated with an inspection ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM InspectionItems WHERE inspection_id = ?", (inspection_id,))
    items = cursor.fetchall()
    conn.close()
    return items

def get_inspection_item(item_id):
    """Retrieves a single inspection item by its ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM InspectionItems WHERE id = ?", (item_id,))
    item = cursor.fetchone()
    conn.close()
    return item

def update_item_status(item_id, status):
    """Updates the status of an inspection item."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE InspectionItems SET status = ? WHERE id = ?",
        (status, item_id)
    )
    conn.commit()
    conn.close()

def delete_inspection_item(item_id):
    """Deletes an individual inspection item."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM InspectionItems WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()

def delete_inspection(inspection_id):
    """Deletes an inspection report."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM Inspections WHERE id = ?", (inspection_id,))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
