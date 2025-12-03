import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# Initialize Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

events = [
    {
        'title': 'Pickup Basketball 3v3',
        'category': 'Sports',
        'location': 'Rec Center Courts',
        'max_people': 6,
        'current_people': 4,
        'created_at': datetime.now(),
        'creator_name': 'Felix Chen',
        'creator_uid': 'system_demo_user',
        'members': ['system_demo_user']
    },
    {
        'title': 'Finals Chem Review',
        'category': 'Study',
        'location': 'Library, Room 304',
        'max_people': 10,
        'current_people': 8,
        'created_at': datetime.now(),
        'creator_name': 'Sarah Smith',
        'creator_uid': 'system_demo_user_2',
        'members': ['system_demo_user_2']
    }
]

for event in events:
    db.collection('events').add(event)
    print(f"Added event: {event['title']}")
