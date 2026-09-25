import os
import re
import requests
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://bloeoxrxgtgzsccoscgo.supabase.co").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def save_subscriber_to_supabase(email, monthly_investment, years):
    """
    Saves a subscriber email to Supabase database ('subscribers' table).
    Falls back gracefully with helpful guidance if SUPABASE_KEY is not configured yet.
    """
    supabase_url = os.environ.get("SUPABASE_URL", "https://bloeoxrxgtgzsccoscgo.supabase.co").strip()
    supabase_key = os.environ.get("SUPABASE_KEY", "").strip()

    if not supabase_key:
        print("[WARN] SUPABASE_KEY environment variable is missing in .env.")
        return {
            "status": "success",
            "message": "Thank you! You are subscribed (Pending SUPABASE_KEY in .env).",
            "demo_mode": True,
        }

    headers = {
        "apikey": supabase_key,
        "Authorization": "Bearer " + supabase_key,
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    endpoint = supabase_url.rstrip("/") + "/rest/v1/subscribers"
    payload = {
        "email": email,
        "monthly_investment": float(monthly_investment) if monthly_investment is not None else None,
        "target_years": int(years) if years is not None else 8,
    }

    try:
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=8)
        if resp.status_code in (200, 201):
            return {
                "status": "success",
                "message": "Success! You are subscribed to future financial growth updates.",
            }
        if resp.status_code == 409 or "duplicate key" in resp.text.lower() or "23505" in resp.text:
            return {
                "status": "success",
                "message": "Welcome back! You are already on our notification list.",
            }
        if resp.status_code == 404 or "pgrst205" in resp.text or 'relation "public.subscribers" does not exist' in resp.text:
            print("[Supabase Warning] 'subscribers' table does not exist yet. Please run the SQL schema script.")
            return {
                "status": "success",
                "message": "Subscribed! (Note: Create 'subscribers' table in Supabase dashboard to persist)",
                "table_missing": True,
            }
        print(f"[Supabase API Error {resp.status_code}]: {resp.text}")
        return {
            "status": "error",
            "error": f"Database error ({resp.status_code}): {resp.text}",
        }
    except Exception as e:
        print(f"[Supabase Exception]: {e}")
        return {
            "status": "error",
            "error": f"Could not connect to Supabase: {str(e)}",
        }


def calculate_sip(monthly_investment, annual_rate_percent, years):
    """
    SIP Growth Calculation core logic.
    - Inputs: monthly_investment (Rs.), annual_rate_percent, years
    - monthly_rate = annual_rate_percent / 100 / 12
    - For each month: balance += monthly_investment, then balance *= (1 + monthly_rate)
    - At the end of every 12th month, record {year, total_invested, total_value, gain}
    """
    monthly_rate = annual_rate_percent / 100.0 / 12.0
    balance = 0.0
    total_invested = 0.0
    yearly_data = []

    for month in range(1, int(years) * 12 + 1):
        balance += monthly_investment
        total_invested += monthly_investment
        balance *= (1.0 + monthly_rate)
        if month % 12 == 0:
            year = month // 12
            gain = balance - total_invested
            yearly_data.append({
                "year": year,
                "total_invested": round(total_invested, 2),
                "total_value": round(balance, 2),
                "gain": round(gain, 2),
            })

    total_value = balance
    total_gain = total_value - total_invested
    gain_percentage = (total_gain / total_invested * 100) if total_invested > 0 else 0.0

    summary = {
        "monthly_investment": monthly_investment,
        "annual_rate": annual_rate_percent,
        "years": years,
        "total_invested": round(total_invested, 2),
        "total_value": round(total_value, 2),
        "total_gain": round(total_gain, 2),
        "gain_percentage": round(gain_percentage, 2),
    }
    return {"summary": summary, "yearly_data": yearly_data}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/calculate", methods=["POST", "GET"])
def calculate_api():
    try:
        if request.method == "POST":
            data = request.get_json() or {}
            monthly_investment = float(data.get("monthly_investment", 5000))
            annual_rate_percent = float(data.get("annual_rate_percent", 12))
            years = int(data.get("years", 15))
        else:
            monthly_investment = float(request.args.get("monthly_investment", 5000))
            annual_rate_percent = float(request.args.get("annual_rate_percent", 12))
            years = int(request.args.get("years", 15))

        if monthly_investment <= 0:
            return jsonify({"status": "error", "error": "Monthly investment must be greater than 0"}), 400
        if not (0 <= annual_rate_percent <= 100):
            return jsonify({"status": "error", "error": "Annual rate must be between 0% and 100%"}), 400
        if not (1 <= years <= 50):
            return jsonify({"status": "error", "error": "Duration must be between 1 and 50 years"}), 400

        result = calculate_sip(monthly_investment, annual_rate_percent, years)
        return jsonify({"status": "success", "data": result})
    except (ValueError, TypeError) as e:
        return jsonify({"status": "error", "error": f"Invalid input parameters: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"status": "error", "error": f"An unexpected error occurred: {str(e)}"}), 500


@app.route("/api/subscribe", methods=["POST"])
def subscribe_api():
    try:
        data = request.get_json() or {}
        email = (data.get("email") or "").strip()
        monthly_investment = data.get("monthly_investment")
        years = data.get("years")

        if not email or not EMAIL_REGEX.match(email):
            return jsonify({"status": "error", "error": "Please provide a valid email address."}), 400

        result = save_subscriber_to_supabase(email, monthly_investment, years)
        if result.get("status") == "success":
            return jsonify(result), 200
        return jsonify(result), 500
    except Exception as e:
        return jsonify({"status": "error", "error": f"Subscription failed: {str(e)}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting SIP Growth Calculator on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
