import requests
from datetime import datetime, timedelta
import json
import logging
import os
import time
from playwright.sync_api import sync_playwright
import pytz
import uuid

# Configure logging to a file for persistent debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('flixbus_script.log'),
        logging.StreamHandler()
    ]
)

# Predefined station IDs
stations = {
    "Brasília": "986d85ad-cb8a-4d15-ae26-108e1ba826fc",
    "Fortaleza": "50fb8131-2e48-437e-a354-0dd2f85a13f2",
    "Recife": "dfaf1760-e4a4-4285-99be-ccd49874e24b",
    "Natal": "8f48d082-eb23-468a-9f8f-e4cd2173084b",
    "Salvador": "98ea5d49-948d-40b2-a0d6-d936a8e81ae7",
    "São Paulo": "7838929e-3d6c-4f9a-97cb-fb32a9a40c57",
    "Rio de Janeiro": "335cd12f-2179-4128-add3-25f3ca239367",
    "Campinas": "fcb87a56-c23f-4c6b-83b8-0f2cf87cd9d2",
    "Angra dos Reis": "e6d0d405-e718-4299-a72a-8b0f0e769e72",
    "Goiânia": "3bc5c47d-913b-41cb-911b-7a9de96b014a",
    "Guarulhos": "cbab2d9f-2ac1-4b5f-a186-9d17f2c7182b",
    "Uberlândia": "0e46fcf0-a7d5-4724-8b98-2b6f12dc1d0c",
    "São José dos Pinhais": "2e1db179-23c6-4cf3-a0f3-73fa4ecd747e",
    "Santa Rosa": "9e2e2233-c835-499a-96b7-31f270a8ead5",
    "Itajai": "5071eebb-6b97-48df-86d9-5cb75965811f",
    "Sabara": "304157ca-505a-4d30-b046-350ff1bc1db3",
    "Blumenau": "46b88ab1-79ae-49b4-b0b1-2e6a7409cf84",
    "Balneário do Camboriú": "be940685-6708-4f6f-8d04-c29937e11daf"
}

# FlixBus API configuration
flixbus_api_base_url = "https://global.api.flixbus.com/gis/v2/timetable/{}/departures"
flixbus_api_key = "d3279fed-c793-4801-a659-8646e4415d98"
flixbus_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# Azure Logic Apps configuration
azure_endpoint = "https://prod-120.westeurope.logic.azure.com:443/workflows/89844cad543848848e9279b845b8fd94/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=aqBnONnFyLuU1BgucnPOy3mOtynJVCK9MPkCeiXvQ8w"
azure_endpoint_screenshot = "https://prod-09.westeurope.logic.azure.com:443/workflows/bf2eac10eae844b890e5cc116f5f88ce/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=i2UWenb2yU7haI3NuIJuDeYSymTKfBRBajem1-uiyZU"
azure_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# Track sent trips (trip_id, delay_minutes) and last reset date
sent_trips = set()
last_reset_date = datetime.now(pytz.timezone('America/Sao_Paulo')).date()

def reset_sent_trips():
    """Reset sent_trips daily at midnight UTC-3."""
    global sent_trips, last_reset_date
    now = datetime.now(pytz.timezone('America/Sao_Paulo'))
    current_date = now.date()
    if current_date > last_reset_date:
        logging.info("Resetting sent_trips for new day.")
        sent_trips.clear()
        last_reset_date = current_date

def format_time(timestamp_str, tz=pytz.timezone('America/Sao_Paulo')):
    """Convert timestamp to HH:MM in UTC-3, treating all inputs as UTC."""
    try:
        logging.info(f"format_time input: {timestamp_str}")
        if timestamp_str.endswith('Z'):
            timestamp_str = timestamp_str[:-1] + '+00:00'
        else:
            time_part = timestamp_str[:19]
            if len(timestamp_str) > 19 and ('+' in timestamp_str[19:] or '-' in timestamp_str[19:]):
                timestamp_str = time_part + '+00:00'
            else:
                timestamp_str = timestamp_str + '+00:00'
        dt = datetime.fromisoformat(timestamp_str)
        dt = dt.astimezone(tz)
        formatted_time = dt.strftime("%H:%M")
        logging.info(f"Converted timestamp: {timestamp_str} -> {dt} ({formatted_time}) in {tz}")
        return formatted_time
    except ValueError as e:
        logging.error(f"Error parsing timestamp {timestamp_str}: {e}")
        return "Unknown"

