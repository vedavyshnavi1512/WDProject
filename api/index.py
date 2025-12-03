import os
import json
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file

from flask import Flask, request, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore, auth
from datetime import datetime
import requests

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# Initialize Firebase
firebase_init_error = None
try:
    if os.environ.get('FIREBASE_CREDENTIALS'):
        cred = credentials.Certificate(json.loads(os.environ.get('FIREBASE_CREDENTIALS')))
    else:
        cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    firebase_init_error = str(e)
    print(f"Firebase Init Error: {e}")
    db = None

# --- MIDDLEWARE: Verify Token ---
def verify_token(req):
    """Checks for 'Authorization' header and verifies it with Firebase"""
    if firebase_init_error:
        print(f"Auth Error: Backend failed to initialize - {firebase_init_error}")
        return None

    token = req.headers.get('Authorization')
    if not token:
        print("Auth Error: No Authorization header found")
        return None
    try:
        decoded_token = auth.verify_id_token(token)
        print(f"Auth Success: User {decoded_token['uid']}")
        return decoded_token
    except Exception as e:
        print(f"Auth Error: Token verification failed - {e}")
        return None

# --- AUTH ROUTES ---
RECAPTCHA_SECRET = os.environ.get("RECAPTCHA_SECRET")

def verify_recaptcha(token):
    if not token:
        print("DEBUG: No CAPTCHA token provided")
        return False
    
    if not RECAPTCHA_SECRET:
        print("DEBUG: RECAPTCHA_SECRET is missing! Make sure to set the environment variable.")
        return False

    payload = {'secret': RECAPTCHA_SECRET, 'response': token}
    try:
        r = requests.post("https://www.google.com/recaptcha/api/siteverify", data=payload)
        result = r.json()
        print(f"DEBUG: Recaptcha verification result: {result}")
        return result.get("success", False)
    except Exception as e:
        print(f"DEBUG: Recaptcha request failed: {e}")
        return False

