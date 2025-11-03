import os
import logging
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Gather
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env

app = Flask(__name__)

# --- App Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@db:5432/take5db")
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['FLASK_ADMIN_SWATCH'] = 'cerulean' # A nice theme for the admin panel
app.secret_key = os.getenv("SECRET_KEY", "a-super-secret-key-for-admin") # Needed for Flask-Admin

# --- Initialize Extensions ---
db = SQLAlchemy(app)
admin = Admin(app, name='Take 5 Bot Admin', template_mode='bootstrap3')

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Database Models (Defines the structure for the ORM and Flask-Admin) ---

class CallHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    call_sid = db.Column(db.String(255), nullable=False)
    user_utterance = db.Column(db.Text, nullable=True)
    bot_response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    direction = db.Column(db.String(10))

class Services(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.String(100), nullable=True)
    price_varies = db.Column(db.Boolean, default=False)

class BusinessInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    info_key = db.Column(db.String(255), unique=True, nullable=False)
    info_value = db.Column(db.Text)

class OperatingHours(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day_range = db.Column(db.String(50), unique=True, nullable=False)
    hours = db.Column(db.String(100))

# --- Admin Panel Setup ---
# Add views for each model to the admin panel. These are the pages for editing the data.
admin.add_view(ModelView(Services, db.session))
admin.add_view(ModelView(BusinessInfo, db.session))
admin.add_view(ModelView(OperatingHours, db.session))
admin.add_view(ModelView(CallHistory, db.session)) # View call history in the admin panel

# --- Database Initialization and Seeding ---
def init_db():
    """
    Creates all database tables from the models above and seeds them with
    initial data if they are empty.
    """
    with app.app_context():
        db.create_all()

        # Seed business_info only if it's empty
        if not BusinessInfo.query.first():
            info_data = [
                BusinessInfo(info_key='business_name', info_value='Take 5 Oil Change Orangeville'),
                BusinessInfo(info_key='address', info_value='220 Centennial Road, Orangeville, Ontario, L9W 5K2'),
                BusinessInfo(info_key='intersection', info_value='Riddell Road and Centennial Road'),
                BusinessInfo(info_key='shop_fee', info_value='4 dollars and 45 cents (before tax)')
            ]
            db.session.bulk_save_objects(info_data)
            logger.info("Seeded business_info table.")

        # Seed operating_hours only if it's empty
        if not OperatingHours.query.first():
            hours_data = [
                OperatingHours(day_range='Mon-Fri', hours='8 a.m. to 8 p.m.'),
                OperatingHours(day_range='Sat', hours='8 a.m. to 6 p.m.'),
                OperatingHours(day_range='Sun', hours='9 a.m. to 5 p.m.'),
                OperatingHours(day_range='Holidays', hours='shorter hours')
            ]
            db.session.bulk_save_objects(hours_data)
            logger.info("Seeded operating_hours table.")
        
        # Seed services only if it's empty
        if not Services.query.first():
            services_data = [
                Services(name='oil change economy', description='Up to 6 liters', price='59 dollars and 99 cents', price_varies=False),
                Services(name='oil change synthetic blend', description='Up to 6 liters', price='79 dollars and 99 cents', price_varies=False),
                Services(name='oil change full synthetic', description='Up to 6 liters', price='99 dollars and 99 cents', price_varies=False),
                Services(name='coolant exchange', description='Includes up to 10 liters coolant', price='149 dollars and 99 cents', price_varies=False),
                Services(name='rust proofing', description='Sedan: 59 dollars and 99 cents, SUV or Van: 79 dollars and 99 cents, XL vehicles are additional', price_varies=True),
                Services(name='tire rotation', description='Sedan: 55 dollars and 99 cents, SUV or Van: 79 dollars and 99 cents, Truck: 89 dollars and 99 cents (plus 10 dollars for oversized)', price_varies=True),
                Services(name='tire changeover', description='Same pricing as rotation', price_varies=True),
                Services(name='air & cabin filters', description='Price depends on vehicle, please visit us for a quote', price_varies=True)
            ]
            db.session.bulk_save_objects(services_data)
            logger.info("Seeded services table.")
        
        db.session.commit()
        logger.info("Database initialized successfully.")

# --- Chatbot Logic (Using SQLAlchemy ORM) ---
def get_bot_response(user_utterance, call_sid):
    user_utterance_lower = user_utterance.lower()
    response_text = "I can confirm that at the shop when you stop by—no appointment needed." # Default fallback

    try:
        # Intent 1: Oil Change Pricing
        if "oil change" in user_utterance_lower and ("price" in user_utterance_lower or "cost" in user_utterance_lower or "much" in user_utterance_lower):
            full_synth = Services.query.filter_by(name='oil change full synthetic').first()
            blend = Services.query.filter_by(name='oil change synthetic blend').first()
            economy = Services.query.filter_by(name='oil change economy').first()
            response_text = (
                f"Full synthetic oil changes start at {full_synth.price}, synthetic blend at {blend.price}, "
                f"and economy at {economy.price}. That includes up to six liters. No appointment needed—you can just drive in anytime."
            )
        # Intent 2: Hours
        elif "hours" in user_utterance_lower or "open" in user_utterance_lower:
            hours_rows = OperatingHours.query.filter(OperatingHours.day_range.in_(['Mon-Fri', 'Sat', 'Sun'])).all()
            hours_dict = {h.day_range: h.hours for h in hours_rows}
            response_text = (
                f"Our hours are: Monday through Friday {hours_dict.get('Mon-Fri', '')}, "
                f"Saturday {hours_dict.get('Sat', '')}, and Sunday {hours_dict.get('Sun', '')}."
                f" Most holidays have shorter hours. No appointment needed!"
            )
        # Intent 3: Location
        elif "location" in user_utterance_lower or "where are you" in user_utterance_lower or "address" in user_utterance_lower:
            address = BusinessInfo.query.filter_by(info_key='address').first()
            intersection = BusinessInfo.query.filter_by(info_key='intersection').first()
            weekday_hours = OperatingHours.query.filter_by(day_range='Mon-Fri').first()
            response_text = (
                f"We are located at {address.info_value}, near {intersection.info_value.split(' and ')[0]}."
                f" We're open {weekday_hours.hours} weekdays for drive-thru service, no appointment needed!"
            )
        # Intent 4: Specific Services
        elif "coolant" in user_utterance_lower:
            coolant = Services.query.filter_by(name='coolant exchange').first()
            response_text = (f"Yes, we offer coolant exchange including up to 10 liters of coolant, for {coolant.price}. No appointment is needed, just drive in!")
        elif "rust proofing" in user_utterance_lower:
            rust_info = Services.query.filter_by(name='rust proofing').first()
            response_text = (f"We offer rust proofing. Pricing varies: {rust_info.description}. We can confirm the exact price for your vehicle when you stop by—no appointment needed!")
        elif "tire rotation" in user_utterance_lower or "tire changeover" in user_utterance_lower:
            tire_info = Services.query.filter_by(name='tire rotation').first()
            response_text = (f"Yes, we do tire rotations and on-rim changeovers. Pricing starts at {tire_info.description.split(',')[0]}. We can confirm the exact price for your vehicle when you stop by—no appointment needed!")
        elif "air filter" in user_utterance_lower or "cabin filter" in user_utterance_lower:
            air_filter_info = Services.query.filter_by(name='air & cabin filters').first()
            response_text = (f"Yes, we replace air and cabin filters. {air_filter_info.description}. Please visit us, no appointment is needed!")
        # Intent 5: Services NOT Provided
        elif any(word in user_utterance_lower for word in ["brakes", "engine", "repair", "diagnostic", "check engine", "mechanical"]):
            response_text = "We don’t do full mechanical work here—just quick drive-thru maintenance like oil changes, air and cabin filters, coolant, and tires. Stop by anytime, no appointment needed!"
        # Intent 6: Coupon Request
        elif "coupon" in user_utterance_lower or "discount" in user_utterance_lower:
            response_text = "Sure thing. I can text you ten dollars off your next visit. To receive it, please provide your phone number after the beep. Otherwise, you can ask about other services or just stop by."
    
    except Exception as e:
        logger.error(f"Error processing bot response for CallSid {call_sid}: {e}")
        response_text = "I'm sorry, I'm having trouble accessing my information right now. Please call back in a moment."

    return response_text


# --- Flask Routes ---
@app.route("/")
def hello():
    return "Take 5 Orangeville Voice Assistant is running! Access the admin panel at /admin"

@app.route("/voice", methods=['POST'])
def voice_call():
    """Handle incoming voice calls from Twilio."""
    response = VoiceResponse()
    call_sid = request.values.get('CallSid')
    user_utterance = request.values.get('SpeechResult')
    
    if user_utterance:
        logger.info(f"Received speech from CallSid {call_sid}: {user_utterance}")
        bot_response_text = get_bot_response(user_utterance, call_sid)
        
        response.say(bot_response_text, voice='en-CA-Standard-A')
        logger.info(f"Bot response for CallSid {call_sid}: {bot_response_text}")

        # Store interaction in DB using the ORM
        try:
            history_entry = CallHistory(call_sid=call_sid, user_utterance=user_utterance, bot_response=bot_response_text, direction='inbound')
            db.session.add(history_entry)
            db.session.commit()
        except Exception as e:
            logger.error(f"Error saving call history for CallSid {call_sid}: {e}")
            db.session.rollback()

        if "To receive it, please provide your phone number after the beep" in bot_response_text:
            response.gather(input='dtmf', numDigits=10, timeout=10, action='/gather_phone_number', finishOnKey='#')
        else:
            response.gather(input='speech', speechTimeout='auto', timeout=3, action='/voice')

    else:
        greeting = "Thank you for calling Take 5 Orangeville! How can I help you today?"
        response.say(greeting, voice='en-CA-Standard-A')
        logger.info(f"Initial greeting for CallSid {call_sid}: {greeting}")

        try:
            history_entry = CallHistory(call_sid=call_sid, bot_response=greeting, direction='inbound')
            db.session.add(history_entry)
            db.session.commit()
        except Exception as e:
            logger.error(f"Error saving initial greeting for CallSid {call_sid}: {e}")
            db.session.rollback()

        response.gather(input='speech', speechTimeout='auto', timeout=3, action='/voice')
    
    return str(response)

@app.route("/gather_phone_number", methods=['POST'])
def gather_phone_number():
    """Handles the DTMF input for phone number for coupon."""
    response = VoiceResponse()
    call_sid = request.values.get('CallSid')
    digits = request.values.get('Digits')

    if digits and len(digits) >= 10:
        sms_confirmation_msg = f"Thank you! Your coupon will be sent to {digits}. We look forward to seeing you. Goodbye!"
        response.say(sms_confirmation_msg, voice='en-CA-Standard-A')
        
        try:
            history_entry = CallHistory(call_sid=call_sid, user_utterance=f"Provided phone number: {digits}", bot_response=sms_confirmation_msg, direction='inbound')
            db.session.add(history_entry)
            db.session.commit()
        except Exception as e:
            logger.error(f"Error saving coupon SMS event for CallSid {call_sid}: {e}")
            db.session.rollback()

        response.hangup()
    else:
        response.say("I didn't get a valid 10-digit phone number. Please call back if you'd like to try again or just stop by for service, no appointment needed. Goodbye!", voice='en-CA-Standard-A')
        logger.warning(f"Invalid phone number provided for CallSid {call_sid}: {digits}")
        response.hangup()

    return str(response)

if __name__ == "__main__":
    init_db() # Ensure database is set up and seeded
    app.run(host="0.0.0.0", port=5000, debug=True)