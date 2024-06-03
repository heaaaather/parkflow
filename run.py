from YOLOv8_webcam import object_detection
from flask import Flask, Response, render_template, request, session, redirect, url_for, send_file, jsonify, current_app as app, flash
import os
import firebase_admin
from firebase_admin import db, firestore, storage, auth
from config import cred
from flask_session import Session
from datetime import datetime, timedelta
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
import pdfkit
import base64

# ---------{ INITIATE THE FLASK APP }--------- #
app = Flask(__name__)
app.secret_key = '1369a861a5796e353aeff1d359829995e5ed2ef431a476e3'  # Set a secret key for session management
bcrypt = Bcrypt(app)


# ---------{ ACCESS FIREBASE REALTIME DATABASE }--------- #
database = db.reference()
bucket = storage.bucket()


# ---------{ DEFINE THE ARRAY VARIABLES & DIRECTORIES }--------- #
# Directory to save ROI and Images
ROI_DIR = os.path.join('static', 'roi')
os.makedirs(ROI_DIR, exist_ok=True)

fee_mapping = {
    'regular': 'regular_fee',
    'overnight': 'overnight_fee'
}




# ---------{ DEFINE THE FUNCTIONS }--------- #
# (((( Define the function to set session variables )))
def set_session(user_id, email, role, name=None, license=None):
    session['id'] = user_id
    session['email'] = email
    session['role'] = role
    session['logged_in'] = True

    if name:
        session['name'] = name
    if license:
        session['license'] = license

# (((( Function to check if the user is logged in and has the specified role )))
def check_role(role):
    return 'id' in session and session.get('role') == role

# (((( Function to fetch user data from the database )))
def fetch_user_data(user_id):
    user_ref = database.child('tbl_staffaccount').child(user_id)
    user_data = user_ref.get()

    if user_data is None:
        user_ref = database.child('tbl_customerAcc').child(user_id)
        user_data = user_ref.get()
        if user_data:
            user_data['role'] = 'customer'
    else:
        user_data['role'] = 'staff'
    
    return user_data


# (((( Function to add entry transaction to the database ))) ------ THIS IS THE START OF THE FUNCTIONS FOR PARKING MANAGEMENT
def add_entry_transaction(transaction_id, license_plate, customer_name, entry_date, entry_time):
    parking_entries_ref = database.child('tbl_parking_entries')

    entry_data = {
        'transaction_id': transaction_id,
        'license_plate': license_plate,
        'customer_name': customer_name,
        'entry_date': entry_date,
        'entry_time': entry_time,
        'payment_status':'Pending'
    }

     # Use the provided transaction ID as the key
    parking_entries_ref.child(transaction_id).set(entry_data)

# (((( Function to retrieve the latest entry transaction for a customer )))
def get_latest_entry_transaction(license_plate):
    parking_entries_ref = database.child('tbl_parking_entries')

    query = parking_entries_ref.order_by_child('license_plate').equal_to(license_plate).limit_to_last(1)
    result = query.get()

    if result:
        return list(result.values())[0]
    else:
        return None

# (((( Function to get the latest transaction ID )))
def get_latest_entry_transaction_id():
    root_ref = db.reference()
    parking_entries_ref = root_ref.child('tbl_parking_entries')

    latest_entry = parking_entries_ref.order_by_key().limit_to_last(1).get()

    if latest_entry:
        latest_entry_data = list(latest_entry.values())[0]
        if 'transaction_id' in latest_entry_data:
            latest_transaction_id = int(latest_entry_data['transaction_id'][2:])
            return latest_transaction_id + 1
        else:
            print("Warning: 'transaction_id' not found in latest entry data.")
            # Handle missing 'transaction_id' gracefully, e.g., return a default value
            return 100000
    else:
        print("No latest entry found in database.")
        # Handle case where no entry is found gracefully, e.g., return a default value
        return 100000

# (((( Function to retrive the fees )))
def get_fee_values():
    fee_ref = database.child('tbl_fees').get()
    return fee_ref
    
# (((( Function to calculate parking fee based on duration and parking type )))
def calculate_parking_fee(duration_hours, lost_parking_pass_checked):
    total_fee = 0

    # Retrieve fee values from Firebase
    fee_values = get_fee_values()

    regular_fee = float(fee_values.get('flat_rate', 0))
    lost_ticket_fee = float(fee_values.get('lost_ticket_pass', 0))
    overnight_fee = float(fee_values.get('overnight_rate', 0))

    if duration_hours <= 24:
        total_fee = regular_fee
        if lost_parking_pass_checked:
            total_fee += lost_ticket_fee  # Add lost parking pass fee if checked
        return total_fee  # regular parking fee for less than or equal to 24 hours
    elif duration_hours <= 48:
        total_fee = overnight_fee
        if lost_parking_pass_checked:
            total_fee += lost_ticket_fee  # Add lost parking pass fee if checked
        return total_fee  # base fee for overnight parking (1 day)
    else:
        # calculate the number of days (including any extra hours)
        num_days = duration_hours // 24

        # if there are extra hours beyond the last complete day, count as an additional day
        if duration_hours % 24 > 0:
            num_days += 1

        # calculate the total parking fee
        total_fee = overnight_fee * num_days  # base fee multiplied by the number of days
        if lost_parking_pass_checked:
            total_fee += lost_ticket_fee * num_days  # Add lost parking pass fee for each day if checked
        
        return total_fee
    
