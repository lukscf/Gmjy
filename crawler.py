# Lembrar de colocar as bibliotecas necessarias: selenium, pandas, unidecode
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
from datetime import datetime, timedelta
import time
from unidecode import unidecode  # Biblioteca para remover acentos

# Funcao para gerar slugs a partir do nome da cidade
def create_slug(city_name):
    slug = unidecode(city_name.lower()).replace(" - ", "-").replace(" ", "_")
    return slug

# Carregar a lista de cidades do arquivo CSV no GitHub
cities_url = "https://raw.githubusercontent.com/lukscf/Flix/main/brazilian-cities.csv"
print("Carregando lista de cidades do GitHub...")
cities_df = pd.read_csv(cities_url)

# Construir o dicionario de cidades
cities = {}
for idx, row in cities_df.iterrows():
    city_name = unidecode(row["city"])  # Remove acentos do nome da cidade
    city_name_with_uf = f"{city_name} - {row['state']}"
    cities[str(idx + 1)] = {
        "name": city_name_with_uf,
        "slug": create_slug(city_name_with_uf)
    }

# Lista de pares de cidades a processar
city_pairs = [
    ("Fortaleza - CE", "Recife - PE"),
    ("Joao Pessoa - PB", "Recife - PE"),
    ("Fortaleza - CE", "Natal - RN"),
    ("Fortaleza - CE", "Joao Pessoa - PB"),
    ("Recife - PE", "Salvador - BA"),
    ("Aracaju - SE", "Salvador - BA"),
    ("Sao Paulo - SP", "Brasilia - DF")
]

# Funcao para obter slugs das cidades a partir dos nomes
def get_city_slugs(origin_name, destination_name, cities):
    origin_entry = next((city for city in cities.values() if city["name"].lower() == origin_name.lower()), None)
    destination_entry = next((city for city in cities.values() if city["name"].lower() == destination_name.lower()), None)
    
    if not origin_entry or not destination_entry:
        print(f"Erro: Cidade(s) nao encontrada(s) - Origem: {origin_name}, Destino: {destination_name}")
        return None, None, None, None
    
    return origin_entry["slug"], origin_name, destination_entry["slug"], destination_name

# Funcao para testar combinacoes de cidades com e sem "-todos"
def test_city_combinations(driver, origin_base, destination_base, departure_date):
    combinations = [
        (f"{origin_base}-todos", f"{destination_base}-todos"),
        (f"{origin_base}-todos", destination_base),
        (origin_base, f"{destination_base}-todos"),
        (origin_base, destination_base),
    ]

    for origin_slug, destination_slug in combinations:
        url = f"https://www.viajeguanabara.com.br/onibus/{origin_slug}/{destination_slug}?departureDate={departure_date}&passengers=1:1"
        print(f"\nTestando combinacao: {origin_slug} -> {destination_slug}")
        print(f"Acessando URL: {url}")
        driver.get(url)

        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "app-trip"))
            )
            trips = driver.find_elements(By.CSS_SELECTOR, "app-trip")
            if trips:
                print(f"Combinacao bem-sucedida! Encontradas {len(trips)} viagens.")
                return origin_slug, destination_slug
            else:
                print("Nenhuma viagem encontrada para esta combinacao.")
        except Exception as e:
            print(f"Erro ao testar combinacao: {e}")
            continue

    print("Nenhuma combinacao valida encontrada para as cidades fornecidas.")
    return None, None

# Funcao para extrair ocupacao apos clique
def get_occupancy(trip_id, driver):
    try:
        print(f"Clicando para exibir ocupacao da viagem {trip_id}...")
        driver.find_element(By.CSS_SELECTOR, f"#{trip_id} [data-testid='selectTripAction']").click()
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, f"#{trip_id} .vehicle-item"))
        )

        seats = driver.find_elements(By.CSS_SELECTOR, f"#{trip_id} .vehicle-item")
        total_seats = 0
        occupied_seats = 0
        for seat in seats:
            if "item-empty" not in seat.get_attribute("class"):
                total_seats += 1
                if "item-ecommerce-blocked" in seat.get_attribute("class"):
                    occupied_seats += 1

        available_seats = total_seats - occupied_seats
        load_factor = occupied_seats / total_seats if total_seats > 0 else 0
        print(f"Ocupacao para {trip_id}: {available_seats} assentos disponiveis de {total_seats} (load factor: {load_factor:.2f})")
        return available_seats, total_seats, load_factor
    except Exception as e:
        print(f"Erro ao coletar ocupacao para {trip_id}: {e}")
        return None, None, None
    finally:
        try:
            driver.find_element(By.CSS_SELECTOR, f"#{trip_id} .btn-outline").click()
            time.sleep(1)
        except:
            pass