def take_screenshot(trip_id, output_path=None):
    """Capture a screenshot of the FlixBus tracking page for the given trip_id."""
    if output_path is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(script_dir, f"screenshot_{trip_id}.png")
    
    logging.info(f"Attempting to save screenshot to: {output_path}")
    url = f"https://www.flixbus.com.br/track/ride/{trip_id}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        )
        
        try:
            logging.info(f"Navigating to {url}")
            page.goto(url, wait_until="networkidle")
            
            page.evaluate("document.body.style.zoom = '80%'")
            logging.info("Zoom set to 80%")
            
            accept_button_found = False
            for attempt in range(3):
                try:
                    page.wait_for_selector("[data-testid='uc-accept-all-button']", timeout=10000)
                    page.click("[data-testid='uc-accept-all-button']")
                    logging.info("Clicked 'Accept All' button")
                    accept_button_found = True
                    page.wait_for_timeout(2000)
                    break
                except Exception as e:
                    logging.info(f"Attempt {attempt + 1} failed to find 'Accept All' button: {e}")
                    page.wait_for_timeout(2000)
            
            if not accept_button_found:
                try:
                    page.wait_for_selector("button:has-text('Accept All')", timeout=10000)
                    page.click("button:has-text('Accept All')")
                    logging.info("Clicked 'Accept All' button (fallback method)")
                    page.wait_for_timeout(2000)
                except Exception as e:
                    logging.info(f"Error with fallback method: {e}")
            
            try:
                page.wait_for_selector(".map-container", timeout=15000)
                logging.info("Map element detected")
            except Exception as e:
                logging.info(f"Error waiting for map element: {e}. Trying to proceed anyway.")
            
            page.wait_for_timeout(5000)
            
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(2000)
            
            content = page.content()
            if len(content) < 1000 or "<body" not in content.lower():
                logging.warning("Warning: Page content seems empty.")
                logging.warning(f"Page source snippet: {content[:500]}...")
            
            page.screenshot(path=output_path, full_page=False)
            logging.info(f"Screenshot saved to {output_path}")
            
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                if file_size == 0:
                    logging.error(f"Empty screenshot saved at {output_path}")
                    raise ValueError("Empty screenshot detected")
                logging.info(f"Screenshot file verified: {output_path}, Size: {file_size} bytes")
            else:
                logging.error(f"Screenshot file not found at {output_path}")
                raise FileNotFoundError(f"Screenshot file not found at {output_path}")
            
        except Exception as e:
            logging.error(f"Error during screenshot process for trip {trip_id}: {e}")
            raise
        finally:
            browser.close()
    return output_path

from PIL import Image  # Add this import at the top of your script