# (((( Function to add and update entry transaction to the database )))
def add_exit_transaction(license_plate, exit_date, exit_time, duration, parking_type, lost_parking_pass_fee, total_fee):
    # retrieve the latest entry transaction for the given license plate
    latest_entry_transaction = get_latest_entry_transaction(license_plate)
    
    if latest_entry_transaction:
        # update entry transaction with exit details, duration, parking type, lost parking pass fee, and total fee
        exit_data = {
            'exit_date': exit_date,
            'exit_time': exit_time,
            'duration': duration,
            'parking_type': parking_type,
            'lost_parking_pass_fee': lost_parking_pass_fee,
            'total_fee': total_fee,  # Store total fee
            'payment_status': 'Paid' # update payment status to 'paid'
        }

        # construct path to the entry transaction node in the database
        entry_transaction_id = latest_entry_transaction['transaction_id']
        entry_transaction_path = f'tbl_parking_entries/{entry_transaction_id}'

        # update the entry transaction with exit details, duration, parking type, lost parking pass fee, and total fee
        entry_transaction_ref = database.child(entry_transaction_path)
        entry_transaction_ref.update(exit_data)
    else:
        print("No entry transaction found for the given license plate.")


# (((( Function to get the customer name based on the roi_text )))
def get_customer_name(roi_text):
    try:
        customer_account_ref = database.child('tbl_customerAcc')

        # Query Firebase for customer with matching ROI Text
        query = customer_account_ref.order_by_child('license').equal_to(roi_text).get()

        if query:
            customer_data = list(query.values())[0]
            full_name = f"{customer_data['fname']} {customer_data['lname']}"
            return full_name
        else:
            print(f"No customer found for ROI text: {roi_text}")
            return "Guest"
    except Exception as e:
        print(f"Error occurred while fetching customer data: {str(e)}")
        return "Guest"
    
# (((( Define the function to log staff actions )))
def log_action(action_location, action_message):
    ref = database.child('tbl_logs')
    log_count = ref.get()
    log_id = len(log_count) + 1 if log_count else 1
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ref.child(str(log_id)).set({
        'staffID': session['id'],
        'actionLocation': action_location,
        'actionMessage': action_message,
        'actionTime': current_time
    })

# Handle image upload
def handle_image_upload(image, user_id):
    if image.filename != '':
        image_ext = os.path.splitext(image.filename)[1].lower()
        if image_ext not in ['.jpg', '.jpeg', '.png']:
            flash('Invalid Image Extension')
            return None

        if len(image.read()) > 1200000:
            flash('Image Size Is Too Large')
            return None
        
        # Reset file pointer to the beginning
        image.seek(0)

        new_image_name = f"{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{image_ext}"
        blob = bucket.blob(new_image_name)
        blob.upload_from_file(image)
        
        return new_image_name

    


    








# ---------{ DEFINE THE ROUTES }--------- #
@app.route('/') # ------ THIS IS THE START OF THE FUNCTION FOR RENDERING INDEX TEMPLATE
def index():
    ### does not need any session since this is the landing page ###
    return render_template('index.html')

@app.route('/login_page_redirect') # ------ THIS IS THE START OF THE FUNCTION FOR LOGINS AND CREATE ACCOUNT
def login_page_redirect():
    ### this function is used to load the login page template named login_new.html ###
    return render_template('login_new.html')

@app.route('/login', methods=['POST'])
def login():
    ### this function is used when login button is clicked to identify account ###
    if 'login-btn' in request.form:
        email = request.form['email']
        account_password = request.form['password']

        # check the staff account if it is 'admin' or 'cashier'
        reference = database.child('tbl_staffaccount').order_by_child('emailAddress').equal_to(email).get()
        if reference:
            for key, value in reference.items():
                if value['accountPassword'] == account_password:
                    set_session(key, email, value['staffPosition'], value['firstName'])

                    # redirect based on role
                    if value['staffPosition'] == 'admin':
                        set_session(key, email, value['staffPosition'], value['firstName'])
                        session['logged_in'] = True  # Set session variable after successful login
                        return redirect(url_for('dashboard'))
                    elif value['staffPosition'] == 'cashier':
                        set_session(key, email, value['staffPosition'], value['firstName'])
                        session['logged_in'] = True  # Set session variable after successful login
                        return redirect(url_for('dashboardCashier'))

                    
        # check customer accounts
        reference = database.child('tbl_customerAcc').order_by_child('email').equal_to(email).get()
        if reference:
            for key, value in reference.items():
                if value['passcode'] == account_password:
                    set_session(key, email, 'customer', value['fname'], value.get('license', []))
                    return redirect(url_for('homepage'))
                
        # if invalid email or password
        session['status'] = "Invalid email or password. Please try again."
        return redirect(url_for('login_page_redirect'))
    
    # if it is not a POST request, just render the login template
    return render_template('login_new.html', logged_in=False)

@app.route('/create_account', methods=['POST'])
def create_account():
    if request.method == 'POST':
        first_name = request.form['fname']
        last_name = request.form['lname']
        email = request.form['email']
        password = request.form['passcode']
        license_plate = request.form['license']

        try:
            # Check if the email already exists in staff or customer accounts
            staff_ref = database.child('tbl_staffaccount').order_by_child('email').equal_to(email).get()
            customer_ref = database.child('tbl_customerAcc').order_by_child('email').equal_to(email).get()

            if staff_ref or customer_ref:
                session['status'] = "Email already exists."
                return redirect(url_for('login_page_redirect'))

            # Create a new customer account
            user_data = {
                'fname': first_name,
                'lname': last_name,
                'email': email,
                'passcode': password,
                'license': license_plate
            }

            # Add the user data to the database
            user_ref = database.child('tbl_customerAcc').push(user_data)

            # Set session variables
            set_session(user_ref.key, email, 'customer', first_name, license_plate)

            # Redirect to the homepage
            return redirect(url_for('homepage'))

        except Exception as e:
            session['status'] = f"User registration failed: {str(e)}"
            return redirect(url_for('login_page_redirect'))

    return redirect(url_for('login_page_redirect'))





@app.route('/homepage') # ------ THIS IS THE START OF THE FUNCTION FOR REDIRECTING TO CUSTOMER PAGES
def homepage():
    # Check if the user is logged in and has the role of 'customer'
    if 'logged_in' not in session or session.get('role') != 'customer':
        return redirect(url_for('login_page_redirect'))

    # Retrieve customer information from the database
    user_id = session.get('id')
    customer_info = fetch_user_data(user_id)

    # Render the homepage template with the customer information
    return render_template('homepage.html', customer_info=customer_info, logged_in=session.get('logged_in', False))



