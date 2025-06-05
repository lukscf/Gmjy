# Required libraries: selenium, pandas, unidecode, prompt_toolkit
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
from datetime import datetime, timedelta
import time
from unidecode import unidecode  # Library to remove accents
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter

# Function to generate slugs from city names
def create_slug(city_name):
    # Remove accents, convert to lowercase, and replace spaces with underscores
    slug = unidecode(city_name.lower()).replace(" - ", "-").replace(" ", "_")
    return slug

# Load the list of cities from the CSV on GitHub
cities_url = "https://raw.githubusercontent.com/lukscf/Flix/main/brazilian-cities.csv"
print("Loading city list from GitHub...")
cities_df = pd.read_csv(cities_url)

# Build the dictionary of cities
cities = {}
for idx, row in cities_df.iterrows():
    city_name = unidecode(row["city"])  # Remove accents from city name
    city_name_with_uf = f"{city_name} - {row['state']}"
    cities[str(idx + 1)] = {
        "name": city_name_with_uf,
        "slug": create_slug(city_name_with_uf)
    }

# Create a list of city names for reference
city_names = [city["name"] for city in cities.values()]
print(f"Total cities loaded: {len(city_names)}")

# Predefined list of city pairs to process
city_pairs = [
    ("Fortaleza - CE", "Recife - PE"),
    ("Joao Pessoa - PB", "Recife - PE"),
    ("Fortaleza - CE", "Natal - RN"),
    ("Fortaleza - CE", "Joao Pessoa - PB"),
    ("Recife - PE", "Salvador - BA"),
    ("Aracaju - SE", "Salvador - BA"),
    ("Sao Paulo - SP", "Brasilia - DF")
]

# Function to find slugs for a city pair
def get_city_slugs(origin_name, destination_name):
    origin_entry = next((city for city in cities.values() if city["name"].lower() == origin_name.lower()), None)
    destination_entry = next((city for city in cities.values() if city["name"].lower() == destination_name.lower()), None)
    
    if not origin_entry or not destination_entry:
        print(f"Error: One or both cities not found - {origin_name} or {destination_name}")
        return None, None, None, None
    
    return origin_entry["slug"], origin_name, destination_entry["slug"], destination_name

# Function to test city combinations with and without "-all (TODOS EM PORTUGUES)"
def test_city_combinations(driver, origin_slug, destination_slug, departure_date):
    combinations = [
        (f"{origin_slug}-todos", f"{destination_slug}-todos"),
        (f"{origin_slug}-todos", destination_slug),
        (origin_slug, f"{destination_slug}-todos"),
        (origin_slug, destination_slug),
    ]

    for origin_test_slug, destination_test_slug in combinations:
        url = f"https://www.viajeguanabara.com.br/onibus/{origin_test_slug}/{destination_test_slug}?departureDate={departure_date}&passengers=1:1"
        print(f"\nTesting combination: {origin_test_slug} -> {destination_test_slug}")
        print(f"Accessing URL: {url}")
        driver.get(url)

        # Wait up to 60 seconds for the page to load and check for trips
        try:
            WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "app-trip"))
            )
            trips = driver.find_elements(By.CSS_SELECTOR, "app-trip")
            if trips:
                print(f"Combination successful! Found {len(trips)} trips.")
                return origin_test_slug, destination_test_slug
            else:
                print("No trips found for this combination.")
        except Exception as e:
            print(f"Error testing combination: {e}")
            continue

    print("No valid combination found for the provided cities.")
    return None, None

# Function to extract occupancy after clicking
def get_occupancy(trip_id, driver):
    try:
        print(f"Clicking to display occupancy for trip {trip_id}...")
        driver.find_element(By.CSS_SELECTOR, f"#{trip_id} [data-testid='selectTripAction']").click()
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, f"#{trip_id} .vehicle-item"))
        )

        # Extract occupancy
        seats = driver.find_elements(By.CSS_SELECTOR, f"#{trip_id} .vehicle-item")
        total_seats = 0
        occupied_seats = 0
        for seat in seats:
            if "item-empty" not in seat.get_attribute("class"):  # Ignore aisles
                total_seats += 1
                if "item-ecommerce-blocked" in seat.get_attribute("class"):
                    occupied_seats += 1

        available_seats = total_seats - occupied_seats
        load_factor = occupied_seats / total_seats if total_seats > 0 else 0
        print(f"Occupancy for {trip_id}: {available_seats} seats available out of {total_seats} (load factor: {load_factor:.2f})")
        return available_seats, total_seats, load_factor
    except Exception as e:
        print(f"Error collecting occupancy for {trip_id}: {e}")
        return None, None, None
    finally:
        # Close the occupancy section, if open
        try:
            driver.find_element(By.CSS_SELECTOR, f"#{trip_id} .btn-outline").click()
            time.sleep(1)
        except:
            pass

