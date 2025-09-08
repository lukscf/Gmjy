import pandas as pd
from datetime import datetime, timedelta
import time
from unidecode import unidecode
from seleniumwire import webdriver  # Use selenium-wire para proxies autenticados
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from multiprocessing import Pool

# Lista de proxies do Luna (formatados como http://user:pass@host:port)
proxies = [
    "ADD PROXIES HERE",
]

# Função para formatar nome da cidade para URL (lowercase, sem acentos, hifens, adicionando -sc)
def format_city_name(city, state):
    city_formatted = unidecode(city.lower()).replace(' ', '-')
    return f"{city_formatted}-{state.lower()}"

# Função que cada worker vai executar (processa uma lista de tasks)
def process_tasks(tasks):
    import random  # Import aqui para child process
    import time    # Import aqui para child process
    
    data_local = []  # Lista local para dados desse processo

    for origem, destino, date in tasks:
        # Rotacionar proxy: Escolher um aleatório da lista
        proxy = random.choice(proxies)
        print(f"Usando proxy {proxy} para task {origem} -> {destino} em {date}.")
        
        options = webdriver.ChromeOptions()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        seleniumwire_options = {
            'proxy': {
                'http': proxy, 
                'https': proxy,
                'no_proxy': 'localhost,127.0.0.1'  # Exclui localhost
            }
        }
        try:
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options, seleniumwire_options=seleniumwire_options)
            driver.maximize_window()
        except Exception as e:
            print(f"Erro ao criar driver com proxy {proxy}: {e}. Pulando task.")
            continue

        url = f"https://queropassagem.com.br/onibus/{origem}-para-{destino}?ida={date}"
        
        try:
            driver.get(url)
            time.sleep(1)  # Delay fixo de 1s após carregar URL
            
            # Esperar resultados carregarem
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CLASS_NAME, "cardResultado")))
            
            # Encontrar todos os itens de busca
            items = driver.find_elements(By.CLASS_NAME, "cardResultado")
            
            for idx, item in enumerate(items):
                try:
                    # Extrair dados visíveis (mantido, com defaults)
                    operadora = "N/A"
                    horario = "N/A"
                    duracao = "N/A"
                    classe = "N/A"
                    tarifa_promocional = "N/A"
                    tarifa_original = "N/A"
                    trecho = "N/A"
                    ponto_embarque = "N/A"
                    conexao = "Direto"
                    try:
                        operadora_elem = item.find_element(By.CSS_SELECTOR, ".logo img")
                        operadora = operadora_elem.get_attribute("title") or operadora_elem.get_attribute("alt").replace("Logo da ", "")
                    except:
                        pass
                    try:
                        times = item.find_elements(By.CSS_SELECTOR, ".times p.typo-h5")
                        if len(times) >= 2:
                            horario = f"{times[0].text} - {times[1].text}"
                    except:
                        pass
                    try:
                        duracao_elem = item.find_element(By.CSS_SELECTOR, ".times p.typo-caption")
                        duracao = duracao_elem.text.replace("Duração: ", "").strip()
                    except:
                        pass
                    try:
                        classe = item.find_element(By.CSS_SELECTOR, ".seatClass p.typo-body-2").text
                    except:
                        pass
                    try:
                        tarifa_promocional = item.find_element(By.CSS_SELECTOR, ".price p.typo-h5").text
                    except:
                        pass
                    try:
                        places = item.find_elements(By.CSS_SELECTOR, ".places p.typo-caption")
                        if len(places) >= 2:
                            trecho = f"{places[0].text} -> {places[1].text}"
                            ponto_embarque = places[0].text
                    except:
                        pass
                    
                    # Print estado inicial
                    try:
                        initial_wrapper = item.find_element(By.CLASS_NAME, "busWrapper")
                        print(f"Estado inicial do busWrapper para item {idx}: class='{initial_wrapper.get_attribute('class')}', style='{initial_wrapper.get_attribute('style')}', conteúdo length={len(initial_wrapper.get_attribute('innerHTML'))}.")
                    except:
                        print(f"BusWrapper inicial não encontrado para item {idx}.")
                    
                    # Clique principal no div cardResultado
                    actions = ActionChains(driver)
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)  # Scroll para o div
                    time.sleep(1)  # Delay fixo de 1s antes do clique
                    actions.move_to_element(item).pause(1).perform()  # Move mouse para o div
                    try:
                        actions.click(item).perform()
                        print(f"Clique via ActionChains no div 'cardResultado' sucedido para item {idx}.")
                    except:
                        print(f"ActionChains falhou no div; tentando JS para item {idx}.")
                        driver.execute_script("arguments[0].click();", item)
                    time.sleep(1)  # Delay fixo de 1s após clique
                    
                    # Espera e retry com fallbacks (mantido da versão anterior)
                    max_retries = 5
                    retries = 0
                    map_loaded = False
                    fallback_used = 0  # 0: none, 1: Duração, 2: Logo
                    while retries < max_retries:
                        try:
                            # Espera o botão mudar para "Fechar" ou busLayout aparecer
                            close_button = WebDriverWait(driver, 40).until(lambda d: item.find_element(By.CSS_SELECTOR, "button.secondary"))
                            if "Fechar" in close_button.text.strip():
                                print(f"Botão mudou para 'Fechar' para item {idx}. Div aberta com sucesso.")
                            bus_wrapper = item.find_element(By.CLASS_NAME, "busWrapper")
                            bus_layout = WebDriverWait(driver, 10).until(lambda d: bus_wrapper.find_element(By.CLASS_NAME, "busLayout"))
                            map_loaded = True
                            print(f"BusLayout carregado para item {idx}. Conteúdo length={len(bus_wrapper.get_attribute('innerHTML'))}.")
                            break
                        except:
                            print(f"Tentativa {retries+1} falhou. Estado atual do botão: {item.find_element(By.CSS_SELECTOR, 'button').text if item.find_elements(By.CSS_SELECTOR, 'button') else 'Não encontrado'}.")
                            # Fallbacks sequenciais
                            if fallback_used == 0:
                                # Fallback 1: Clique no "Duração"
                                try:
                                    duracao_elem = item.find_element(By.CSS_SELECTOR, ".times p.typo-caption")
                                    if "Duração" in duracao_elem.text:
                                        print(f"Tentando fallback 1: Clique na palavra 'Duração' para item {idx}.")
                                        actions.move_to_element(duracao_elem).pause(1).click(duracao_elem).perform()
                                        time.sleep(1)  # Delay fixo de 1s após fallback
                                        fallback_used = 1
                                    else:
                                        fallback_used = 1
                                except:
                                    print(f"Fallback 1 ('Duração') falhou para item {idx}.")
                                    fallback_used = 1
                            elif fallback_used == 1:
                                # Fallback 2: Clique no "logo"
                                try:
                                    logo_elem = item.find_element(By.CLASS_NAME, "logo")
                                    print(f"Tentando fallback 2: Clique no 'logo' para item {idx}.")
                                    actions.move_to_element(logo_elem).pause(1).click(logo_elem).perform()
                                    time.sleep(1)  # Delay fixo de 1s após fallback
                                    fallback_used = 2
                                except:
                                    print(f"Fallback 2 ('logo') falhou para item {idx}.")
                                    fallback_used = 2
                            # Tenta re-clicar no div principal
                            try:
                                driver.execute_script("arguments[0].click();", item)
                            except:
                                pass
                            time.sleep(1)  # Delay fixo de 1s nos retries
                            retries += 1
                        
                        if not map_loaded:
                            print(f"Falha ao abrir div e carregar mapa após {max_retries} tentativas (com fallbacks). Usando defaults.")
                            assentos_disponiveis = 0
                            total_assentos = 0
                            load_factor = 0
                        else:
                            # Contar assentos
                            all_seats = bus_layout.find_elements(By.TAG_NAME, "div")
                            print(f"Encontrados {len(all_seats)} divs no busLayout para item {idx}.")
                            occupied_seats = [seat for seat in all_seats if "occupied" in seat.get_attribute("class").lower() or seat.text.strip().upper() == "X"]
                            free_seats = [seat for seat in all_seats if "occupied" not in seat.get_attribute("class").lower() and seat.text.strip().isdigit() and seat.text.strip() != ""]
                            
                            assentos_disponiveis = len(free_seats)
                            total_assentos = len(free_seats) + len(occupied_seats)
                            load_factor = (total_assentos - assentos_disponiveis) / total_assentos if total_assentos > 0 else 0
                            print(f"Assentos disponíveis: {assentos_disponiveis}, Total: {total_assentos}, Load Factor: {load_factor} para item {idx}.")
                        
                        # Fechar o detalhe
                        try:
                            close_button = item.find_element(By.CSS_SELECTOR, "button.secondary")
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", close_button)
                            time.sleep(1)  # Delay fixo de 1s antes de fechar
                            try:
                                actions.click(close_button).perform()
                            except:
                                driver.execute_script("arguments[0].click();", close_button)
                            time.sleep(1)  # Delay fixo de 1s após fechar
                            print(f"Div fechada com sucesso para item {idx}.")
                        except:
                            print(f"Botão 'Fechar' não encontrado para item {idx}. Ignorando.")
                        
                        # Datas
                        data_consulta = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        coletado_dia = datetime.now().strftime('%Y-%m-%d')
                        pbd = "N/A"
                        
                        # Armazenar dados
                        data_local.append({
                            "origem": origem,
                            "destino": destino,
                            "trecho": trecho,
                            "classe": classe,
                            "horario": horario,
                            "duracao": duracao,
                            "tarifa_original": tarifa_original,
                            "tarifa_promocional": tarifa_promocional,
                            "conexao": conexao,
                            "ponto_embarque": ponto_embarque,
                            "assentos_disponiveis": assentos_disponiveis,
                            "total_assentos": total_assentos,
                            "load_factor": load_factor,
                            "data_consulta": data_consulta,
                            "Coletado_dia": coletado_dia,
                            "PBD": pbd,
                            "operadora": operadora
                        })
                    
                except Exception as e:
                    print(f"Erro geral ao processar item {idx} para {origem} -> {destino} em {date}: {e}")
                    continue
            
        except Exception as e:
            print(f"Erro ao carregar URL {url}: {e}")
            continue
        
        driver.quit()  # Fechar driver após task para rotacionar proxy na próxima

    return data_local