### add map
@app.route('/about_us')
def about_us():
    # Check if the user is logged in and has the role of 'customer'
    if 'logged_in' not in session or session.get('role') != 'customer':
        return redirect(url_for('login_page_redirect'))

    # Retrieve customer information from the database
    user_id = session.get('id')
    customer_info = fetch_user_data(user_id)

    return render_template('about.html', customer_info=customer_info, logged_in=session.get('logged_in', False))


@app.route('/customer_profile')
def customer_profile():
    # Check if the user is logged in and has the role of 'customer'
    if 'logged_in' not in session or session.get('role') != 'customer':
        return redirect(url_for('login_page_redirect'))

    user_id = session['id']
    user_data = fetch_user_data(user_id)
    license_number = user_data.get('license', '')  # Get the license number from user data
    entry_transactions = []

    # Query tbl_parking_entries for entry transactions based on the license number
    if license_number:
        entries_ref = database.child('tbl_parking_entries').order_by_child('license_plate').equal_to(license_number).get()
        if entries_ref:
            for entry_key, entry_data in entries_ref.items():  # Use items() to iterate over key-value pairs
                entry_transactions.append(entry_data)

    return render_template('customer_profile.html', user_data=user_data, entry_transactions=entry_transactions, logged_in=session.get('logged_in', False))

@app.route('about')
def about():
    return render_template('about.html')


@app.route('/upload_image', methods=['POST'])
def upload_image():
    user_id = session['id']

    if 'profile_picture' in request.files:
        profile_picture = request.files['profile_picture']
        if profile_picture.filename != '':
            # Create a blob object in Firebase Storage
            blob = bucket.blob('profile_pictures/' + secure_filename(profile_picture.filename))

            # Upload the file to Firebase Storage
            blob.upload_from_file(profile_picture)

            # Get the public URL of the uploaded file
            profile_picture_url = blob.public_url

            # Update the user's profile picture URL in the database
            user_ref = database.child('tbl_customerAcc').child(user_id)
            user_ref.update({'profile_picture': profile_picture_url})

            return jsonify({'status': 'success', 'url': profile_picture_url})
        else:
            return jsonify({'status': 'error', 'message': 'No profile picture selected.'})
    else:
        return jsonify({'status': 'error', 'message': 'No profile picture data found in the request.'})

@app.route('/upload_header', methods=['POST'])
def upload_header():
    user_id = session['id']

    if 'header_pic' in request.files:
        header_pic = request.files['header_pic']
        if header_pic.filename != '':
            # Create a blob object in Firebase Storage
            blob = bucket.blob('header_pictures/' + secure_filename(header_pic.filename))

            # Upload the file to Firebase Storage
            blob.upload_from_file(header_pic)

            # Get the public URL of the uploaded file
            header_pic_url = blob.public_url

            # Update the user's header URL in the database
            user_ref = database.child('tbl_customerAcc').child(user_id)
            user_ref.update({'header_pic': header_pic_url})

            return jsonify({'status': 'success', 'url': header_pic_url})
        else:
            return jsonify({'status': 'error', 'message': 'No header picture selected.'})
    else:
        return jsonify({'status': 'error', 'message': 'No header picture data found in the request.'})

@app.route('/update_license', methods=['POST'])
def update_license():
    if 'updatePlate' in request.form:
        if 'id' in session:
            user_id = session['id']
            old_plate = request.form['lplate_edit']
            new_plate = request.form['new_plate']

            # Reference to the user's data in Firebase
            user_ref = database.child('tbl_customerAcc').child(user_id)

            # Fetch the current user data
            user_data = user_ref.get()

            # Check if the 'license' field exists and is an array
            if user_data and 'license' in user_data and isinstance(user_data['license'], list):
                licenses = user_data['license']
                if old_plate in licenses:
                    # Update the license plate
                    index = licenses.index(old_plate)
                    licenses[index] = new_plate

                    # Update the data in Firebase
                    user_ref.update({'license': licenses})

                    # JavaScript alert and redirect
                    return redirect(url_for('customer_profile'))
                else:
                    return "Old license plate not found."
            else:
                return "User data not found or user has no license plates."
        else:
            return "User ID not found. Please log in."
    else:
        return "No data submitted!"


# Route to handle adding a license plate
@app.route('/add_plate', methods=['POST'])
def add_plate():
    if 'id' in session:
        user_id = session['id']
        new_plate_number = request.form['plate_number']
        
        # Reference to the user's data in Firebase Realtime Database
        user_ref = f"tbl_customerAcc/{user_id}"
        user_data = database.child(user_ref).get().val()

        # Check if the 'license' field exists
        if 'license' in user_data:
            # If 'license' field is a list, append the new plate number
            if isinstance(user_data['license'], list):
                user_data['license'].append(new_plate_number)
            # If 'license' field is a string, convert it to a list and append the new plate number
            else:
                user_data['license'] = [user_data['license'], new_plate_number]
        else:
            # Create the 'license' field as a list with the new plate number
            user_data['license'] = [new_plate_number]

        # Update the user's data in Firebase Realtime Database
        database.child(user_ref).set(user_data)

        # Redirect to the customer profile page
        return redirect(url_for('customer_profile'))
    else:
        # Redirect to login page if user is not logged in
        return redirect(url_for('login'))