def send_to_azure_logic_apps(trip):
    """Send trip data as JSON to azure_endpoint and screenshot URL to azure_endpoint_screenshot."""
    trip_id = trip.get("trip_id", "Unknown")
    delay_minutes = int(trip["delay_seconds"] / 60)
    trip_key = (trip_id, delay_minutes)

    if trip_key in sent_trips:
        logging.info(f"Skipping duplicate send for trip_id {trip_id} with delay {delay_minutes} minutes")
        return

    # Take a screenshot of the tracking page
    screenshot_filepath = None
    try:
        screenshot_filepath = take_screenshot(trip_id)
    except Exception as e:
        logging.error(f"Failed to capture screenshot for trip {trip_id}: {e}")
        return

    # Resize and convert screenshot to JPEG
    jpeg_filepath = None
    if screenshot_filepath and os.path.exists(screenshot_filepath):
        try:
            with Image.open(screenshot_filepath) as img:
                # Convert to JPEG
                jpeg_filepath = screenshot_filepath.rsplit('.', 1)[0] + '.jpg'
                img.convert('RGB').save(jpeg_filepath, 'JPEG', quality=85)
                logging.info(f"Converted and resized screenshot to {jpeg_filepath}")
            # Remove original screenshot file
            os.remove(screenshot_filepath)
            logging.info(f"Deleted original screenshot: {screenshot_filepath}")
            screenshot_filepath = jpeg_filepath
        except Exception as e:
            logging.error(f"Error resizing/converting screenshot for trip {trip_id}: {e}")
            # Proceed with original screenshot if conversion fails
            jpeg_filepath = None

    # Prepare JSON payload for metadata
    json_payload = {
        "city": trip["city"],
        "scheduled_time": format_time(trip["scheduled_time"]),
        "actual_time": format_time(trip["actual_time"]),
        "final_destination": trip["final_destination"] if trip["final_destination"] != "Unknown" else "Not Specified",
        "timestamp": datetime.now(pytz.timezone('America/Sao_Paulo')).isoformat(),
        "delay_minutes": delay_minutes,
        "line_code": trip["line_code"],
        "trip_id": trip_id,
        "downgrade_comment": "LowCatRefund" if trip.get("is_downgrade", False) else ""
    }

    # Send JSON payload to azure_endpoint
    try:
        logging.info(f"Sending JSON data to {azure_endpoint}: {json.dumps(json_payload, indent=2)}")
        logging.info(f"JSON request headers: {azure_headers}")
        response = requests.post(
            azure_endpoint,
            headers={"Content-Type": "application/json", "User-Agent": azure_headers["User-Agent"]},
            json=json_payload
        )
        response.raise_for_status()
        logging.info(f"JSON request sent to Azure Logic Apps: {json.dumps(json_payload, indent=2)}")
        logging.info(f"JSON response Status: {response.status_code}")
        logging.info(f"JSON response Content: {response.text}")
    except requests.RequestException as e:
        logging.error(f"Error sending JSON to Azure Logic Apps: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logging.error(f"JSON response content: {e.response.text}")
            logging.error(f"JSON response headers: {e.response.headers}")
        logging.info("Proceeding to attempt screenshot upload despite JSON failure")

    # Upload screenshot to Filebin.net and send URL to azure_endpoint_screenshot
    if screenshot_filepath and os.path.exists(screenshot_filepath):
        upload_success = False
        download_url = None

        try:
            with open(screenshot_filepath, "rb") as file_handle:
                bin_id = str(uuid.uuid4())[:8]  # Random bin ID
                filename = os.path.basename(screenshot_filepath)
                url = f"https://filebin.net/{bin_id}/{filename}"
                headers = {
                    "cid": str(uuid.uuid4())[:8],  # Optional custom client ID
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
                logging.info(f"Uploading screenshot to Filebin.net for trip_id {trip_id}: {url}")
                response = requests.put(
                    url,
                    data=file_handle,
                    headers=headers,
                    timeout=30
                )
                response.raise_for_status()
                upload_response = response.json()
                download_url = upload_response.get("url", url)  # Use the request URL as fallback if no redirect
                if download_url:
                    upload_success = True
                    logging.info(f"Screenshot uploaded to Filebin.net, URL: {download_url}")
                else:
                    logging.warning("Filebin.net returned no URL in response")
        except Exception as e:
            logging.error(f"Error uploading to Filebin.net: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logging.error(f"Filebin.net response content: {e.response.text}")

        # Send the URL to azure_endpoint_screenshot if upload succeeded
        if upload_success and download_url:
            try:
                payload = {
                    "screenshot_url": download_url,
                    "file_name": f"screenshot_{trip_id}.jpg"  # Updated to .jpg
                }
                logging.info(f"Sending URL to {azure_endpoint_screenshot}: {json.dumps(payload, indent=2)}")
                response = requests.post(
                    azure_endpoint_screenshot,
                    headers={"Content-Type": "application/json", "User-Agent": azure_headers["User-Agent"]},
                    json=payload
                )
                response.raise_for_status()
                logging.info(f"URL request sent to Azure Logic Apps: {json.dumps(payload, indent=2)}")
                logging.info(f"URL response Status: {response.status_code}")
                logging.info(f"URL response Content: {response.text}")
                sent_trips.add(trip_id)
            except Exception as e:
                logging.error(f"Error sending URL to Azure Logic Apps: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    logging.error(f"URL response content: {e.response.text}")

        # Clean up screenshot file
        if screenshot_filepath and os.path.exists(screenshot_filepath):
            try:
                with open(screenshot_filepath, "rb") as f:
                    pass  # Force close any lingering handle
                os.remove(screenshot_filepath)
                logging.info(f"Deleted temporary file: {screenshot_filepath}")
            except OSError as e:
                logging.error(f"Error deleting file {screenshot_filepath}: {e}")

def check_delays():
    """Check for delayed departures for all lines where the station is the first stop (partida)."""
    reset_sent_trips()

    now = datetime.now(pytz.timezone('America/Sao_Paulo'))
    logging.info(f"Current time in America/Sao_Paulo: {now}")
    from_time = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(pytz.timezone('UTC')).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    to_time = now.replace(hour=23, minute=59, second=59, microsecond=0).astimezone(pytz.timezone('UTC')).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    logging.info(f"Querying trips from {from_time} to {to_time}")

    seen_trip_ids = set()
    delayed_trips = []

    for city, station_id in stations.items():
        logging.info(f"Checking delays for {city} (ID: {station_id})...")
        url = flixbus_api_base_url.format(station_id) + f"?from={from_time}&to={to_time}&apiKey={flixbus_api_key}"
        try:
            response = requests.get(url, headers=flixbus_headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            logging.info(f"API response for {city}: {json.dumps(data, indent=2)}")
        except requests.RequestException as e:
            logging.error(f"Error accessing FlixBus API for {city}: {e}")
            continue

        for trip in data.get('rides', []):
            trip_id = trip.get('id', 'Unknown')
            if trip_id in seen_trip_ids:
                logging.info(f"Skipping duplicate trip ID {trip_id} in this run")
                continue
            seen_trip_ids.add(trip_id)
            deviation = trip.get('status', {}).get('deviation', {})
            if deviation and deviation.get('deviation_class') == 'LATE':
                calls = trip.get('calls', [])
                is_partida = any(
                    call.get('sequence') == 1 and call.get('stop', {}).get('id') == station_id
                    for call in calls
                )
                if not is_partida:
                    logging.info(f"Skipping trip ID {trip_id} with line {trip.get('line', {}).get('code', 'Unknown')} as it is not a partida from {city}")
                    continue
                final_destination = calls[-1].get('stop', {}).get('name', 'Unknown') if calls else "Unknown"
                scheduled_time = trip.get('status', {}).get('scheduled_timestamp', 'Unknown')
                actual_time = deviation.get('deviation_timestamp', 'Unknown')
                delay_seconds = deviation.get('deviation_seconds', 0)
                line_code = trip.get('line', {}).get('code', 'Unknown')

                logging.info(f"Trip ID {trip_id}: Raw scheduled_time={scheduled_time}, Raw actual_time={actual_time}")

                delayed_trips.append({
                    'city': city,
                    'scheduled_time': scheduled_time,
                    'actual_time': actual_time,
                    'final_destination': final_destination,
                    'delay_seconds': delay_seconds,
                    'line_code': line_code,
                    'trip_id': trip_id,
                    'is_downgrade': False
                })

    if delayed_trips:
        print("\n=== Delayed Departures ===")
        print(f"{'City':<15} {'Line':<10} {'Scheduled':<10} {'Actual':<10} {'Delay (min)':<12} {'Destination':<25}")
        print("-" * 80)
        for trip in delayed_trips:
            scheduled_formatted = format_time(trip['scheduled_time'])
            actual_formatted = format_time(trip['actual_time'])
            print(f"{trip['city']:<15} {trip['line_code']:<10} {scheduled_formatted:<10} {actual_formatted:<10} {int(trip['delay_seconds'] / 60):<12} {trip['final_destination']:<25}")
            send_to_azure_logic_apps(trip)
        print("====================")
    else:
        logging.info("No delayed departures found.")
        print("\nNo delayed departures found.")

# Main execution
if __name__ == "__main__":
    try:
        while True:
            print(f"\nCheck started at {datetime.now(pytz.timezone('America/Sao_Paulo')).strftime('%Y-%m-%d %H:%M:%S %Z')}")
            check_delays()
            print("Waiting 5 minutes for next check...")
            time.sleep(300)  # 5 minutes
    except KeyboardInterrupt:
        print("Monitoring stopped.")
    except Exception as e:
        logging.error(f"Script failed: {e}")
        print(f"Script failed: {e}")
