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

    if firebase_init_error:
        return jsonify({"error": f"Backend failed to initialize: {firebase_init_error}"}), 500

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
        event_data = event.to_dict()
        members = event_data.get('members', [])
        if user['uid'] in members:
            # Unjoin
            event_ref.update({
                'members': firestore.ArrayRemove([user['uid']]),
                'current_people': firestore.Increment(-1)
            })
            return jsonify({"status": "unjoined"}), 200
        else:
            # Join
            # Check capacity
            current_people = event_data.get('current_people', 0)
            max_people = int(event_data.get('max_people', 100)) # Default to 100 if missing
            
            if current_people >= max_people:
                return jsonify({"error": "Event is full"}), 400

            # Check if kicked
            if user['uid'] in event_data.get('kicked_users', []):
                return jsonify({"error": "You have been kicked from this event"}), 403

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

@app.route('/events/<event_id>/kick', methods=['POST'])
def kick_member(event_id):
    user = verify_token(request)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    target_uid = data.get('target_uid')
    if not target_uid:
        return jsonify({"error": "Target UID required"}), 400

    event_ref = db.collection('events').document(event_id)
    doc = event_ref.get()
    
    if not doc.exists:
        return jsonify({"error": "Event not found"}), 404
    
    event_data = doc.to_dict()
    
    # Only creator can kick
    if event_data.get('creator_uid') != user['uid']:
        return jsonify({"error": "Permission denied"}), 403
    
    if target_uid not in event_data.get('members', []):
        return jsonify({"error": "User not in event"}), 400

    event_ref.update({
        'members': firestore.ArrayRemove([target_uid]),
        'kicked_users': firestore.ArrayUnion([target_uid]),
        'current_people': firestore.Increment(-1)
    })
    
    return jsonify({"status": "kicked"}), 200

@app.route('/events/<event_id>/unblock', methods=['POST'])
def unblock_member(event_id):
    user = verify_token(request)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    target_uid = data.get('target_uid')
    if not target_uid:
        return jsonify({"error": "Target UID required"}), 400

    event_ref = db.collection('events').document(event_id)
    doc = event_ref.get()
    
    if not doc.exists:
        return jsonify({"error": "Event not found"}), 404
    
    event_data = doc.to_dict()
    
    # Only creator can unblock
    if event_data.get('creator_uid') != user['uid']:
        return jsonify({"error": "Permission denied"}), 403
    
    event_ref.update({
        'kicked_users': firestore.ArrayRemove([target_uid])
    })
    
    return jsonify({"status": "unblocked"}), 200

@app.route('/events/<event_id>/blocked', methods=['GET'])
def get_blocked_users(event_id):
    user = verify_token(request)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    event_ref = db.collection('events').document(event_id)
    doc = event_ref.get()
    
    if not doc.exists:
        return jsonify({"error": "Event not found"}), 404
        
    event_data = doc.to_dict()
    
    # Only creator can see blocked list
    if event_data.get('creator_uid') != user['uid']:
        return jsonify({"error": "Permission denied"}), 403
        
    blocked_uids = event_data.get('kicked_users', [])
    blocked_users = []
    
    for uid in blocked_uids:
        user_doc = db.collection('users').document(uid).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            blocked_users.append({
                'uid': uid,
                'name': user_data.get('name', 'Unknown'),
                'title': user_data.get('title', '')
            })
            
    return jsonify(blocked_users), 200

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

# --- FRIEND ROUTES ---
# --- FRIEND ROUTES ---
@app.route('/friends/request', methods=['POST'])
def send_friend_request():
    user = verify_token(request)
    if not user: return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    target_uid = data.get('target_uid')
    if not target_uid: return jsonify({"error": "Target UID required"}), 400
    
    # Check if already friends
    if db.collection('users').document(user['uid']).collection('friends').document(target_uid).get().exists:
        return jsonify({"error": "Already friends"}), 400

    # Add to target's friend_requests
    db.collection('users').document(target_uid).collection('friend_requests').document(user['uid']).set({
        'sender_uid': user['uid'],
        'sender_name': user.get('name', 'Unknown'),
        'timestamp': datetime.now().isoformat()
    })
    
    # Add to my sent_requests
    db.collection('users').document(user['uid']).collection('sent_requests').document(target_uid).set({
        'target_uid': target_uid,
        'timestamp': datetime.now().isoformat()
    })
    
    return jsonify({"message": "Request sent"}), 200

@app.route('/friends/accept', methods=['POST'])
def accept_friend_request():
    user = verify_token(request)
    if not user: return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    requester_uid = data.get('requester_uid')
    if not requester_uid: return jsonify({"error": "Requester UID required"}), 400
    
    # 1. Add to my friends
    db.collection('users').document(user['uid']).collection('friends').document(requester_uid).set({
        'added_at': datetime.now().isoformat()
    })
    
    # 2. Add me to their friends
    db.collection('users').document(requester_uid).collection('friends').document(user['uid']).set({
        'added_at': datetime.now().isoformat()
    })
    
    # 3. Delete request
    db.collection('users').document(user['uid']).collection('friend_requests').document(requester_uid).delete()
    
    # 4. Delete sent_request from requester
    db.collection('users').document(requester_uid).collection('sent_requests').document(user['uid']).delete()
    
    return jsonify({"message": "Friend accepted"}), 200

@app.route('/friends/reject', methods=['POST'])
def reject_friend_request():
    user = verify_token(request)
    if not user: return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    requester_uid = data.get('requester_uid')
    
    db.collection('users').document(user['uid']).collection('friend_requests').document(requester_uid).delete()
    # Also delete sent_request from requester
    db.collection('users').document(requester_uid).collection('sent_requests').document(user['uid']).delete()
    
    return jsonify({"message": "Request rejected"}), 200