@app.route('/dashboard') # ------ THIS IS THE START OF THE FUNCTION FOR REDIRECTING TO DASHBOARD ACCDR. TO ROLE
def dashboard():
    if 'id' not in session:
        return redirect(url_for('login'))

    user_id = session['id']
    role = session.get('role')
    user_ref = db.reference('tbl_staffaccount/' + user_id)
    user_data = user_ref.get()

    if user_data is None:
        return redirect(url_for('login'))
    
    staff_info = fetch_user_data(user_id)

    log_action('Dashboard', 'Visited the Dashboard page')

    # Retrieve parking entries from Firebase
    parking_entries_ref = database.child('tbl_parking_entries')
    parking_entries = parking_entries_ref.get()

    # Convert parking entries data to a list of dictionaries
    parking_entries_list = []
    if parking_entries:
        for key, value in parking_entries.items():
            entry_data = value
            entry_data['entry_id'] = key
            parking_entries_list.append(entry_data)

    # Initialize counters for occupied and non-occupied parking slots
    total_paid = 0

    # Calculate occupied and non-occupied parking slots
    if parking_entries:
        for key, value in parking_entries.items():
            if value.get('payment_status') == 'Paid':
                total_paid += 1

    # Calculate total parking slots
    total_parking_slots = 750  # You can replace this with your actual total parking slots value

    total_non_occupied = total_parking_slots - total_paid

    image_url = f"https://storage.googleapis.com/{bucket.name}/{user_data.get('imagePath', 'default-image.jpg')}" 

    if role == 'admin':
        staff_info = fetch_user_data(user_id)
        return render_template('dashboard.html', staff_info=staff_info, user=user_data, image_url=image_url, parking_entries=parking_entries_list, total_id=total_paid, total_available_id=total_non_occupied, total_parking_slots=total_parking_slots)
    elif role == 'cashier':
        staff_info = fetch_user_data(user_id)
        return render_template('dashboardCashier.html', staff_info=staff_info, user=user_data, image_url=image_url, parking_entries=parking_entries_list, total_id=total_paid, total_available_id=total_non_occupied, total_parking_slots=total_parking_slots)
    else:
        return redirect(url_for('login_page_redirect'))
    
@app.route('/parking_entries')
def parking_entries():
    # Fetch parking entries from Firebase
    parking_entries_ref = database.child('tbl_parking_entries')
    parking_entries = parking_entries_ref.get()

    # Convert Firebase data to a list of dictionaries
    parking_entries_list = []
    if parking_entries:
        for key, value in parking_entries.items():
            entry_data = value
            entry_data['entry_id'] = key
            parking_entries_list.append(entry_data)

    # Render the template with parking entries data
    return render_template('parking_entries.html', parking_entries=parking_entries_list)





