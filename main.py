import streamlit as st # type: ignore
import spacy # type: ignore
import speech_recognition as sr
import re
import psycopg2
from datetime import datetime, timedelta
import google.generativeai as genai  # type: ignore # Gemini API
import json  # For parsing Gemini's JSON response
from fpdf import FPDF  # type: ignore # For generating PDF invoices

# Load spaCy model
nlp = spacy.load("en_core_web_sm")

# Initialize Gemini API
GEMINI_API_KEY = "GEMINI_API_KEY"  # Replace with your Gemini API key
genai.configure(api_key=GEMINI_API_KEY)

# Use the correct model name
gemini_model = genai.GenerativeModel('gemini-1.5-pro-latest')  # Updated model name

# PostgreSQL connection details
DB_HOST = "localhost"       # Replace with your database host
DB_NAME = "speech"          # Replace with your database name
DB_USER = "postgres"        # Replace with your database username
DB_PASSWORD = "Arun2146"    # Replace with your database password

def connect_to_db():
    """Connect to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except Exception as e:
        st.error(f"Error connecting to the database: {e}")
        return None

def create_table_if_not_exists(conn):
    """Create the table if it doesn't exist."""
    create_table_query = """
    CREATE TABLE IF NOT EXISTS transactions (
        id SERIAL PRIMARY KEY,
        service TEXT,
        price TEXT,
        tax TEXT,
        payment_method TEXT,
        billing_address TEXT,
        shipping_address TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    try:
        with conn.cursor() as cursor:
            cursor.execute(create_table_query)
            conn.commit()
    except Exception as e:
        st.error(f"Error creating table: {e}")

def insert_into_db(conn, data):
    """Insert extracted data into the PostgreSQL database."""
    insert_query = """
    INSERT INTO transactions (service, price, tax, payment_method, billing_address, shipping_address)
    VALUES (%s, %s, %s, %s, %s, %s);
    """
    try:
        with conn.cursor() as cursor:
            cursor.execute(insert_query, (
                data["Service"],
                data["Price"],
                data["Tax"],
                data["Payment Method"],
                data["Billing Address"],
                data["Shipping Address"]
            ))
            conn.commit()
            st.success("Data inserted successfully!")
    except Exception as e:
        st.error(f"Error inserting data into the database: {e}")

def correct_grammar(sentence):
    """Correct grammar of a sentence using Gemini API."""
    try:
        prompt = f"Correct the grammar of the following sentence: {sentence}"
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        st.error(f"Grammar correction failed: {e}")
        return sentence

def extract_keywords(sentence):
    """
    Extract keywords (Service, Price, Tax, Payment Method, Billing Address, Shipping Address)
    from a sentence using Gemini API.
    """
    try:
        # Use Gemini to extract structured information
        prompt = f"""
        Extract the following details from the sentence below:
        - Service: The service being offered or requested.
        - Price: The price mentioned (e.g., $100).
        - Tax: The tax rate or amount mentioned (e.g., 10% or $10).
        - Payment Method: The payment method mentioned (e.g., credit card, PayPal).
        - Billing Address: The billing address mentioned.
        - Shipping Address: The shipping address mentioned.

        Sentence: "{sentence}"

        Return the details in the following JSON format:
        {{
            "Service": "service name or null",
            "Price": "price or null",
            "Tax": "tax or null",
            "Payment Method": "payment method or null",
            "Billing Address": "billing address or null",
            "Shipping Address": "shipping address or null"
        }}

        Example:
        Input: "I need a graphic design service for $100 with a 10% tax. My billing address is 123 Main St, and the shipping address is 456 Elm St. I'll pay with a credit card."
        Output:
        {{
            "Service": "graphic design",
            "Price": "$100",
            "Tax": "10%",
            "Payment Method": "credit card",
            "Billing Address": "123 Main St",
            "Shipping Address": "456 Elm St"
        }}
        """
        
        # Send the prompt to Gemini
        response = gemini_model.generate_content(prompt)
        extracted_data = response.text.strip()

        # Debug: Print the raw response from Gemini
        st.write("Gemini Raw Response:", extracted_data)

        # Try to parse the response as JSON
        try:
            data = json.loads(extracted_data)
            return data
        except json.JSONDecodeError:
            st.warning("Failed to parse Gemini response as JSON. Attempting to extract fields using regex.")
            # Fallback: Use regex to extract fields from the raw response
            service_match = re.search(r'"Service":\s*"([^"]+)"', extracted_data)
            price_match = re.search(r'"Price":\s*"([^"]+)"', extracted_data)
            tax_match = re.search(r'"Tax":\s*"([^"]+)"', extracted_data)
            payment_method_match = re.search(r'"Payment Method":\s*"([^"]+)"', extracted_data)
            billing_address_match = re.search(r'"Billing Address":\s*"([^"]+)"', extracted_data)
            shipping_address_match = re.search(r'"Shipping Address":\s*"([^"]+)"', extracted_data)

            return {
                "Service": service_match.group(1) if service_match else None,
                "Price": price_match.group(1) if price_match else None,
                "Tax": tax_match.group(1) if tax_match else None,
                "Payment Method": payment_method_match.group(1) if payment_method_match else None,
                "Billing Address": billing_address_match.group(1) if billing_address_match else None,
                "Shipping Address": shipping_address_match.group(1) if shipping_address_match else None
            }
    except Exception as e:
        st.error(f"Error extracting keywords with Gemini: {e}")
        # Fallback to regex-based extraction
        return extract_keywords_with_regex(sentence)

def extract_keywords_with_regex(sentence):
    """
    Extract keywords (Service, Price, Tax, Payment Method, Billing Address, Shipping Address)
    from a sentence using regex as a fallback.
    """
    try:
        # Extract Service
        service_match = re.search(r"(social media management|graphic design|design service)", sentence, re.IGNORECASE)
        service = service_match.group(1) if service_match else None

        # Extract Price
        price_match = re.search(r"\$\d+|\d+\s*dollars", sentence, re.IGNORECASE)
        price = price_match.group(0) if price_match else None

        # Extract Tax
        tax_match = re.search(r"\b(\d+)%", sentence)
        tax = tax_match.group(1) + "%" if tax_match else None

        # Extract Payment Method
        payment_methods = ["credit card", "debit card", "cash", "paypal", "bank transfer"]
        payment_method = None
        for method in payment_methods:
            if method in sentence.lower():
                payment_method = method
                break

        # Extract Billing Address
        billing_match = re.search(r"billing address is ([A-Za-z]+)", sentence, re.IGNORECASE)
        billing_address = billing_match.group(1) if billing_match else None

        # Extract Shipping Address
        shipping_match = re.search(r"shipping address is ([A-Za-z]+)", sentence, re.IGNORECASE)
        shipping_address = shipping_match.group(1) if shipping_match else None

        return {
            "Service": service,
            "Price": price,
            "Tax": tax,
            "Payment Method": payment_method,
            "Billing Address": billing_address,
            "Shipping Address": shipping_address
        }
    except Exception as e:
        st.error(f"Error extracting keywords with regex: {e}")
        return {
            "Service": None,
            "Price": None,
            "Tax": None,
            "Payment Method": None,
            "Billing Address": None,
            "Shipping Address": None
        }

def generate_invoice(data, filename="invoice.pdf"):
    """Generate a PDF invoice matching the provided sample format."""
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)

        # Add company header
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "East Repair Inc.", ln=1)
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, "1912 Harvest Lane", ln=1)
        pdf.cell(0, 10, "New York, NY 12210", ln=1)
        pdf.ln(10)

        # Add bill to/ship to sections
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(95, 10, "BILL TO:", ln=0)
        pdf.cell(95, 10, "SHIP TO:", ln=1)
        pdf.set_font("Arial", size=12)
        pdf.cell(95, 10, data.get("Billing Address", "N/A"), ln=0)
        pdf.cell(95, 10, data.get("Shipping Address", "N/A"), ln=1)
        pdf.ln(10)

        # Add invoice details
        pdf.cell(40, 10, "INVOICE #", border=0, ln=0)
        pdf.cell(50, 10, "US-001", border=0, ln=0)
        pdf.cell(40, 10, "INVOICE DATE", border=0, ln=0)
        pdf.cell(50, 10, datetime.now().strftime("%m/%d/%Y"), border=0, ln=1)
        
        pdf.cell(40, 10, "P.O.#", border=0, ln=0)
        pdf.cell(50, 10, "2312/2019", border=0, ln=0)
        pdf.cell(40, 10, "DUE DATE", border=0, ln=0)
        pdf.cell(50, 10, (datetime.now() + timedelta(days=15)).strftime("%m/%d/%Y"), border=0, ln=1)
        pdf.ln(10)

        # Add table headers
        pdf.set_fill_color(200, 200, 200)
        pdf.cell(20, 10, "QTY", border=1, fill=True, align="C")
        pdf.cell(75, 10, "DESCRIPTION", border=1, fill=True)
        pdf.cell(50, 10, "UNIT PRICE", border=1, fill=True, align="R")
        pdf.cell(45, 10, "AMOUNT", border=1, fill=True, align="R")
        pdf.ln()

        # Add line item
        unit_price = re.sub(r'[^\d.]', '', data.get("Price", "0")) if data.get("Price") else "0"
        qty = 1
        amount = float(unit_price) if unit_price else 0.0
        
        pdf.cell(20, 10, str(qty), border=1, align="C")
        pdf.cell(75, 10, data.get("Service", "N/A"), border=1)
        pdf.cell(50, 10, f"${float(unit_price):.2f}", border=1, align="R")
        pdf.cell(45, 10, f"${amount:.2f}", border=1, align="R")
        pdf.ln()

        # Calculate totals
        tax_rate = float(re.sub(r'[^\d.]', '', data.get("Tax", "0"))) if data.get("Tax") else 0.0
        tax_amount = amount * (tax_rate / 100)
        total = amount + tax_amount

        # Add totals
        pdf.cell(145, 10, "Subtotal", border=1, align="R")
        pdf.cell(45, 10, f"${amount:.2f}", border=1, align="R")
        pdf.ln()
        
        pdf.cell(145, 10, f"Sales Tax {tax_rate:.2f}%", border=1, align="R")
        pdf.cell(45, 10, f"${tax_amount:.2f}", border=1, align="R")
        pdf.ln()
        
        pdf.cell(145, 10, "TOTAL", border=1, align="R", fill=True)
        pdf.cell(45, 10, f"${total:.2f}", border=1, align="R", fill=True)
        pdf.ln(20)

        # Add terms
        pdf.multi_cell(0, 10, "TERMS & CONDITIONS\nPayment is due within 15 days\n\nThank you\nPlease make checks payable to: East Repair Inc.")

        # Save PDF
        pdf.output(filename)
        st.success(f"Invoice generated: {filename}")
        return filename
    except Exception as e:
        st.error(f"Error generating invoice: {e}")
        return None

def get_audio_input():
    """Capture audio input and convert to text."""
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        st.info("Please speak the sentence...")
        try:
            audio = recognizer.listen(source)
            sentence = recognizer.recognize_google(audio)
            st.write(f"You said (raw): {sentence}")
            return sentence
        except sr.UnknownValueError:
            st.warning("Sorry, I couldn't understand the audio.")
        except sr.RequestError as e:
            st.error(f"Error with the speech recognition service: {e}")
    return None

def main():
    st.title("Invoice Generator")
    st.write("This app extracts details from a spoken sentence and generates an invoice.")

    # Connect to the database
    conn = connect_to_db()
    if conn is None:
        return

    # Create the table if it doesn't exist
    create_table_if_not_exists(conn)

    # Input options
    input_method = st.radio("Choose input method:", ("Text Input", "Voice Input"))

    if input_method == "Text Input":
        sentence = st.text_input("Enter the sentence:")
    else:
        if st.button("Start Recording"):
            sentence = get_audio_input()
        else:
            sentence = None

    if sentence:
        # Correct grammar
        corrected_sentence = correct_grammar(sentence)
        st.write(f"Corrected Sentence: {corrected_sentence}")

        # Extract keywords
        keywords = extract_keywords(corrected_sentence)
        st.write("Extracted Keywords:", keywords)

        # Insert data into the database
        insert_into_db(conn, keywords)

        # Generate and download the invoice
        invoice_file = generate_invoice(keywords)
        if invoice_file:
            with open(invoice_file, "rb") as f:
                st.download_button(
                    label="Download Invoice",
                    data=f,
                    file_name="invoice.pdf",
                    mime="application/pdf"
                )

    # Close the database connection
    conn.close()

if __name__ == "__main__":
    main()