@app.route('/auth/signup', methods=['POST'])
def signup():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    name = data.get('name')
    captcha_token = data.get('captcha_token')

    if not verify_recaptcha(captcha_token):
        return jsonify({"error": "Invalid CAPTCHA"}), 400

    try:
        # Create user in Firebase
        user = auth.create_user(
            email=email,
            password=password,
            display_name=name
        )
        # Generate custom token for client to sign in
        custom_token = auth.create_custom_token(user.uid)
        
        # Create user document in Firestore
        try:
            db.collection('users').document(user.uid).set({
                'name': name,
                'email': email,
                'created_at': datetime.now(),
                'bio': '',
                'title': ''
            })
        except Exception as db_e:
            print(f"Error creating user doc: {db_e}")
            # Continue anyway, token is generated
            
        return jsonify({"token": custom_token.decode('utf-8')}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    captcha_token = data.get('captcha_token')

    if not verify_recaptcha(captcha_token):
        return jsonify({"error": "Invalid CAPTCHA"}), 400

    try:

        API_KEY = os.environ.get("FIREBASE_API_KEY")
        verify_password_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"
        payload = {"email": email, "password": password, "returnSecureToken": True}
        res = requests.post(verify_password_url, json=payload)
        
        if res.status_code != 200:
            return jsonify({"error": "Invalid email or password"}), 401
            
        user_info = res.json()
        uid = user_info['localId']
        custom_token = auth.create_custom_token(uid)
        return jsonify({"token": custom_token.decode('utf-8')}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 400

from flask import send_file

@app.route('/', methods=['GET'])
def home():
    return send_file('../index.html')

@app.route('/health', methods=['GET'])
def health():
    if firebase_init_error:
        return jsonify({"status": "error", "message": firebase_init_error}), 500
    return jsonify({"status": "ok"}), 200

# --- MOCK DATA ---
MOCK_EVENTS = [
    {
        "id": "mock-1",
        "title": "Badminton Doubles (Mock)",
        "category": "Sports",
        "location": "Rec Center",
        "max_people": 4,
        "current_people": 1,
        "event_date": "2024-12-25",
        "event_time": "18:00",
        "created_at": "2024-12-03T12:00:00",
        "creator_name": "Mock User",
        "creator_uid": "mock-uid",
        "members": ["mock-uid"]
    },
    {
        "id": "mock-2",
        "title": "Late Night Study (Mock)",
        "category": "Study",
        "location": "Library",
        "max_people": 6,
        "current_people": 3,
        "event_date": "2024-12-26",
        "event_time": "20:00",
        "created_at": "2024-12-03T14:00:00",
        "creator_name": "Alice",
        "creator_uid": "mock-alice",
        "members": ["mock-alice"]
    },
    {
        "id": "mock-3",
        "title": "Morning Coffee (Mock)",
        "category": "Coffee",
        "location": "Campus Cafe",
        "max_people": 10,
        "current_people": 5,
        "event_date": "2024-12-27",
        "event_time": "09:00",
        "created_at": "2024-12-03T08:00:00",
        "creator_name": "Bob",
        "creator_uid": "mock-bob",
        "members": ["mock-bob"]
    }
]

# --- PUBLIC ROUTES ---
@app.route('/events', methods=['GET'])
def get_events():
    if firebase_init_error:
        return jsonify({"error": f"Backend Init Failed: {firebase_init_error}"}), 500
    try:
        events_ref = db.collection('events').order_by('created_at', direction=firestore.Query.DESCENDING)
        docs = events_ref.stream()
        events = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            events.append(data)
        return jsonify(events), 200
    except Exception as e:
        print(f"Error fetching events: {e}")
        return jsonify({"error": str(e)}), 500

# --- PROTECTED ROUTES ---
@app.route('/events', methods=['POST'])
def create_event():
    user = verify_token(request) # 1. Verify User
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    new_event = {
        'title': data.get('title'),
        'category': data.get('category'),
        'location': data.get('location'),
        'max_people': int(data.get('max_people')),
        'current_people': 1,
        'event_date': data.get('event_date'),
        'event_time': data.get('event_time'),
        'created_at': datetime.now(),
        'creator_name': user.get('name', 'Unknown'), # Use name from token
        'creator_uid': user['uid'],
        'members': [user['uid']]
    }
    db.collection('events').add(new_event)
    return jsonify({"message": "Created"}), 201

@app.route('/join', methods=['POST'])
def join_event():
    user = verify_token(request)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    event_ref = db.collection('events').document(data.get('event_id'))
    event = event_ref.get()

    if event.exists:
        members = event.to_dict().get('members', [])
        if user['uid'] in members:
            # Unjoin
            event_ref.update({
                'members': firestore.ArrayRemove([user['uid']]),
                'current_people': firestore.Increment(-1)
            })
            return jsonify({"status": "unjoined"}), 200
        else:
            # Join
            event_ref.update({
                'members': firestore.ArrayUnion([user['uid']]),
                'current_people': firestore.Increment(1)
            })
            return jsonify({"status": "joined"}), 200
    return jsonify({"error": "Not found"}), 404

@app.route('/events/<event_id>', methods=['DELETE'])
def delete_event(event_id):
    user = verify_token(request)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
        
    event_ref = db.collection('events').document(event_id)
    doc = event_ref.get()
    
    # Check if the requester is the creator
    if doc.exists and doc.to_dict().get('creator_uid') == user['uid']:
        event_ref.delete()
        return jsonify({"message": "Deleted"}), 200
    
    return jsonify({"error": "Permission denied"}), 403

@app.route('/events/<event_id>/members', methods=['GET'])
def get_event_members(event_id):
    try:
        event_ref = db.collection('events').document(event_id)
        event = event_ref.get()
        
        if not event.exists:
            return jsonify({"error": "Event not found"}), 404
            
        member_uids = event.to_dict().get('members', [])
        members_data = []
        
        # Batch fetch users would be better, but for now loop is fine for small scale
        # Or use 'in' query if list is small (<10)
        
        if not member_uids:
             return jsonify([]), 200

        # Fetch up to 10 members at a time or just loop (simple for now)
        for uid in member_uids:
            user_doc = db.collection('users').document(uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                members_data.append({
                    "uid": uid,
                    "name": user_data.get('name', 'Unknown User'),
                    "title": user_data.get('title', '')
                })
            else:
                members_data.append({
                    "uid": uid,
                    "name": "Unknown User",
                    "title": ""
                })
                
        return jsonify(members_data), 200
    except Exception as e:
        print(f"Error fetching members: {e}")
        return jsonify({"error": str(e)}), 500

# --- REVIEW ROUTES ---
@app.route('/reviews', methods=['POST'])
def add_review():
    user = verify_token(request)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    target_uid = data.get('target_uid')
    rating = data.get('rating')
    comment = data.get('comment')

    if not all([target_uid, rating, comment]):
        return jsonify({"error": "Missing fields"}), 400

    review = {
        'reviewer_uid': user['uid'],
        'reviewer_name': user.get('name', 'Anonymous'),
        'target_uid': target_uid,
        'rating': int(rating),
        'comment': comment,
        'created_at': datetime.now()
    }

    db.collection('reviews').add(review)
    return jsonify({"message": "Review added"}), 201

@app.route('/reviews/<review_id>', methods=['DELETE'])
def delete_review(review_id):
    user = verify_token(request)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    review_ref = db.collection('reviews').document(review_id)
    doc = review_ref.get()

    if doc.exists:
        if doc.to_dict().get('reviewer_uid') == user['uid']:
            review_ref.delete()
            return jsonify({"message": "Review deleted"}), 200
        else:
            return jsonify({"error": "Permission denied"}), 403
    
    return jsonify({"error": "Not found"}), 404

# --- USER PROFILE ROUTES ---
@app.route('/users/<user_id>', methods=['GET'])
def get_user_profile(user_id):
    user_ref = db.collection('users').document(user_id)
    doc = user_ref.get()
    if doc.exists:
        return jsonify(doc.to_dict()), 200
    return jsonify({}), 200 # Return empty if not found (first time)

@app.route('/users/profile', methods=['POST'])
def update_user_profile():
    user = verify_token(request)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    # Merge with existing data
    user_ref = db.collection('users').document(user['uid'])
    user_ref.set(data, merge=True)
    
    return jsonify({"message": "Profile updated"}), 200

@app.route('/reviews/<user_id>', methods=['GET'])
def get_reviews(user_id):
    reviews_ref = db.collection('reviews').where('target_uid', '==', user_id).stream()
    
    reviews = []
    total_rating = 0
    count = 0

    for doc in reviews_ref:
        data = doc.to_dict()
        data['id'] = doc.id
        reviews.append(data)
        total_rating += data.get('rating', 0)
        count += 1

    avg_rating = round(total_rating / count, 1) if count > 0 else 0

    return jsonify({
        "reviews": reviews,
        "average_rating": avg_rating,
        "total_reviews": count
    }), 200

if __name__ == '__main__':
    app.run(debug=True, port=5001)
