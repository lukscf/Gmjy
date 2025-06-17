# -*- coding: utf-8 -*-
# Lembrar de colocar as bibliotecas necessarias: selenium, pandas, unidecode, openpyxl
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
from datetime import datetime, timedelta
import time
from unidecode import unidecode

# Funcao para converter preco de texto para float
def convert_price(price_text):
    if price_text == "N/A":
        return None
    if not isinstance(price_text, str):
        print(f"Erro: price_text não é uma string: {price_text}")
        return None
    try:
        # Remove "R$" and strip whitespace
        cleaned_price = price_text.replace("R$", "").strip()
        # Remove thousands separator (period) and replace decimal comma with period
        cleaned_price = cleaned_price.replace(".", "").replace(",", ".")
        return float(cleaned_price)
    except (ValueError, AttributeError) as e:
        print(f"Erro ao converter preco '{price_text}': {e}")
        return None

# Funcao para calcular PBD
def calculate_pbd(departure_date, collect_date):
    try:
        departure = datetime.strptime(departure_date, "%d-%m-%Y")
        collected = datetime.strptime(collect_date, "%d-%m-%Y")
        pbd = (departure - collected).days
        return pbd
    except ValueError as e:
        print(f"Erro ao calcular PBD: {e}")
        return None

# Funcao para decodificar texto com seguranca
def safe_decode(text):
    try:
        return text.encode('utf-8').decode('utf-8')
    except UnicodeDecodeError:
        return text.encode('utf-8').decode('latin1')

# Funcao para gerar slugs a partir do nome da cidade
def create_slug(city_name):
    slug = unidecode(city_name.lower()).replace(" - ", "-").replace(" ", "_")
    return slug

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
def get_city_slugs(origin_name, destination_name):
    # Gerar slugs diretamente dos nomes das cidades
    origin_slug = create_slug(origin_name)
    destination_slug = create_slug(destination_name)
    
    # Verificar se os nomes sao validos
    if not origin_name or not destination_name:
        print(f"Erro: Cidade(s) nao encontrada(s) - Origem: {origin_name}, Destino: {destination_name}")
        return None, None, None, None
    
    return origin_slug, origin_name, destination_slug, destination_name

# Funcao para testar combinacoes de cidades com e sem "-todos"
def test_city_combinations(driver, origin_base, destination_base, departure_date):
    # Priorizar "-todos" para Sao Paulo - SP e Brasilia - DF
    if "sao_paulo-sp" in origin_base and "brasilia-df" in destination_base:
        combinations = [
            (f"{origin_base}-todos", f"{destination_base}-todos"),  # Priorizar esta combinacao
            (f"{origin_base}-todos", destination_base),
            (origin_base, f"{destination_base}-todos"),
            (origin_base, destination_base),
        ]
    else:
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
def scrape_guanabara_trips(origin_slug, origin_name, destination_slug, destination_name, departure_date, driver, collect_date):
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

            route = safe_decode(trip.find_element(By.CSS_SELECTOR, ".trip-route").text.strip().replace("\n", " -> "))
            trip_class = safe_decode(trip.find_element(By.CSS_SELECTOR, "[data-testid='tripClassNameOutput']").text.strip())
            departure_time = safe_decode(trip.find_element(By.CSS_SELECTOR, "[data-testid='tripDepartureTimeOutput'] .trip-time-number").text.strip())
            arrival_time = safe_decode(trip.find_element(By.CSS_SELECTOR, "[data-testid='triparrivalTimeOutput'] .trip-time-number").text.strip())
            next_day = "+1" in safe_decode(trip.find_element(By.CSS_SELECTOR, "[data-testid='triparrivalTimeOutput']").text)
            duration = safe_decode(trip.find_element(By.CSS_SELECTOR, "[data-testid='tripDurationOutput'] .trip-durantion").text.strip())
            price = safe_decode(trip.find_element(By.CSS_SELECTOR, "[data-testid='tripPriceOutput']").text.strip())
            old_price = safe_decode(trip.find_element(By.CSS_SELECTOR, ".old-value").text.strip()) if trip.find_elements(By.CSS_SELECTOR, ".old-value") else "N/A"
            boarding_point = safe_decode(trip.find_element(By.CSS_SELECTOR, ".boarding__location").text.strip())
            connections = safe_decode(trip.find_element(By.CSS_SELECTOR, ".details__connections").text.strip()) if trip.find_elements(By.CSS_SELECTOR, ".details__connections") else "Nao"

            price_float = convert_price(price)
            old_price_float = convert_price(old_price)
            pbd = calculate_pbd(departure_date, collect_date)

            available_seats, total_seats, load_factor = get_occupancy(trip_id, driver)

            trip_data.append({
                "origem": origin_name,
                "destino": destination_name,
                "trecho": route,
                "classe": trip_class,
                "horario": f"{departure_time} - {arrival_time}{' (+1)' if next_day else ''}",
                "duracao": duration,
                "tarifa_original": old_price_float,
                "tarifa_promocional": price_float,
                "conexao": connections,
                "ponto_embarque": boarding_point,
                "assentos_disponiveis": available_seats,
                "total_assentos": total_seats,
                "load_factor": load_factor,
                "data_consulta": departure_date,
                "Coletado_dia": collect_date,
                "PBD": pbd
            })

        except Exception as e:
            print(f"Erro ao processar viagem {trip_id}: {e}")
            continue

    return trip_data

# Configurar o driver
options = webdriver.ChromeOptions()
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124")
options.add_argument("--lang=pt-BR")
options.add_argument("--accept-charset=UTF-8")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# Definir a data base com base na escolha do usuario
while True:
    start_date_choice = input("Digite a data de inicio (Hoje ou Amanha): ").strip().lower()
    if start_date_choice == "hoje":
        base_date = datetime.now()
        print(f"Data base definida como hoje: {base_date.strftime('%d-%m-%Y')}")
        break
    elif start_date_choice == "amanha":
        base_date = datetime.now() + timedelta(days=1)
        print(f"Data base definida como amanha: {base_date.strftime('%d-%m-%Y')}")
        break
    else:
        print("Opcao invalida! Por favor, digite 'Hoje' ou 'Amanha'.")

# Data de coleta
collect_date = datetime.now().strftime("%d-%m-%Y")

# Definir os dias futuros para coletar snapshots
days_ahead = [1, 3, 5, 7, 10, 14]
all_data = []

# Iterar sobre os pares de cidades
for origin_name, destination_name in city_pairs:
    print(f"\n=== Processando par de cidades: {origin_name} -> {destination_name} ===")
    
    # Obter slugs das cidades
    origin_base, origin_name, destination_base, destination_name = get_city_slugs(origin_name, destination_name)
    
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
        data = scrape_guanabara_trips(origin_slug, origin_name, destination_slug, destination_name, target_date, driver, collect_date)
        all_data.extend(data)

driver.quit()

# Remover acentos de todas as strings antes de salvar no XLSX
for entry in all_data:
    for key, value in entry.items():
        if isinstance(value, str):
            entry[key] = unidecode(value)

# Salvar em XLSX
if all_data:
    df = pd.DataFrame(all_data)
    df.to_excel("guanabara_trips_data.xlsx", index=False, engine='openpyxl')
    print("\nDados coletados e salvos em guanabara_trips_data.xlsx:")
    print(df)
else:
    print("\nNenhum dado foi coletado. Verifique os logs acima para identificar o problema.")
