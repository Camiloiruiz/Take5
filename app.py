import os
import logging
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Gather
# from twilio.rest import Client # Uncomment if you enable SMS sending for coupon
import psycopg2
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database connection details
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@db:5432/take5db")

# Uncomment and fill these if you enable SMS sending for coupon
# TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
# TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
# TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
# twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) # Initialize Twilio Client

def get_db_connection():
    """Establishes a new database connection."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# --- Database Initialization and Seeding ---
def init_db():
    """
    Initializes the database by creating tables if they don't exist
    and populating them with default data if they are empty.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Table for call history (unchanged)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS call_history (
                id SERIAL PRIMARY KEY,
                call_sid VARCHAR(255) NOT NULL,
                user_utterance TEXT,
                bot_response TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                direction VARCHAR(10)
            );
        """)

        # Table for services
        cur.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL,
                description TEXT,
                price VARCHAR(100),
                price_varies BOOLEAN DEFAULT FALSE
            );
        """)

        # Table for general business information (key-value store)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS business_info (
                id SERIAL PRIMARY KEY,
                info_key VARCHAR(255) UNIQUE NOT NULL,
                info_value TEXT
            );
        """)
        
        # Table for operating hours
        cur.execute("""
            CREATE TABLE IF NOT EXISTS operating_hours (
                id SERIAL PRIMARY KEY,
                day_range VARCHAR(50) UNIQUE NOT NULL,
                hours VARCHAR(100)
            );
        """)

        # --- Data Seeding (runs only if tables are empty) ---
        
        # Seed business_info
        cur.execute("SELECT COUNT(*) FROM business_info")
        if cur.fetchone()[0] == 0:
            info_data = [
                ('business_name', 'Take 5 Oil Change Orangeville'),
                ('address', '220 Centennial Road, Orangeville, Ontario, L9W 5K2'),
                ('intersection', 'Riddell Road and Centennial Road'),
                ('no_appointment', 'True'),
                ('drive_thru', 'True'),
                ('avg_oil_change_time', '12 minutes or less'),
                ('shop_fee', '4 dollars and 45 cents (before tax)')
            ]
            cur.executemany("INSERT INTO business_info (info_key, info_value) VALUES (%s, %s)", info_data)
            logger.info("Seeded business_info table.")

        # Seed operating_hours
        cur.execute("SELECT COUNT(*) FROM operating_hours")
        if cur.fetchone()[0] == 0:
            hours_data = [
                ('Mon-Fri', '8 a.m. to 8 p.m.'),
                ('Sat', '8 a.m. to 6 p.m.'),
                ('Sun', '9 a.m. to 5 p.m.'),
                ('Holidays', 'shorter hours')
            ]
            cur.executemany("INSERT INTO operating_hours (day_range, hours) VALUES (%s, %s)", hours_data)
            logger.info("Seeded operating_hours table.")

        # Seed services
        cur.execute("SELECT COUNT(*) FROM services")
        if cur.fetchone()[0] == 0:
            services_data = [
                ('oil change economy', 'Up to 6 liters', '59 dollars and 99 cents', False),
                ('oil change synthetic blend', 'Up to 6 liters', '79 dollars and 99 cents', False),
                ('oil change full synthetic', 'Up to 6 liters', '99 dollars and 99 cents', False),
                ('coolant exchange', 'Includes up to 10 liters coolant', '149 dollars and 99 cents', False),
                ('rust proofing', 'Sedan: 59 dollars and 99 cents, SUV or Van: 79 dollars and 99 cents, XL vehicles are additional', None, True),
                ('tire rotation', 'Sedan: 55 dollars and 99 cents, SUV or Van: 79 dollars and 99 cents, Truck: 89 dollars and 99 cents (plus 10 dollars for oversized)', None, True),
                ('tire changeover', 'Same pricing as rotation', None, True),
                ('air & cabin filters', 'Price depends on vehicle, please visit us for a quote', None, True)
            ]
            cur.executemany("INSERT INTO services (name, description, price, price_varies) VALUES (%s, %s, %s, %s)", services_data)
            logger.info("Seeded services table.")

        conn.commit()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
    finally:
        if conn:
            conn.close()


# --- Chatbot Logic (Now Database-Driven) ---
def get_bot_response(user_utterance, call_sid):
    user_utterance_lower = user_utterance.lower()
    response_text = "I can confirm that at the shop when you stop by—no appointment needed." # Default fallback
    conn = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Intent 1: Oil Change Pricing
        if "oil change" in user_utterance_lower and ("price" in user_utterance_lower or "cost" in user_utterance_lower or "much" in user_utterance_lower):
            cur.execute("SELECT price FROM services WHERE name = 'oil change full synthetic'")
            full_synth_price = cur.fetchone()[0]
            cur.execute("SELECT price FROM services WHERE name = 'oil change synthetic blend'")
            blend_price = cur.fetchone()[0]
            cur.execute("SELECT price FROM services WHERE name = 'oil change economy'")
            economy_price = cur.fetchone()[0]
            response_text = (
                f"Full synthetic oil changes start at {full_synth_price}, synthetic blend at {blend_price}, "
                f"and economy at {economy_price}. That includes up to six liters. No appointment needed—you can just drive in anytime."
            )
        # Intent 2: Hours
        elif "hours" in user_utterance_lower or "open" in user_utterance_lower:
            cur.execute("SELECT day_range, hours FROM operating_hours WHERE day_range IN ('Mon-Fri', 'Sat', 'Sun')")
            hours_rows = cur.fetchall()
            hours_dict = dict(hours_rows)
            response_text = (
                f"Our hours are: Monday through Friday {hours_dict.get('Mon-Fri', '')}, "
                f"Saturday {hours_dict.get('Sat', '')}, and Sunday {hours_dict.get('Sun', '')}."
                f" Most holidays have shorter hours. No appointment needed!"
            )
        # Intent 3: Location
        elif "location" in user_utterance_lower or "where are you" in user_utterance_lower or "address" in user_utterance_lower:
            cur.execute("SELECT info_value FROM business_info WHERE info_key = 'address'")
            address = cur.fetchone()[0]
            cur.execute("SELECT info_value FROM business_info WHERE info_key = 'intersection'")
            intersection = cur.fetchone()[0]
            cur.execute("SELECT hours FROM operating_hours WHERE day_range = 'Mon-Fri'")
            weekday_hours = cur.fetchone()[0]
            response_text = (
                f"We are located at {address}, near {intersection.split(' and ')[0]}."
                f" We're open {weekday_hours} weekdays for drive-thru service, no appointment needed!"
            )
        # Intent 4: Specific Services (Coolant, Rust Proofing, Tires, Air/Cabin Filters)
        elif "coolant" in user_utterance_lower:
            cur.execute("SELECT price FROM services WHERE name = 'coolant exchange'")
            coolant_price = cur.fetchone()[0]
            response_text = (
                f"Yes, we offer coolant exchange including up to 10 liters of coolant, for {coolant_price}."
                f" No appointment is needed, just drive in!"
            )
        elif "rust proofing" in user_utterance_lower:
            cur.execute("SELECT description FROM services WHERE name = 'rust proofing'")
            rust_desc = cur.fetchone()[0]
            response_text = (
                f"We offer rust proofing. Pricing varies: {rust_desc}. "
                f"We can confirm the exact price for your vehicle when you stop by—no appointment needed!"
            )
        elif "tire rotation" in user_utterance_lower or "tire changeover" in user_utterance_lower:
            cur.execute("SELECT description FROM services WHERE name = 'tire rotation'")
            tire_desc = cur.fetchone()[0]
            response_text = (
                f"Yes, we do tire rotations and on-rim changeovers. Pricing starts at {tire_desc.split(',')[0]}. "
                f"We can confirm the exact price for your vehicle when you stop by—no appointment needed!"
            )
        elif "air filter" in user_utterance_lower or "cabin filter" in user_utterance_lower:
            cur.execute("SELECT description FROM services WHERE name = 'air & cabin filters'")
            air_filter_desc = cur.fetchone()[0]
            response_text = (
                f"Yes, we replace air and cabin filters. {air_filter_desc}. "
                f"Please visit us, no appointment is needed!"
            )
        # Intent 5: Services NOT Provided
        elif any(word in user_utterance_lower for word in ["brakes", "engine", "repair", "diagnostic", "check engine", "mechanical"]):
            response_text = "We don’t do full mechanical work here—just quick drive-thru maintenance like oil changes, air and cabin filters, coolant, and tires. Stop by anytime, no appointment needed!"
        # Intent 6: Coupon Request
        elif "coupon" in user_utterance_lower or "discount" in user_utterance_lower:
            response_text = "Sure thing. I can text you ten dollars off your next visit. To receive it, please provide your phone number after the beep. Otherwise, you can ask about other services or just stop by."
    
    except Exception as e:
        logger.error(f"Error processing bot response for CallSid {call_sid}: {e}")
        # A safe, generic response in case of database failure
        response_text = "I'm sorry, I'm having trouble accessing my information right now. Please call back in a moment."
    finally:
        if conn:
            conn.close()

    return response_text

# --- Flask Routes (Largely Unchanged) ---
@app.route("/")
def hello():
    return "Take 5 Orangeville Voice Assistant is running!"

@app.route("/voice", methods=['POST'])
def voice_call():
    """Handle incoming voice calls from Twilio."""
    response = VoiceResponse()
    call_sid = request.values.get('CallSid')
    user_utterance = request.values.get('SpeechResult') # Transcribed speech from Twilio
    
    if user_utterance:
        logger.info(f"Received speech from CallSid {call_sid}: {user_utterance}")
        bot_response_text = get_bot_response(user_utterance, call_sid)
        
        response.say(bot_response_text, voice='en-CA-Standard-A')
        logger.info(f"Bot response for CallSid {call_sid}: {bot_response_text}")

        # Store interaction in DB
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO call_history (call_sid, user_utterance, bot_response, direction) VALUES (%s, %s, %s, %s)",
                (call_sid, user_utterance, bot_response_text, 'inbound')
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving call history for CallSid {call_sid}: {e}")
        finally:
            if conn:
                conn.close()

        # If a coupon was offered and a number requested, we need to gather DTMF for it
        if "To receive it, please provide your phone number after the beep" in bot_response_text:
            response.gather(input='dtmf', numDigits=10, timeout=10, action='/gather_phone_number', finishOnKey='#')
        else:
            response.gather(input='speech', speechTimeout='auto', timeout=3, action='/voice')

    else:
        # This branch is for the very first incoming call, or if user was silent
        greeting = "Thank you for calling Take 5 Orangeville! How can I help you today?"
        response.say(greeting, voice='en-CA-Standard-A')
        logger.info(f"Initial greeting for CallSid {call_sid}: {greeting}")

        # Store initial greeting
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO call_history (call_sid, bot_response, direction) VALUES (%s, %s, %s)",
                (call_sid, greeting, 'inbound')
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving initial greeting for CallSid {call_sid}: {e}")
        finally:
            if conn:
                conn.close()

        response.gather(input='speech', speechTimeout='auto', timeout=3, action='/voice')
    
    return str(response)

@app.route("/gather_phone_number", methods=['POST'])
def gather_phone_number():
    """Handles the DTMF input for phone number for coupon."""
    response = VoiceResponse()
    call_sid = request.values.get('CallSid')
    digits = request.values.get('Digits')

    if digits and len(digits) >= 10:
        phone_number = "+" + digits

        # Default confirmation message if SMS sending is not enabled/configured
        sms_confirmation_msg = f"Thank you! Your coupon will be sent to {digits}. We look forward to seeing you. Goodbye!"
        response.say(sms_confirmation_msg, voice='en-CA-Standard-A')
        
        # Log this event to call_history
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO call_history (call_sid, user_utterance, bot_response, direction) VALUES (%s, %s, %s, %s)",
                (call_sid, f"Provided phone number: {digits}", sms_confirmation_msg, 'inbound')
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving coupon SMS event for CallSid {call_sid}: {e}")
        finally:
            if conn:
                conn.close()

        response.hangup()
    else:
        response.say("I didn't get a valid 10-digit phone number. Please call back if you'd like to try again or just stop by for service, no appointment needed. Goodbye!", voice='en-CA-Standard-A')
        logger.warning(f"Invalid phone number provided for CallSid {call_sid}: {digits}")
        response.hangup()

    return str(response)

if __name__ == "__main__":
    init_db() # Ensure database is set up and seeded
    app.run(host="0.0.0.0", port=5000, debug=True)