@app.route('/webcam_feed') # ------ THIS IS THE START OF THE FUNCTIONS FOR PARKING MANAGEMENT
def webcam_feed():
    return Response(object_detection(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/roi_text')
def roi_text():
    try:
        with open(os.path.join(ROI_DIR, 'roi_text.txt'), 'r') as file:
            roi_text = file.read()

        # Query the customer database based on the ROI text
        customer_name = get_customer_name(roi_text)

        return jsonify({'roiText': roi_text, 'customerName': customer_name})
    except Exception as e:
        print(f"Error reading ROI text: {str(e)}")
        return jsonify({'roiText': '', 'customerName': 'Guest'})


@app.route('/parking_entry')
def parking_entry():
    if 'id' not in session:
        return redirect(url_for('login'))

    user_id = session['id']
    user_ref = db.reference('tbl_staffaccount/' + user_id)
    user_data = user_ref.get()

    if user_data is None:
        return redirect(url_for('login'))
    
    staff_info = fetch_user_data(user_id)

    transaction_id = f"TX{get_latest_entry_transaction_id()}"
    entry_date = datetime.now().strftime("%Y-%m-%d")
    entry_time = datetime.now().strftime("%H:%M:%S")

    log_action('Parking', 'Visited the Parking page')


   # Initialize customer name as 'Guest'
    customer_name = 'Guest'

    # Retrieve ROI text (license plate) dynamically during the entry process
    roi_text_response = roi_text()  # Retrieve ROI text once
    roi_text_data = roi_text_response.get_json()
    license_plate = roi_text_data.get('roiText', '')

    # Get customer name from ROI text if available
    if 'customerName' in roi_text_data:
        customer_name = roi_text_data['customerName']

    image_url = f"https://storage.googleapis.com/{bucket.name}/{user_data.get('imagePath', 'default-image.jpg')}" 

    return render_template('parking_entry.html', staff_info=staff_info, user=user_data, image_url=image_url, transaction_id=transaction_id, entry_date=entry_date, entry_time=entry_time, customer_name=customer_name)

@app.route('/parking_exit')
def parking_exit():
    if 'id' not in session:
        return redirect(url_for('login'))

    user_id = session['id']
    user_ref = db.reference('tbl_staffaccount/' + user_id)
    user_data = user_ref.get()

    if user_data is None:
        return redirect(url_for('login'))
    
    staff_info = fetch_user_data(user_id)

    exit_date = datetime.now().strftime("%Y-%m-%d")
    exit_time = datetime.now().strftime("%H:%M:%S")

    # Initialize customer name as 'Guest'
    customer_name = 'Guest'

    # Retrieve ROI text (license plate) dynamically during the exit process
    roi_text_response = roi_text()  # Retrieve ROI text once
    roi_text_data = roi_text_response.get_json()
    license_plate = roi_text_data.get('roiText', '')

    # Get customer name from ROI text if available
    if 'customerName' in roi_text_data:
        customer_name = roi_text_data['customerName']

    log_action('Parking', 'Visited the Parking page')

    latest_entry_transaction = get_latest_entry_transaction(license_plate)

    if latest_entry_transaction:
        entry_date = latest_entry_transaction['entry_date']
        entry_time = latest_entry_transaction['entry_time']
        transaction_id = latest_entry_transaction['transaction_id']

        # Calculate duration in seconds
        entry_datetime = datetime.strptime(f"{entry_date} {entry_time}", "%Y-%m-%d %H:%M:%S")
        exit_datetime = datetime.strptime(f"{exit_date} {exit_time}", "%Y-%m-%d %H:%M:%S")
        duration_seconds = (exit_datetime - entry_datetime).total_seconds()

        # Convert duration to DD:HH:MM:SS format
        days, remainder = divmod(duration_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        duration_formatted = f"{int(days):02}:{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

        # Determine parking type based on duration in hours
        duration_hours = duration_seconds / 3600
        parking_type = "Regular" if duration_hours <= 24 else "Overnight"
        
        # Initial total fee calculation
        lost_parking_pass_checked = False  # Default value
        total_fee = calculate_parking_fee(duration_hours, lost_parking_pass_checked)
        
        # Update exit transaction details
        add_exit_transaction(
            license_plate,
            exit_date,
            exit_time,
            duration_formatted,  # Store duration in the desired format
            parking_type,
            lost_parking_pass_checked,
            total_fee  # Store total fee
        )

        image_url = f"https://storage.googleapis.com/{bucket.name}/{user_data.get('imagePath', 'default-image.jpg')}" 

        return render_template('parking_exit.html', staff_info=staff_info, exit_date=exit_date, exit_time=exit_time,
                               transaction_id=transaction_id, license_plate=license_plate, customer_name=customer_name,
                               duration=duration_formatted, parking_type=parking_type, total_fee=total_fee, user=user_data, image_url=image_url)
    else:
        return render_template('parking_exit.html', staff_info=staff_info, exit_date=exit_date, exit_time=exit_time)

@app.route('/entry_submit', methods=["POST"])
def entry_submit():
    if 'id' not in session:
        return redirect(url_for('login'))

    user_id = session['id']
    user_ref = db.reference('tbl_staffaccount/' + user_id)
    user_data = user_ref.get()

    if user_data is None:
        return redirect(url_for('login'))
    
    staff_info = fetch_user_data(user_id)

    if request.method == 'POST':
        transaction_id = request.form['transaction_id']
        license_plate = request.form['license_plate']
        entry_date = request.form['entry_date']
        entry_time = request.form['entry_time']

        try:
            # Existing code...
            roi_text_response = roi_text()  # Retrieve ROI text once
            roi_text_data = roi_text_response.get_json()
            roi_text = roi_text_data.get('roiText', '')
        except Exception as e:
            print(f"Error retrieving ROI text: {e}")
            roi_text = ''  # Set roi_text to a default value or handle the error

        # Retrieve customer name based on the ROI text
        customer_name = get_customer_name(roi_text)

        log_action('Parking', 'Entered an Entry Data')
        
        # Update the session name with the retrieved customer name
        session['name'] = customer_name

        # Add the entry transaction to the database
        add_entry_transaction(transaction_id, license_plate, customer_name, entry_date, entry_time)

        image_url = f"https://storage.googleapis.com/{bucket.name}/{user_data.get('imagePath', 'default-image.jpg')}" 
        
        return render_template('parking_entry.html', staff_info=staff_info, user=user_data, image_url=image_url,  customer_name= customer_name)
    return redirect(url_for('index'))


@app.route('/exit_submit', methods=["POST"])
def exit_submit():
    if 'id' not in session:
        return redirect(url_for('login'))

    user_id = session['id']
    user_ref = db.reference('tbl_staffaccount/' + user_id)
    user_data = user_ref.get()

    if user_data is None:
        return redirect(url_for('login'))
    
    staff_info = fetch_user_data(user_id)
    

    if request.method == 'POST':
        transaction_id = request.form['transaction_id']
        license_plate = request.form['license_plate']
        customer_name = request.form['customer_name']
        exit_date = request.form['exit_date']
        exit_time = request.form['exit_time']
        duration_str = request.form['duration']
        parking_type = request.form['parking_type']
        lost_parking_pass_checked = request.form.get('lost_parking_pass_fee') == 'on'

        log_action('Parking', 'Entered an Exit Data')

        # Parse duration string into days, hours, minutes, and seconds
        duration_parts = duration_str.split(':')
        days = int(duration_parts[0])
        hours = int(duration_parts[1])
        minutes = int(duration_parts[2])
        seconds = int(duration_parts[3])

        # Convert duration to hours
        duration_hours = days * 24 + hours + minutes / 60 + seconds / 3600

        # Calculate total fee
        total_fee = calculate_parking_fee(duration_hours, lost_parking_pass_checked)

        # Update exit transaction details
        add_exit_transaction(
            license_plate,
            exit_date,
            exit_time,
            duration_hours,
            parking_type,
            lost_parking_pass_checked,
            total_fee
        )
        image_url = f"https://storage.googleapis.com/{bucket.name}/{user_data.get('imagePath', 'default-image.jpg')}" 

        return render_template('parking_exit.html',  customer_name= customer_name, duration=duration_hours, parking_type=parking_type, total_fee=total_fee, staff_info=staff_info, user=user_data, image_url=image_url)
    return redirect(url_for('index'))






@app.route('/map') # ------ THIS IS THE START OF THE FUNCTIONS FOR MAP
def map():
    if 'id' not in session:
        return redirect(url_for('login'))

    user_id = session['id']
    user_ref = db.reference('tbl_staffaccount/' + user_id)
    user_data = user_ref.get()

    if user_data is None:
        return redirect(url_for('login'))
    
    staff_info = fetch_user_data(user_id)

    log_action('Map', 'Visited the Map page')

    image_url = f"https://storage.googleapis.com/{bucket.name}/{user_data.get('imagePath', 'default-image.jpg')}" 

    # Render the template with staff information
    return render_template('map.html', staff_info=staff_info, user=user_data, image_url=image_url)




@app.route('/parking_activity') # ------ THIS IS THE START OF THE FUNCTIONS FOR ACTIVITY
def parking_activity():
    if 'id' not in session:
        return redirect(url_for('login'))

    user_id = session['id']
    user_ref = db.reference('tbl_staffaccount/' + user_id)
    user_data = user_ref.get()

    if user_data is None:
        return redirect(url_for('login'))
    
    staff_info = fetch_user_data(user_id)

    log_action('Map', 'Visited the Activity page')

    image_url = f"https://storage.googleapis.com/{bucket.name}/{user_data.get('imagePath', 'default-image.jpg')}"   
   
    # Render the template with staff information
    return render_template('activity.html', staff_info=staff_info, user=user_data, image_url=image_url)



@app.route('/history_transactions') # ------ THIS IS THE START OF THE FUNCTIONS FOR TRANSACTIONS
def history_transactions():
    if 'id' not in session:
        return redirect(url_for('login'))

    user_id = session['id']
    user_ref = db.reference('tbl_staffaccount/' + user_id)
    user_data = user_ref.get()

    if user_data is None:
        return redirect(url_for('login'))
    
    staff_info = fetch_user_data(user_id)

    log_action('Transactions', 'Visited the Transactions page')

    # Retrieve parking entries from Firebase
    parking_entries_ref = database.child('tbl_parking_entries')
    parking_entries = parking_entries_ref.get()

    # Convert parking entries data to a list of dictionaries
    parking_entries_list = []
    if parking_entries:
        for key, value in parking_entries.items():
            entry_data = value
            entry_data['entry_id'] = key
            parking_entries_list.append(entry_data)


    image_url = f"https://storage.googleapis.com/{bucket.name}/{user_data.get('imagePath', 'default-image.jpg')}"            

    # Render the template with staff information
    return render_template('history.html', user=user_data, image_url=image_url, staff_info=staff_info, parking_entries=parking_entries_list)


@app.route('/generate_pdf')
def generate_pdf():
    plate_number = request.args.get('license_plate')
    transaction_id = request.args.get('transaction_id')

    if not plate_number or not transaction_id:
        return 'Plate number and transaction ID are required.', 400

    ref = db.reference('tbl_parking_entries')
    snapshot = ref.order_by_child('license_plate').equal_to(plate_number).get()

    if snapshot:
        park_pdf_data = None
        for key, val in snapshot.items():
            if val['transaction_id'] == transaction_id:
                park_pdf_data = val
                break

        if park_pdf_data:
            exit_date = park_pdf_data.get('exit_date', 'N/A')
            exit_time = park_pdf_data.get('exit_time', 'N/A')
            entry_time = park_pdf_data.get('entry_time', 'N/A')
            total_fee = park_pdf_data.get('total_fee', 0)
            customer_name = park_pdf_data.get('customer_name', 'N/A')

            # Read the logo image file and encode it as base64
            with open('static\img\stalu_logo.png', 'rb') as logo_file:
                logo_data = base64.b64encode(logo_file.read()).decode()

            html_content = f"""
            <html>
            <head>
                <style>
                body {{
                    font-family: "Courier New", Courier, monospace;
                    font-size: 13px;
                    color: #333;
                    text-align: center; /* Center-align the content */
                    padding: 0;
                }}
                .company-title {{
                    font-size: 17px;
                    margin-bottom: 25px;
                    font-weight: bold;
                }}
                .company-contact {{
                    font-size: 9px;
                    margin-top: 25px;
                }}
                .logo {{
                    width: 60px;
                    
                </style>
            </head>
            <body>
                <div class="company-title">
                    <img src="data:image/png;base64,{logo_data}" alt="Company Logo" class="logo">
                    <p><b>Sta.Lucia East Grand Mall</b></p>
                </div>
                <p><b>PARKING TICKET</b></p>
                <p>TRANSACTION ID: {transaction_id}</p>
                <p><b>PLATE NUMBER: {park_pdf_data['license_plate']}</b></p>
                <p>OWNER NAME: {customer_name}</p><br>
                <p>TIME OF ENTRY: {entry_time}</p>
                <p>TIME OF EXIT: {exit_time}</p>
                <p>DATE: {exit_date}</p><br>
                <p><b>PARKING FEE: Php {total_fee}0</b></p>

                <h5>Thank you and come again!</h5>

                <div class="company-contact">
                    <p>Penthouse, Building III, Sta. Lucia East<br>Grand Mall, Cainta, Rizal 1900</p>
                    <p>+63 02 8681-7332/+63 02 8681-9999</p>
                </div>
            </body>
            </html>
            """

            pdf_output_path = 'output.pdf'
            pdfkit_options = {
                'page-width': '80mm',
                'page-height': '130mm'
            }
            pdfkit.from_string(html_content, pdf_output_path, options=pdfkit_options)

            return send_file(pdf_output_path, mimetype='application/pdf', as_attachment=False)

    return 'Record not found for the given plate number and transaction ID.', 404









@app.route('/sales') # ------ THIS IS THE START OF THE FUNCTIONS FOR SALES
def sales():
    # Retrieve the user ID from the session
    if 'id' not in session:
        return redirect(url_for('login'))

    user_id = session['id']
    user_ref = db.reference('tbl_staffaccount/' + user_id)
    user_data = user_ref.get()

    if user_data is None:
        return redirect(url_for('login'))
    
    staff_info = fetch_user_data(user_id)

    log_action('Sales', 'Visited the Sales page')

     # Get fee values using get_fee_values() function
    flat_rate = get_fee_values()['flat_rate']
    night_parking = get_fee_values()['overnight_rate']
    lost_ticket = get_fee_values()['lost_ticket_pass']

    # Calculate the start and end dates for the current week
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    # Calculate the start and end dates for the current month
    start_of_month = today.replace(day=1)
    end_of_month = start_of_month.replace(day=1, month=start_of_month.month + 1) - timedelta(days=1)

    # Format the dates
    formatted_today = format_date(today)
    formatted_start_of_week = format_date(start_of_week)
    formatted_end_of_week = format_date(end_of_week)
    formatted_start_of_month = format_date(start_of_month)
    formatted_end_of_month = format_date(end_of_month)

    # Fetch entries from the database for the current day, week, and month
    daily_entries = fetch_entries_for_date(today)
    weekly_entries = fetch_entries_for_period(start_of_week, end_of_week)
    monthly_entries = fetch_entries_for_period(start_of_month, end_of_month)

    # Calculate total sales for the day, week, and month
    daily_sales = calculate_total_sales(daily_entries)
    weekly_sales = calculate_total_sales(weekly_entries)
    monthly_sales = calculate_total_sales(monthly_entries)

    image_url = f"https://storage.googleapis.com/{bucket.name}/{user_data.get('imagePath', 'default-image.jpg')}"     

    return render_template('rates.html',
                           flat_rate=flat_rate,
                           night_parking=night_parking,
                           lost_ticket=lost_ticket,
                           staff_info=staff_info, 
                           daily_sales=daily_sales, 
                           weekly_sales=weekly_sales, 
                           monthly_sales=monthly_sales,
                           formatted_today=formatted_today, 
                           formatted_start_of_week=formatted_start_of_week,
                           formatted_end_of_week=formatted_end_of_week,
                           formatted_start_of_month=formatted_start_of_month,
                           formatted_end_of_month=formatted_end_of_month,
                           user=user_data, image_url=image_url)

def format_date(date):
    return date.strftime('%b %d, %Y')

def fetch_entries_for_date(date):
    # Query the database to fetch entries for the given date
    # You may need to adjust this based on your database structure
    entries_ref = db.reference('tbl_parking_entries')
    query = entries_ref.order_by_child('entry_date').equal_to(date.strftime('%Y-%m-%d'))
    entries = query.get()

    return entries

def fetch_entries_for_period(start_date, end_date):
    # Query the database to fetch entries within the given period
    # You may need to adjust this based on your database structure
    entries_ref = db.reference('tbl_parking_entries')
    query = entries_ref.order_by_child('entry_date').start_at(start_date.strftime('%Y-%m-%d')).end_at(end_date.strftime('%Y-%m-%d'))
    entries = query.get()

    return entries

def calculate_total_sales(entries):
    total_sales = 0
    if entries:
        for entry in entries.values():
            total_sales += float(entry.get('total_fee', 0))

    return total_sales







@app.route('/staff_users') # ------ THIS IS THE START OF THE FUNCTIONS FOR STAFF ACCOUNTS
def staff_users():
    if 'id' not in session:
        return redirect(url_for('login'))

    user_id = session['id']
    user_ref = db.reference('tbl_staffaccount/' + user_id)
    user_data = user_ref.get()

    if user_data is None:
        return redirect(url_for('login'))
    
    staff_info = fetch_user_data(user_id)

    log_action('Staff Account', 'Visited the Staff Account page')

    # Fetch data from Firebase Realtime Database
    data = database.child('tbl_staffaccount').order_by_child('archived').equal_to(0).get()
    
    staff_accounts = []
    if data:
        for staff_id, staff_data in data.items():
            staff_accounts.append({
                'id': staff_id,
                'fullName': f"{staff_data['firstName']} {staff_data['lastName']}",
                'emailAddress': staff_data['emailAddress'],
                'staffPosition': staff_data['staffPosition']
            })

    image_url = f"https://storage.googleapis.com/{bucket.name}/{user_data.get('imagePath', 'default-image.jpg')}"    
    
    return render_template('staff_users.html', staff_accounts=staff_accounts, staff_info=staff_info, user=user_data, image_url=image_url)

# Global variable to keep track of the last used staff ID
last_staff_id = 0

@app.route('/add_staff_account', methods=["POST"])
def add_staff_account():
    global last_staff_id

    # Get form data
    first_name = request.form.get('firstName')
    last_name = request.form.get('lastName')
    email_address = request.form.get('emailAddress')
    password = request.form.get('accountPassword')
    staff_position = request.form.get('staffPosition')

    # Validate form data
    if not first_name or not last_name or not email_address or not password or not staff_position:
        return jsonify(success=False, message="All fields are required"), 400

    # Increment the last staff ID
    last_staff_id += 1

    # Insert data into the database
    new_staff_id = last_staff_id

    log_action('Staff Account', 'Added a New Staff Account')

    # Push data to Firebase using the custom ID
    database.child('tbl_staffaccount').child(new_staff_id).set({
        'firstName': first_name,
        'lastName': last_name,
        'emailAddress': email_address,
        'accountPassword': password,
        'staffPosition': staff_position,
        'archived': 0
    })

    return jsonify(success=True, message="Account added successfully")

@app.route('/save_changes_staff', methods=["POST"])
def save_changes_staff():
    # Get form data
    staff_id = request.form.get('staffId')
    first_name = request.form.get('firstName')
    last_name = request.form.get('lastName')
    email_address = request.form.get('emailAddress')
    password = request.form.get('accountPassword')
    staff_position = request.form.get('staffPosition')

    log_action('Staff Account', 'Edited a Staff Account')

    # Validate form data
    if not staff_id or not first_name or not last_name or not email_address or not password or not staff_position:
        return jsonify(success=False, message="All fields are required"), 400

    # Update data in the database
    update_data = {
        'firstName': first_name,
        'lastName': last_name,
        'emailAddress': email_address,
        'accountPassword': password,
        'staffPosition': staff_position
    }
    
    database.child('tbl_staffaccount').child(staff_id).update(update_data)

    return jsonify(success=True, message="Changes saved successfully")


@app.route('/archive_staff_account', methods=["POST"])
def archive_staff_account():
    # Get form data
    staff_id = request.form.get('staffId')

    log_action('Staff Account', 'Archived a Staff Account')

    # Validate form data
    if not staff_id:
        return jsonify(success=False, message="Staff ID is required"), 400

    # Update the 'archived' status in the database
    update_data = {'archived': 1}
    database.child('tbl_staffaccount').child(staff_id).update(update_data)

    return jsonify(success=True, message="Staff account archived successfully")








@app.route('/archives')
def archives():
    if 'id' not in session:
        return redirect(url_for('login'))

    user_id = session['id']
    user_ref = db.reference('tbl_staffaccount/' + user_id)
    user_data = user_ref.get()

    if user_data is None:
        return redirect(url_for('login'))
    
    staff_info = fetch_user_data(user_id)

    log_action('Archive', 'Visited the Archive page')

    # Fetch data from Firebase Realtime Database where archived is equal to 1
    archived_data = database.child('tbl_staffaccount').order_by_child('archived').equal_to(1).get()

    archived_staff_accounts = []
    if archived_data:
        for staff_id, staff_data in archived_data.items():
            archived_staff_accounts.append({
                'id': staff_id,
                'fullName': f"{staff_data['firstName']} {staff_data['lastName']}",
                'emailAddress': staff_data['emailAddress'],
                'staffPosition': staff_data['staffPosition']
            })
    
    image_url = f"https://storage.googleapis.com/{bucket.name}/{user_data.get('imagePath', 'default-image.jpg')}"    

    return render_template('archive.html', archived_staff_accounts=archived_staff_accounts, staff_info=staff_info, user=user_data, image_url=image_url)




@app.route('/logs_page') # ------ THIS IS THE START OF THE FUNCTIONS FOR LOGS RECORD
def logs_page():
    if 'id' not in session:
        return redirect(url_for('login'))

    user_id = session['id']
    user_ref = db.reference('tbl_staffaccount/' + user_id)
    user_data = user_ref.get()

    if user_data is None:
        return redirect(url_for('login'))
    
    staff_info = fetch_user_data(user_id)

    log_action('Logs', 'Visited the Logs page')

    logs_ref = database.child('tbl_logs')
    logs = logs_ref.order_by_child('actionTime').get()

    staff_name = get_staff_name(user_id)

    # Pagination setup
    logs_records_per_page = 10
    logs_page = int(request.args.get('logs_page', 1))  # Get page number from query parameter, default to 1
    logs_offset = (logs_page - 1) * logs_records_per_page

    # Get the total number of logs from Firebase
    logCountSnapshot = database.get('tbl_logs')
    logs_total_records = len(logCountSnapshot) if logCountSnapshot else 0
    logs_total_pages = (logs_total_records + logs_records_per_page - 1) // logs_records_per_page

    # Get logs for the current page
    logs = database.child('tbl_logs').order_by_child('actionTime').limit_to_last(logs_records_per_page).get()

    # Pagination links
    logs_pagination = ""
    if logs_page > 1:
        logs_pagination += f'<a href="/logs?logs_page={logs_page - 1}" aria-label="Previous">Previous</a>'
    for i in range(logs_page - 4, logs_page + 6):
        if 1 <= i <= logs_total_pages:
            logs_pagination += f'<a href="/logs?logs_page={i}" class="{ "active" if i == logs_page else "" }">{i}</a>'
    if logs_page < logs_total_pages:
        logs_pagination += f'<a href="/logs?logs_page={logs_page + 1}" aria-label="Next">Next</a>'

    image_url = f"https://storage.googleapis.com/{bucket.name}/{user_data.get('imagePath', 'default-image.jpg')}"    

    return render_template('logs.html', staff_info=staff_info, logs=logs, staff_name=staff_name, logs_pagination=logs_pagination, user=user_data, image_url=image_url)

def get_staff_name(staff_id):
    staff_ref = db.reference('tbl_staffaccount').child(staff_id)
    staff_data = staff_ref.get()

    if staff_data:
        return f"{staff_data.get('firstName', '')} {staff_data.get('lastName', '')}"
    return 'Unknown'







@app.route('/user_profile', methods=['GET', 'POST']) # ------ THIS IS THE START OF THE FUNCTIONS FOR CUSTOMER PROFILE
def user_profile():
    if 'id' not in session:
        return redirect(url_for('login'))

    user_id = session['id']
    user_ref = db.reference('tbl_staffaccount/' + user_id)
    user_data = user_ref.get()

    if user_data is None:
        return redirect(url_for('login'))
    
    staff_info = fetch_user_data(user_id)
    
    if request.method == 'POST':
        # Handle image upload
        if 'image' in request.files:
            image = request.files['image']
            new_image_name = handle_image_upload(image, user_id)
            if new_image_name is not None:
                user_ref.update({'imagePath': new_image_name})
                user_data['imagePath'] = new_image_name

        # Handle other profile updates
        updates = {}
        first_name = request.form.get('update-fname')
        last_name = request.form.get('update-lname')
        email = request.form.get('update-email')
        password = request.form.get('password')
        new_password = request.form.get('new-pass')
        confirm_password = request.form.get('confirm-pass')

        if first_name and first_name != user_data.get('firstName'):
            updates['firstName'] = first_name

        if last_name and last_name != user_data.get('lastName'):
            updates['lastName'] = last_name

        if email and email != user_data.get('emailAddress'):
            updates['emailAddress'] = email

        if new_password and new_password == confirm_password:
            hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
            updates['accountPassword'] = hashed_password

        if updates:
            user_ref.update(updates)
            user_data.update(updates)

    image_url = f"https://storage.googleapis.com/{bucket.name}/{user_data.get('imagePath', 'default-image.jpg')}"

    return render_template('profile.html', user=user_data, image_url=image_url, staff_info=staff_info)








@app.route('/logout_staff') # ------ THIS IS THE START OF THE FUNCTIONS FOR LOGGING OUT
def logout_staff():
    # Clear session variables
    session.pop('logged_in', None)
    session.clear()

    # Redirect to the logout page or homepage
    return redirect(url_for('index'))

@app.route('/logout_customer', methods=['POST'])
def logout_customer():
    session.pop('id', None)  # Remove 'id' from session if it exists
    return redirect(url_for('index'))  # Redirect to the homepage or any other appropriate page


if __name__ == "__main__":
    app.run(debug=True)


### ADD SUCCESS PAGES
### ADD LOGS