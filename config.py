import firebase_admin
from firebase_admin import credentials

# Initialize Firebase
cred = credentials.Certificate("parkflow-371ef-firebase-adminsdk-hge3z-7bf0223212.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://parkflow-371ef-default-rtdb.firebaseio.com/',
    'storageBucket': 'parkflow-371ef.appspot.com'
})