# Funcao para coletar dados de todas as viagens
def scrape_guanabara_trips(origin_slug, origin_name, destination_slug, destination_name, departure_date, driver):
    url = f"https://www.viajeguanabara.com.br/onibus/{origin_slug}/{destination_slug}?departureDate={departure_date}&passengers=1:1"
    print(f"Acessando URL: {url}")
    driver.get(url)

    try:
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "app-trip"))
        )
    except Exception as e:
        print(f"Erro ao carregar a pagina: {e}")
        return []

    if "CAPTCHA" in driver.page_source or "bloqueado" in driver.page_source.lower():
        print("A pagina parece estar bloqueada por CAPTCHA ou anti-scraping. Intervencao manual necessaria.")
        return []

    trips = driver.find_elements(By.CSS_SELECTOR, "app-trip")
    if not trips:
        print("Nenhuma viagem encontrada na pagina.")
        return []

    print(f"Encontradas {len(trips)} viagens na pagina.")
    trip_data = []

    for trip in trips:
        try:
            trip_id = trip.find_element(By.CSS_SELECTOR, "[data-testid^='idTrip']").get_attribute("id")
            print(f"Processando viagem {trip_id}...")

            route = trip.find_element(By.CSS_SELECTOR, ".trip-route").text.strip().replace("\n", " -> ")
            trip_class = trip.find_element(By.CSS_SELECTOR, "[data-testid='tripClassNameOutput']").text.strip()
            departure_time = trip.find_element(By.CSS_SELECTOR, "[data-testid='tripDepartureTimeOutput'] .trip-time-number").text.strip()
            arrival_time = trip.find_element(By.CSS_SELECTOR, "[data-testid='triparrivalTimeOutput'] .trip-time-number").text.strip()
            next_day = "+1" in trip.find_element(By.CSS_SELECTOR, "[data-testid='triparrivalTimeOutput']").text
            duration = trip.find_element(By.CSS_SELECTOR, "[data-testid='tripDurationOutput'] .trip-durantion").text.strip()
            price = trip.find_element(By.CSS_SELECTOR, "[data-testid='tripPriceOutput']").text.strip()
            old_price = trip.find_element(By.CSS_SELECTOR, ".old-value").text.strip() if trip.find_elements(By.CSS_SELECTOR, ".old-value") else "N/A"
            boarding_point = trip.find_element(By.CSS_SELECTOR, ".boarding__location").text.strip()
            connections = trip.find_element(By.CSS_SELECTOR, ".details__connections").text.strip() if trip.find_elements(By.CSS_SELECTOR, ".details__connections") else "Nao"

            available_seats, total_seats, load_factor = get_occupancy(trip_id, driver)

            trip_data.append({
                "origem": origin_name,
                "destino": destination_name,
                "trecho": route,
                "classe": trip_class,
                "horario": f"{departure_time} - {arrival_time}{' (+1)' if next_day else ''}",
                "duracao": duration,
                "tarifa_original": old_price,
                "tarifa_promocional": price,
                "conexao": connections,
                "ponto_embarque": boarding_point,
                "assentos_disponiveis": available_seats,
                "total_assentos": total_seats,
                "load_factor": load_factor,
                'Coletado_dia': datetime.now()
        })

        except Exception as e:
            print(f"Erro ao processar viagem {trip_id}: {e}")
            continue

    return trip_data

# Configurar o driver
options = webdriver.ChromeOptions()
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# Definir a data base com base na escolha do usuario
while True:
    start_date_choice = input("Digite a data de inicio (Hoje ou Amanha): ").strip().lower()
    if start_date_choice == "hoje":
        base_date = datetime.now()
        print(f"Data base definida como hoje: {base_date.strftime('%d-%m-%Y')}")
        break
    elif start_date_choice == "amanha" or start_date_choice == "amanha":
        base_date = datetime.now() + timedelta(days=1)
        print(f"Data base definida como amanha: {base_date.strftime('%d-%m-%Y')}")
        break
    else:
        print("Opcao invalida! Por favor, digite 'Hoje' ou 'Amanha'.")

# Definir os dias futuros para coletar snapshots
days_ahead = [1, 3, 5, 7, 10, 14]
all_data = []

# Iterar sobre os pares de cidades
for origin_name, destination_name in city_pairs:
    print(f"\n=== Processando par de cidades: {origin_name} -> {destination_name} ===")
    
    # Obter slugs das cidades
    origin_base, origin_name, destination_base, destination_name = get_city_slugs(origin_name, destination_name, cities)
    
    if not origin_base or not destination_base:
        print(f"Pulando par {origin_name} -> {destination_name} devido a erro nas cidades.")
        continue

    # Testar combinacoes de cidades com e sem "-todos"
    print("\n=== Testando Combinacoes de Cidades ===")
    origin_slug, destination_slug = test_city_combinations(driver, origin_base, destination_base, base_date.strftime("%d-%m-%Y"))

    if not origin_slug or not destination_slug:
        print(f"Nao foi possivel encontrar uma combinacao valida para {origin_name} -> {destination_name}. Pulando.")
        continue

    # Iterar sobre os dias futuros
    for days in days_ahead:
        target_date = (base_date + timedelta(days=days)).strftime("%d-%m-%Y")
        print(f"\nColetando dados para {target_date}...")
        data = scrape_guanabara_trips(origin_slug, origin_name, destination_slug, destination_name, target_date, driver)
        for entry in data:
            entry["data_consulta"] = target_date
        all_data.extend(data)

driver.quit()

# Remover acentos de todas as strings antes de salvar no CSV
for entry in all_data:
    for key, value in entry.items():
        if isinstance(value, str):
            entry[key] = unidecode(value)

# Salvar em CSV
if all_data:
    df = pd.DataFrame(all_data)
    df.to_csv("guanabara_trips_data.csv", index=False, encoding='utf-8')
    print("\nDados coletados:")
    print(df)
else:
    print("\nNenhum dado foi coletado. Verifique os logs acima para identificar o problema.")
