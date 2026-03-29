from flask import Flask, render_template, request, jsonify
import requests
import os

app = Flask(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/get_hospitals", methods=["POST"])
def get_hospitals():
    data = request.json
    city = data.get("city", "Chennai")

    # Step 1: Get city coordinates
    geocode_url = f"https://nominatim.openstreetmap.org/search?q={city},India&format=json&limit=1"
    headers = {"User-Agent": "HealthcareDesertDetector/1.0"}
    geo_response = requests.get(geocode_url, headers=headers)
    geo_data = geo_response.json()

    if not geo_data:
        return jsonify({"error": "City not found"}), 404

    lat = float(geo_data[0]["lat"])
    lon = float(geo_data[0]["lon"])

    # Step 2: Fetch real hospitals
    overpass_url = "https://overpass-api.de/api/interpreter"
    query = f"""
[out:json][timeout:40];
(
  node["amenity"="hospital"](around:20000,{lat},{lon});
  node["amenity"="clinic"](around:20000,{lat},{lon});
  node["amenity"="doctors"](around:20000,{lat},{lon});
);
out body;
"""

    # Initialize hospitals list BEFORE try block
    hospitals = []

    try:
        overpass_response = requests.post(
            overpass_url,
            data=query,
            timeout=45,
            headers={"User-Agent": "HealthcareDesertDetector/1.0"}
        )
        if overpass_response.status_code == 200:
            overpass_data = overpass_response.json()
            for element in overpass_data.get("elements", []):
                name = element.get("tags", {}).get("name", "Unknown Facility")
                hospitals.append({
                    "name": name,
                    "lat": element["lat"],
                    "lon": element["lon"],
                    "type": element["tags"].get("amenity", "hospital")
                })
        print(f"City: {city} | Hospitals found: {len(hospitals)} | Status: {overpass_response.status_code}")

    except Exception as e:
        print(f"Overpass API error for {city}: {e}")
        hospitals = []

    # Step 3: Find desert zones
    desert_zones = find_desert_zones(lat, lon, hospitals)

    # Step 4: Ask AI for recommendations
    ai_recommendation = get_ai_recommendation(city, len(hospitals), desert_zones)

    return jsonify({
        "city": city,
        "center": {"lat": lat, "lon": lon},
        "hospitals": hospitals,
        "total": len(hospitals),
        "desert_zones": desert_zones,
        "ai_recommendation": ai_recommendation
    })


def find_desert_zones(center_lat, center_lon, hospitals):
    import math
    desert_zones = []
    grid_size = 0.03

    for i in range(-2, 3):
        for j in range(-2, 3):
            grid_lat = center_lat + (i * grid_size)
            grid_lon = center_lon + (j * grid_size)

            has_hospital = False
            for h in hospitals:
                dist = math.sqrt(
                    (h["lat"] - grid_lat) ** 2 +
                    (h["lon"] - grid_lon) ** 2
                ) * 111

                if dist < 3:
                    has_hospital = True
                    break

            if not has_hospital:
                desert_zones.append({
                    "lat": grid_lat,
                    "lon": grid_lon,
                    "risk": "HIGH"
                })

    return desert_zones


def get_ai_recommendation(city, hospital_count, desert_zones):
    desert_count = len(desert_zones)

    prompt = f"""You are a senior healthcare infrastructure analyst for Indian cities.

Data:
- City: {city}
- Total hospitals/clinics found: {hospital_count}
- Desert zones detected (areas with zero healthcare within 3km): {desert_count}

Write a detailed 4-line analysis:
Line 1: Overall healthcare status of {city} based on the numbers
Line 2: Which type of areas are likely affected (outskirts, slums, industrial zones, coastal areas etc based on city geography)
Line 3: Estimated population at risk (calculate roughly based on average Indian urban density of 10,000 people per sq km and 3km radius zones)
Line 4: Specific government action with exact facility type (PHC, CHC, mobile unit) and urgency level

Be specific to {city}'s geography. No bullet points. No headings. Just 4 direct sentences. Max 100 words."""

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200
            },
            timeout=45
        )
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Groq API error: {e}")
        return f"AI analysis unavailable. City: {city} has {hospital_count} facilities and {desert_count} desert zones detected."


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
