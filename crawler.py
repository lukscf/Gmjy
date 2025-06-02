# Lembrar de colocar as bibliotecas necessárias: selenium, panda, unicode, prompt_toolkit.

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
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter

# Função para gerar slugs a partir do nome da cidade
def create_slug(city_name):
    # Remove acentos, converte para minúsculas e substitui espaços por underscores
    slug = unidecode(city_name.lower()).replace(" - ", "-").replace(" ", "_")
    return slug

# Carregar a lista de cidades do arquivo CSV no GitHub
cities_url = "https://raw.githubusercontent.com/lukscf/Flix/main/brazilian-cities.csv"
print("Carregando lista de cidades do GitHub...")
cities_df = pd.read_csv(cities_url)

# Construir o dicionário de cidades
cities = {}
for idx, row in cities_df.iterrows():
    city_name = unidecode(row["city"])  # Remove acentos do nome da cidade
    city_name_with_uf = f"{city_name} - {row['state']}"
    cities[str(idx + 1)] = {
        "name": city_name_with_uf,
        "slug": create_slug(city_name_with_uf)
    }

# Criar uma lista de nomes de cidades para o auto-complete
city_names = [city["name"] for city in cities.values()]
city_completer = WordCompleter(city_names, ignore_case=True)
print(f"Total de cidades carregadas: {len(city_names)}")

# Função para testar combinações de cidades com e sem "-todos"
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

        # Aguardar até 20 segundos para carregar a página e verificar se há viagens
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

# Função para selecionar origem e destino com auto-complete
def select_cities():
    print("\n=== Seletor de Origem e Destino ===")
    print("Digite o nome da cidade e use TAB para auto-completar. Pressione Enter para confirmar.")
    
    session = PromptSession(completer=city_completer)

    # Selecionar origem
    while True:
        origin_name = session.prompt("Digite o nome da cidade de origem: ").strip()
        origin_entry = next((city for city in cities.values() if city["name"].lower() == origin_name.lower()), None)
        if origin_entry:
            origin_base = origin_entry["slug"]
            break
        else:
            print("Cidade nao encontrada! Tente novamente.")

    # Selecionar destino
    while True:
        destination_name = session.prompt("Digite o nome da cidade de destino: ").strip()
        destination_entry = next((city for city in cities.values() if city["name"].lower() == destination_name.lower()), None)
        if destination_entry:
            destination_base = destination_entry["slug"]
            break
        else:
            print("Cidade nao encontrada! Tente novamente.")
    
    return origin_base, origin_name, destination_base, destination_name

# Função para extrair ocupação após clique
def get_occupancy(trip_id, driver):
    try:
        print(f"Clicando para exibir ocupacao da viagem {trip_id}...")
        driver.find_element(By.CSS_SELECTOR, f"#{trip_id} [data-testid='selectTripAction']").click()
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, f"#{trip_id} .vehicle-item"))
        )

        # Extrair ocupação
        seats = driver.find_elements(By.CSS_SELECTOR, f"#{trip_id} .vehicle-item")
        total_seats = 0
        occupied_seats = 0
        for seat in seats:
            if "item-empty" not in seat.get_attribute("class"):  # Ignorar corredores
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
        # Fechar a seção de ocupação, se aberta
        try:
            driver.find_element(By.CSS_SELECTOR, f"#{trip_id} .btn-outline").click()
            time.sleep(1)
        except:
            pass

# Função para coletar dados de todas as viagens
def scrape_guanabara_trips(origin_slug, origin_name, destination_slug, destination_name, departure_date, driver):
    url = f"https://www.viajeguanabara.com.br/onibus/{origin_slug}/{destination_slug}?departureDate={departure_date}&passengers=1:1"
    print(f"Acessando URL: {url}")
    driver.get(url)

    # Aguardar até 20 segundos para carregar a página e verificar se há viagens
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "app-trip"))
        )
    except Exception as e:
        print(f"Erro ao carregar a pagina: {e}")
        return []

    # Verificar se a página foi bloqueada (ex.: CAPTCHA)
    if "CAPTCHA" in driver.page_source or "bloqueado" in driver.page_source.lower():
        print("A pagina parece estar bloqueada por CAPTCHA ou anti-scraping. Intervencao manual necessaria.")
        return []

    # Encontrar todas as viagens
    trips = driver.find_elements(By.CSS_SELECTOR, "app-trip")
    if not trips:
        print("Nenhuma viagem encontrada na pagina.")
        return []

    print(f"Encontradas {len(trips)} viagens na pagina.")
    trip_data = []

    for trip in trips:
        try:
            # Extrair ID da viagem
            trip_id = trip.find_element(By.CSS_SELECTOR, "[data-testid^='idTrip']").get_attribute("id")
            print(f"Processando viagem {trip_id}...")

            # Extrair informações visíveis
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

            # Extrair ocupação
            available_seats, total_seats, load_factor = get_occupancy(trip_id, driver)

            # Armazenar dados, incluindo origem e destino
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
                "load_factor": load_factor
            })

        except Exception as e:
            print(f"Erro ao processar viagem {trip_id}: {e}")
            continue

    return trip_data

# Configurar o driver
options = webdriver.ChromeOptions()
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# Definir a data atual como 02-06-2025
current_date = datetime.strptime("02-06-2025", "%d-%m-%Y")
base_date = current_date  # Usar a data atual diretamente como base_date

# Selecionar cidades com auto-complete
origin_base, origin_name, destination_base, destination_name = select_cities()

# Testar combinações de cidades com e sem "-todos"
print("\n=== Testando Combinacoes de Cidades ===")
origin_slug, destination_slug = test_city_combinations(driver, origin_base, destination_base, base_date.strftime("%d-%m-%Y"))

if not origin_slug or not destination_slug:
    print("Nao foi possivel encontrar uma combinacao valida. Encerrando o script.")
    driver.quit()
    exit()

# Definir os dias futuros para coletar snapshots
days_ahead = [1, 3, 5, 7, 10, 14]
all_data = []

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