# Function to scrape trip data for a given city pair and date
def scrape_guanabara_trips(origin_slug, origin_name, destination_slug, destination_name, departure_date, driver):
    url = f"https://www.viajeguanabara.com.br/onibus/{origin_slug}/{destination_slug}?departureDate={departure_date}&passengers=1:1"
    print(f"Accessing URL: {url}")
    driver.get(url)

    # Wait up to 60 seconds for the page to load and check for trips
    try:
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "app-trip"))
        )
    except Exception as e:
        print(f"Error loading page: {e}")
        return []

    # Check if the page is blocked (e.g., CAPTCHA)
    if "CAPTCHA" in driver.page_source or "blocked" in driver.page_source.lower():
        print("The page appears to be blocked by CAPTCHA or anti-scraping measures. Manual intervention required.")
        return []

    # Find all trips
    trips = driver.find_elements(By.CSS_SELECTOR, "app-trip")
    if not trips:
        print("No trips found on the page.")
        return []

    print(f"Found {len(trips)} trips on the page.")
    trip_data = []

    for trip in trips:
        try:
            # Extract trip ID
            trip_id = trip.find_element(By.CSS_SELECTOR, "[data-testid^='idTrip']").get_attribute("id")
            print(f"Processing trip {trip_id}...")

            # Extract visible information
            route = trip.find_element(By.CSS_SELECTOR, ".trip-route").text.strip().replace("\n", " -> ")
            trip_class = trip.find_element(By.CSS_SELECTOR, "[data-testid='tripClassNameOutput']").text.strip()
            departure_time = trip.find_element(By.CSS_SELECTOR, "[data-testid='tripDepartureTimeOutput'] .trip-time-number").text.strip()
            arrival_time = trip.find_element(By.CSS_SELECTOR, "[data-testid='triparrivalTimeOutput'] .trip-time-number").text.strip()
            next_day = "+1" in trip.find_element(By.CSS_SELECTOR, "[data-testid='triparrivalTimeOutput']").text
            duration = trip.find_element(By.CSS_SELECTOR, "[data-testid='tripDurationOutput'] .trip-durantion").text.strip()
            price = trip.find_element(By.CSS_SELECTOR, "[data-testid='tripPriceOutput']").text.strip()
            old_price = trip.find_element(By.CSS_SELECTOR, ".old-value").text.strip() if trip.find_elements(By.CSS_SELECTOR, ".old-value") else "N/A"
            boarding_point = trip.find_element(By.CSS_SELECTOR, ".boarding__location").text.strip()
            connections = trip.find_element(By.CSS_SELECTOR, ".details__connections").text.strip() if trip.find_elements(By.CSS_SELECTOR, ".details__connections") else "No"

            # Extract occupancy
            available_seats, total_seats, load_factor = get_occupancy(trip_id, driver)

            # Store data, including origin and destination
            trip_data.append({
                "origin": origin_name,
                "destination": destination_name,
                "route": route,
                "class": trip_class,
                "schedule": f"{departure_time} - {arrival_time}{' (+1)' if next_day else ''}",
                "duration": duration,
                "original_fare": old_price,
                "promotional_fare": price,
                "connection": connections,
                "boarding_point": boarding_point,
                "available_seats": available_seats,
                "total_seats": total_seats,
                "load_factor": load_factor
            })

        except Exception as e:
            print(f"Error processing trip {trip_id}: {e}")
            continue

    return trip_data

# Set up the driver
options = webdriver.ChromeOptions()
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# Set the base date to tomorrow
base_date = datetime.now() + timedelta(days=1)

# Define future days to collect snapshots
days_ahead = [1, 3, 5, 7, 10, 14]
all_data = []

# Iterate over city pairs
for origin_name, destination_name in city_pairs:
    print(f"\n=== Processing City Pair: {origin_name} -> {destination_name} ===")
    
    # Get slugs for the city pair
    origin_slug, origin_name, destination_slug, destination_name = get_city_slugs(origin_name, destination_name)
    
    if not origin_slug or not destination_slug:
        print(f"Skipping city pair {origin_name} -> {destination_name} due to missing slugs.")
        continue

    # Test city combinations with and without "-all"
    print("\n=== Testing City Combinations ===")
    origin_test_slug, destination_test_slug = test_city_combinations(driver, origin_slug, destination_slug, base_date.strftime("%d-%m-%Y"))

    if not origin_test_slug or not destination_test_slug:
        print(f"No valid combination found for {origin_name} -> {destination_name}. Skipping.")
        continue

    # Iterate over future days
    for days in days_ahead:
        target_date = (base_date + timedelta(days=days)).strftime("%d-%m-%Y")
        print(f"\nCollecting data for {target_date}...")
        data = scrape_guanabara_trips(origin_test_slug, origin_name, destination_test_slug, destination_name, target_date, driver)
        for entry in data:
            entry["query_date"] = target_date
        all_data.extend(data)

driver.quit()

# Remove accents from all strings before saving to CSV
for entry in all_data:
    for key, value in entry.items():
        if isinstance(value, str):
            entry[key] = unidecode(value)

# Save to CSV
if all_data:
    df = pd.DataFrame(all_data)
    df.to_csv("guanabara_trips_data.csv", index=False, encoding='utf-8')
    print("\nCollected data:")
    print(df)
else:
    print("\nNo data was collected. Check the logs above to identify the issue.")
