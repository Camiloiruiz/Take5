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
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# Initialize the database (create tables if they don't exist)
def init_db():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS call_history (
                id SERIAL PRIMARY KEY,
                call_sid VARCHAR(255) NOT NULL,
                user_utterance TEXT,
                bot_response TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                direction VARCHAR(10) # 'inbound'
            );
        """)
        conn.commit()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
    finally:
        if conn:
            conn.close()

# --- Knowledge Base (Hardcoded for simplicity, could be from DB/config file) ---
KNOWLEDGE_BASE = {
    "business_name": "Take 5 Oil Change Orangeville",
    "address": "220 Centennial Road, Orangeville, Ontario, L9W 5K2",
    "intersection": "Riddell Road and Centennial Road",
    "hours": {
        "Mon-Fri": "8 a.m. to 8 p.m.",
        "Sat": "8 a.m. to 6 p.m.",
        "Sun": "9 a.m. to 5 p.m.",
        "Holidays": "shorter hours" # Specific holiday hours would need to be manually updated
    },
    "no_appointment": True,
    "drive_thru": True,
    "avg_oil_change_time": "12 minutes or less",
    "services": {
        "oil change economy": {"description": "Up to 6 liters", "price": "59 dollars and 99 cents"},
        "oil change synthetic blend": {"description": "Up to 6 liters", "price": "79 dollars and 99 cents"},
        "oil change full synthetic": {"description": "Up to 6 liters", "price": "99 dollars and 99 cents"},
        "coolant exchange": {"description": "Includes up to 10 liters coolant", "price": "149 dollars and 99 cents"},
        "rust proofing": {"description": "Sedan: 59 dollars and 99 cents, SUV or Van: 79 dollars and 99 cents, XL vehicles are additional", "price_varies": True},
        "tire rotation": {"description": "Sedan: 55 dollars and 99 cents, SUV or Van: 79 dollars and 99 cents, Truck: 89 dollars and 99 cents (plus 10 dollars for oversized)", "price_varies": True},
        "tire changeover": {"description": "Same pricing as rotation", "price_varies": True},
        "air & cabin filters": {"description": "Price depends on vehicle, please visit us for a quote", "request_details": True},
    },
    "shop_fee": "4 dollars and 45 cents (before tax)"
}

# --- Chatbot Logic (Keyword-based) ---
def get_bot_response(user_utterance, call_sid):
    user_utterance_lower = user_utterance.lower()
    response_text = ""

    # Intent 1: Oil Change Pricing
    if "oil change" in user_utterance_lower and ("price" in user_utterance_lower or "cost" in user_utterance_lower or "much" in user_utterance_lower):
        economy_price = KNOWLEDGE_BASE['services']['oil change economy']['price']
        blend_price = KNOWLEDGE_BASE['services']['oil change synthetic blend']['price']
        full_synth_price = KNOWLEDGE_BASE['services']['oil change full synthetic']['price']
        response_text = (
            f"Full synthetic oil changes start at {full_synth_price}, synthetic blend at {blend_price}, "
            f"and economy at {economy_price}. That includes up to six liters. No appointment needed—you can just drive in anytime."
        )
    # Intent 2: Hours
    elif "hours" in user_utterance_lower or "open" in user_utterance_lower:
        response_text = (
            f"Our hours are: Monday through Friday {KNOWLEDGE_BASE['hours']['Mon-Fri']}, "
            f"Saturday {KNOWLEDGE_BASE['hours']['Sat']}, and Sunday {KNOWLEDGE_BASE['hours']['Sun']}."
            f" Most holidays have shorter hours. No appointment needed!"
        )
    # Intent 3: Location
    elif "location" in user_utterance_lower or "where are you" in user_utterance_lower or "address" in user_utterance_lower:
        response_text = (
            f"We are located at {KNOWLEDGE_BASE['address']}, near {KNOWLEDGE_BASE['intersection'].split(' and ')[0]}."
            f" We're open {KNOWLEDGE_BASE['hours']['Mon-Fri']} weekdays for drive-thru service, no appointment needed!"
        )
    # Intent 4: Specific Services (Coolant, Rust Proofing, Tires, Air/Cabin Filters)
    elif "coolant" in user_utterance_lower:
        coolant_info = KNOWLEDGE_BASE['services']['coolant exchange']
        response_text = (
            f"Yes, we offer coolant exchange including up to 10 liters of coolant, for {coolant_info['price']}."
            f" No appointment is needed, just drive in!"
        )
    elif "rust proofing" in user_utterance_lower:
        rust_info = KNOWLEDGE_BASE['services']['rust proofing']
        response_text = (
            f"We offer rust proofing. Pricing varies: {rust_info['description']}. "
            f"We can confirm the exact price for your vehicle when you stop by—no appointment needed!"
        )
    elif "tire rotation" in user_utterance_lower or "tire changeover" in user_utterance_lower:
        tire_info = KNOWLEDGE_BASE['services']['tire rotation']
        response_text = (
            f"Yes, we do tire rotations and on-rim changeovers. Pricing starts at {tire_info['description'].split(',')[0]}. "
            f"We can confirm the exact price for your vehicle when you stop by—no appointment needed!"
        )
    elif "air filter" in user_utterance_lower or "cabin filter" in user_utterance_lower:
        air_filter_info = KNOWLEDGE_BASE['services']['air & cabin filters']
        response_text = (
            f"Yes, we replace air and cabin filters. {air_filter_info['description']}. "
            f"Please visit us, no appointment is needed!"
        )
    # Intent 5: Services NOT Provided
    elif any(word in user_utterance_lower for word in ["brakes", "engine", "repair", "diagnostic", "check engine", "mechanical"]):
        response_text = "We don’t do full mechanical work here—just quick drive-thru maintenance like oil changes, air and cabin filters, coolant, and tires. Stop by anytime, no appointment needed!"
    # Intent 6: Coupon Request
    elif "coupon" in user_utterance_lower or "discount" in user_utterance_lower:
        response_text = "Sure thing. I can text you ten dollars off your next visit. To receive it, please provide your phone number after the beep. Otherwise, you can ask about other services or just stop by."
    # Fallback / General Inquiry
    else:
        response_text = "I can confirm that at the shop when you stop by—no appointment needed."

    return response_text

# --- Flask Routes ---
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
            # Gather DTMF input (phone number)
            response.gather(input='dtmf', numDigits=10, timeout=10, action='/gather_phone_number', finishOnKey='#')
        else:
            # Continue gathering speech for further questions
            response.gather(input='speech', speechTimeout='auto', timeout=3, action='/voice')

    else:
        # This branch is for the very first incoming call, or if user was silent
        greeting = "Thank you for calling Take 5 Orangeville! How can I help you today?"
        response.say(greeting, voice='en-CA-Standard-A')
        logger.info(f"Initial greeting for CallSid {call_sid}: {greeting}")

        # Store initial greeting
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

        # Always gather speech after initial greeting to allow for user input
        response.gather(input='speech', speechTimeout='auto', timeout=3, action='/voice')
    
    return str(response)

@app.route("/gather_phone_number", methods=['POST'])
def gather_phone_number():
    """Handles the DTMF input for phone number for coupon."""
    response = VoiceResponse()
    call_sid = request.values.get('CallSid')
    digits = request.values.get('Digits') # The DTMF digits entered by the user

    if digits and len(digits) >= 10: # Basic validation for a 10-digit number
        phone_number = "+" + digits # Twilio expects E.164 format, e.g., +1XXXXXXXXXX

        # --- IMPORTANT: Uncomment the following lines to enable actual SMS sending ---
        # if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER:
        #     try:
        #         twilio_client.messages.create(
        #             to=phone_number,
        #             from_=TWILIO_PHONE_NUMBER, # Your Twilio number
        #             body="Here's your $10 off coupon for Take 5 Orangeville! Visit us soon!"
        #         )
        #         sms_confirmation_msg = f"Thank you! Your coupon has been sent to {digits}."
        #         logger.info(f"Coupon SMS sent to {phone_number} for CallSid {call_sid}.")
        #     except Exception as e:
        #         sms_confirmation_msg = "I'm sorry, I couldn't send the SMS coupon right now."
        #         logger.error(f"Error sending SMS for CallSid {call_sid} to {phone_number}: {e}")
        # else:
        #     sms_confirmation_msg = "SMS sending is not configured, but thank you for providing your number."
        #     logger.warning("Twilio SMS credentials not set in environment variables.")

        # Default confirmation message if SMS sending is not enabled/configured
        sms_confirmation_msg = f"Thank you! Your coupon will be sent to {digits}. We look forward to seeing you. Goodbye!"


        response.say(sms_confirmation_msg, voice='en-CA-Standard-A')
        
        # Log this event to call_history as well
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

        response.hangup() # End the call after trying to send the coupon
    else:
        # If the digits are not 10 digits or no digits entered
        response.say("I didn't get a valid 10-digit phone number. Please call back if you'd like to try again or just stop by for service, no appointment needed. Goodbye!", voice='en-CA-Standard-A')
        logger.warning(f"Invalid phone number provided for CallSid {call_sid}: {digits}")
        response.hangup() # End the call

    return str(response)

if __name__ == "__main__":
    init_db() # Ensure database is set up
    app.run(host="0.0.0.0", port=5000, debug=True)