if __name__ == '__main__':
    print("Starting main process...")
    # Carregar cidades e dates aqui
    csv_url = "https://raw.githubusercontent.com/lukscf/Gmjy/main/brazilian-cities.csv"
    df_cities = pd.read_csv(csv_url)
    df_sc = df_cities[df_cities['state'] == 'SC'].copy()
    df_sc = df_sc.sort_values(by='inhabitants', ascending=False).head(30)
    df_sc['formatted'] = df_sc.apply(lambda row: format_city_name(row['city'], row['state']), axis=1)
    cities = df_sc['formatted'].tolist()
    
    start_date = datetime.now() + timedelta(days=1)
    dates = [(start_date + timedelta(days=i)).strftime('%d-%m-%Y') for i in range(7)]
    
    # Gerar todos os tasks
    tasks = []
    for origem in cities:
        for destino in cities:
            if origem == destino:
                continue
            for date in dates:
                tasks.append((origem, destino, date))

    # Dividir tasks entre 5 workers
    num_workers = 5
    task_chunks = [tasks[i::num_workers] for i in range(num_workers)]

    # Rodar em paralelo com Pool
    with Pool(num_workers) as pool:
        results = pool.map(process_tasks, task_chunks)

    # Combinar resultados
    all_data = []
    for result in results:
        all_data.extend(result)

    # Salvar em CSV
    current_date = datetime.now().strftime('%d-%m-%y')
    filename = f"queropassagem_data_sc-{current_date}.csv"
    df = pd.DataFrame(all_data)
    df.to_csv(filename, index=False)
    print(f"Dados salvos em {filename}")