@app.route('/friends/cancel_request', methods=['POST'])
def cancel_friend_request():
    user = verify_token(request)
    if not user: return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    target_uid = data.get('target_uid')
    
    # Delete from my sent_requests
    db.collection('users').document(user['uid']).collection('sent_requests').document(target_uid).delete()
    # Delete from target's friend_requests
    db.collection('users').document(target_uid).collection('friend_requests').document(user['uid']).delete()
    
    return jsonify({"message": "Request cancelled"}), 200

@app.route('/friends/requests', methods=['GET'])
def get_friend_requests():
    user = verify_token(request)
    if not user: return jsonify({"error": "Unauthorized"}), 401
    
    reqs_ref = db.collection('users').document(user['uid']).collection('friend_requests').stream()
    requests = []
    for doc in reqs_ref:
        requests.append(doc.to_dict())
        
    return jsonify(requests), 200

@app.route('/friends/sent_requests', methods=['GET'])
def get_sent_requests():
    user = verify_token(request)
    if not user: return jsonify({"error": "Unauthorized"}), 401
    
    sent_ref = db.collection('users').document(user['uid']).collection('sent_requests').stream()
    sent_requests = []
    
    for doc in sent_ref:
        data = doc.to_dict()
        target_uid = data.get('target_uid')
        
        # Fetch target profile for display
        target_doc = db.collection('users').document(target_uid).get()
        if target_doc.exists:
            target_data = target_doc.to_dict()
            sent_requests.append({
                'target_uid': target_uid,
                'name': target_data.get('name', 'Unknown'),
                'title': target_data.get('title', '')
            })
            
    return jsonify(sent_requests), 200

@app.route('/friends/<friend_uid>', methods=['DELETE'])
def remove_friend(friend_uid):
    user = verify_token(request)
    if not user: return jsonify({"error": "Unauthorized"}), 401
    
    # Remove from both sides
    db.collection('users').document(user['uid']).collection('friends').document(friend_uid).delete()
    db.collection('users').document(friend_uid).collection('friends').document(user['uid']).delete()
    
    return jsonify({"message": "Friend removed"}), 200

@app.route('/friends', methods=['GET'])
def get_friends():
    user = verify_token(request)
    if not user: return jsonify({"error": "Unauthorized"}), 401
    
    friends_ref = db.collection('users').document(user['uid']).collection('friends').stream()
    friends_list = []
    
    for doc in friends_ref:
        friend_uid = doc.id
        # Fetch friend profile
        friend_doc = db.collection('users').document(friend_uid).get()
        if not friend_doc.exists: continue
        
        friend_data = friend_doc.to_dict()
        
        # Check activity (simple query for now)
        # Find events where this friend is a member
        events_ref = db.collection('events').where('members', 'array_contains', friend_uid).limit(1).stream()
        active_event = None
        for evt in events_ref:
            active_event = evt.to_dict().get('title')
            
        friends_list.append({
            'uid': friend_uid,
            'name': friend_data.get('name', 'Unknown'),
            'title': friend_data.get('title', ''),
            'active_event': active_event
        })
        
    return jsonify(friends_list), 200

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

# --- DIRECT MESSAGE ROUTES ---
@app.route('/friends/<friend_uid>/chat', methods=['GET'])
def get_friend_messages(friend_uid):
    user = verify_token(request)
    if not user: return jsonify({"error": "Unauthorized"}), 401
    
    # Deterministic Chat ID
    chat_id = '_'.join(sorted([user['uid'], friend_uid]))
    
    messages_ref = db.collection('direct_messages').document(chat_id).collection('messages').order_by('timestamp').stream()
    messages = []
    for doc in messages_ref:
        data = doc.to_dict()
        data['id'] = doc.id
        messages.append(data)
        
    return jsonify(messages), 200

@app.route('/friends/<friend_uid>/chat', methods=['POST'])
def send_friend_message(friend_uid):
    user = verify_token(request)
    if not user: return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    message = data.get('message')
    if not message: return jsonify({"error": "Message required"}), 400
    
    # Deterministic Chat ID
    chat_id = '_'.join(sorted([user['uid'], friend_uid]))
    
    msg_data = {
        'sender_uid': user['uid'],
        'sender_name': user.get('name', 'Anonymous'),
        'message': message,
        'timestamp': datetime.now().isoformat()
    }
    
    db.collection('direct_messages').document(chat_id).collection('messages').add(msg_data)
    return jsonify(msg_data), 201

# --- CHAT ROUTES ---
@app.route('/events/<event_id>/chat', methods=['GET'])
def get_chat_messages(event_id):
    user = verify_token(request)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    # Verify membership
    event_ref = db.collection('events').document(event_id)
    event = event_ref.get()
    if not event.exists:
        return jsonify({"error": "Event not found"}), 404
    
    if user['uid'] not in event.to_dict().get('members', []) and event.to_dict().get('creator_uid') != user['uid']:
        return jsonify({"error": "Not a member"}), 403

    # Fetch messages
    messages_ref = db.collection('events').document(event_id).collection('messages').order_by('timestamp').stream()
    messages = []
    for doc in messages_ref:
        data = doc.to_dict()
        data['id'] = doc.id
        messages.append(data)
    
    return jsonify(messages), 200

@app.route('/events/<event_id>/chat', methods=['POST'])
def send_chat_message(event_id):
    user = verify_token(request)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    # Verify membership
    event_ref = db.collection('events').document(event_id)
    event = event_ref.get()
    if not event.exists:
        return jsonify({"error": "Event not found"}), 404
    }

    db.collection('events').document(event_id).collection('messages').add(msg_data)
    return jsonify(msg_data), 201

if __name__ == '__main__':
    app.run(debug=True, port=5001)
