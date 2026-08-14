import json
import urllib.request
import math
import os
import sys
import signal
import time
import gzip
import logging
from mapa_destinos import MAPA_DESTINOS
from datetime import datetime, timezone, timedelta
import rotas_onibus


# --- CONFIGURAÇÕES DO SISTEMA ---
TOKEN = os.environ.get('SUPERVISOR_TOKEN')
HA_URL = "http://supervisor/core/api/services/mqtt/publish"
ARQUIVO_MEMORIA = "/dev/shm/memoria_frota.json"
COMPRIMENTOS_ROTAS = {}
PROGRESSO_CASA = {}

# --- LEITURA DAS OPÇÕES DA ABA "CONFIGURAÇÕES" DO ADD-ON ---
ARQUIVO_OPCOES = "/data/options.json"
opcoes_usuario = {}

if os.path.exists(ARQUIVO_OPCOES):
    try:
        with open(ARQUIVO_OPCOES, 'r', encoding='utf-8') as f:
            opcoes_usuario = json.load(f)
    except Exception as e:
        # Como o log ainda não foi configurado, usamos um print de segurança
        print(f"Erro ao ler configurações do Add-on: {e}. Usando valores padrão.")

# --- CONFIGURAÇÃO DINÂMICA DE LOG ---
# Puxa o nível de log escolhido no painel (padrão será 'warning' se não encontrar)
nivel_log_usuario = opcoes_usuario.get('log_level', 'warning').upper()

# Converte o texto da tela para o formato que a biblioteca de logging entende
numeric_level = getattr(logging, nivel_log_usuario, logging.WARNING)

# Aplica a configuração globalmente
logging.basicConfig(level=numeric_level, format='%(asctime)s - %(levelname)s - %(message)s')

# Log de confirmação (só aparece se o nível permitir)
logging.debug(f"DADOS RECEBIDOS DO PAINEL: {opcoes_usuario}")

# Puxa os dados da UI ou usa os valores padrão
LINHAS_MONITORADAS = opcoes_usuario.get('linhas_monitoradas', [])
ponto_onibus_lat = opcoes_usuario.get('ponto_onibus_lat', 0.0)
ponto_onibus_lon = opcoes_usuario.get('ponto_onibus_lon', 0.0)
FATOR_CURVAS = opcoes_usuario.get('fator_curvas', 1.4)
VELOCIDADE_MEDIA_ONIBUS = opcoes_usuario.get('velocidade_media_onibus', 18.0)
CONFIRMACOES_NECESSARIAS = opcoes_usuario.get('confirmacoes_necessarias', 2)
TEMPO_RETENCAO_MEMORIA = opcoes_usuario.get('tempo_retencao_memoria', 3600)
INTERVALO_ATUALIZACAO = opcoes_usuario.get('intervalo_de_atualizacao_segundos', 30)

# --- FUNÇÕES ---

def extrair_numero_linha(linha):
    """Extrai apenas os números da linha, ignorando letras como SP, SN, etc."""
    return "".join(filter(str.isdigit, linha))
    
def formatar_nome_linha(linha_numero):
    """Formata o número da linha com espaços entre dígitos (ex: 554 -> '5 5 4')"""
    return " ".join(linha_numero)

def enviar_mqtt(topic, payload, retain=False):
    """Envia mensagem MQTT via Home Assistant API"""
    if not TOKEN:
        logging.error("Token MQTT não configurado!")
        return False
    
    data = json.dumps({
        "topic": topic, 
        "payload": json.dumps(payload) if isinstance(payload, dict) else payload,
        "retain": retain 
    }).encode('utf-8')
    
    req = urllib.request.Request(HA_URL, data=data)
    req.add_header('Authorization', f'Bearer {TOKEN}')
    req.add_header('Content-Type', 'application/json')

    for tentativa in range(3):
        try:
            response = urllib.request.urlopen(req, timeout=5)
            if response.getcode() == 200:
                return True
        except urllib.error.URLError as e:
            logging.warning(f"Erro MQTT tentativa {tentativa+1}/3: {e}")
            if tentativa < 2:
                time.sleep(2 ** tentativa)
        except Exception as e:
            logging.error(f"Erro inesperado no MQTT: {e}")
            break
    
    return False

def calcular_distancia(lat1, lon1, lat2, lon2):
    """Calcula distância em km entre dois pontos usando fórmula de Haversine"""
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def distancia_xy(lat1, lon1, lat2, lon2):
    """
    Converte latitude/longitude em um plano local (metros).
    Boa aproximação para distâncias pequenas.
    """
    R = 6371000.0

    lat1r = math.radians(lat1)
    lat2r = math.radians(lat2)

    x = math.radians(lon2 - lon1) * R * math.cos((lat1r + lat2r) / 2)
    y = math.radians(lat2 - lat1) * R

    return x, y

def calcular_comprimento_total(rota):
    """Soma a distância de todos os segmentos para obter o tamanho real da rota."""
    comp = 0.0
    for i in range(len(rota) - 1):
        x, y = distancia_xy(rota[i][0], rota[i][1], rota[i+1][0], rota[i+1][1])
        comp += math.hypot(x, y)
    return comp

def progresso_na_rota(lat, lon, rota):
    """
    Retorna:
        progresso (metros desde o início da rota)
        índice do segmento mais próximo
        distância do ônibus até a rota (metros)
    """

    melhor_dist = float("inf")
    melhor_progresso = 0.0
    melhor_segmento = 0

    distancia_acumulada = 0.0

    for i in range(len(rota) - 1):

        lat1, lon1 = rota[i]
        lat2, lon2 = rota[i + 1]

        ax, ay = 0.0, 0.0
        bx, by = distancia_xy(lat1, lon1, lat2, lon2)
        px, py = distancia_xy(lat1, lon1, lat, lon)

        abx = bx - ax
        aby = by - ay

        apx = px - ax
        apy = py - ay

        ab2 = abx * abx + aby * aby

        if ab2 == 0:
            continue

        t = (apx * abx + apy * aby) / ab2

        if t < 0:
            t = 0
        elif t > 1:
            t = 1

        projx = ax + t * abx
        projy = ay + t * aby

        dx = px - projx
        dy = py - projy

        dist = math.hypot(dx, dy)

        comprimento_segmento = math.hypot(abx, aby)

        progresso = distancia_acumulada + t * comprimento_segmento

        if dist < melhor_dist:
            melhor_dist = dist
            melhor_progresso = progresso
            melhor_segmento = i

        distancia_acumulada += comprimento_segmento

    return melhor_progresso, melhor_segmento, melhor_dist

# --- VALIDAÇÃO INICIAL ---
if not TOKEN:
        logging.error("TOKEN não configurado! Por favor, configure o token de longa duração.")
        exit(1)

# --- CARREGA MEMÓRIA ---
memoria = {}
# ... (código que carrega o JSON) ...
    
# --- REGRA DE DESLIGAMENTO SEGURO ---
def desligar_suavemente(sig, frame):
    logging.info("Sinal de parada recebido do Home Assistant. Encerrando o rastreador...")
    sys.exit(0)

# Fica escutando o botão "Parar" (SIGTERM) e o "Ctrl+C" (SIGINT)
signal.signal(signal.SIGINT, desligar_suavemente)
signal.signal(signal.SIGTERM, desligar_suavemente)
# ------------------------------------

AGORA = time.time()

print("▶ STATUS [OK]: Conexão com a Data.Rio estabelecida.", flush=True)

while True:
    AGORA = time.time()
    nova_memoria = {}
          
        # --- CARREGA DADOS ---
    try:
    # --- 1. RASTREAMENTO SPPO (ÔNIBUS NORMAIS) ---
        # Usa o relógio UTC para a URL bater perfeitamente com o servidor da API
        agora_dt = datetime.now(timezone.utc)
        menos_40_dt = agora_dt - timedelta(seconds=40) # Janela de 40 segundos

        # Formata exatamente no padrão exigido pela Mobilidade Rio (YYYY-MM-DD+HH:MM:SS)
        data_final = agora_dt.strftime("%Y-%m-%d+%H:%M:%S")
        data_inicial = menos_40_dt.strftime("%Y-%m-%d+%H:%M:%S")

        # Monta a URL dinâmica para SPPO
        url_sppo = f"https://dados.mobilidade.rio/gps/sppo?dataInicial={data_inicial}&dataFinal={data_final}"
        logging.debug(f"URL SPPO gerada: {url_sppo}")

        req_sppo = urllib.request.Request(url_sppo)
        req_sppo.add_header("Accept-Encoding", "gzip") # Avisa que aceitamos dados compactados

        with urllib.request.urlopen(req_sppo, timeout=15) as response:
            if response.getcode() == 200:
                raw_data = response.read()
                # Se a API enviar compactado, descompacta antes de ler
                if response.info().get('Content-Encoding') == 'gzip':
                    raw_data = gzip.decompress(raw_data)
                    
                dados_sppo = json.loads(raw_data.decode('utf-8'))
                logging.debug(f"Dados SPPO baixados: {len(dados_sppo)} ônibus encontrados")
            else:
                logging.error(f"Erro ao acessar API SPPO da Prefeitura: Código {response.getcode()}")
                time.sleep(30)
                continue

    # --- 2. RASTREAMENTO BRT ---
        # URL fixa para o BRT, sem parâmetros de tempo
        url_brt = "https://dados.mobilidade.rio/gps/brt"
        logging.debug(f"URL BRT gerada: {url_brt}")

        req_brt = urllib.request.Request(url_brt)
        req_brt.add_header("Accept-Encoding", "gzip")

        with urllib.request.urlopen(req_brt, timeout=15) as response:
            if response.getcode() == 200:
                # ESSA LINHA É FUNDAMENTAL: Ela baixa os dados reais da prefeitura
                raw_data = response.read()
                
                # Se vier compactado, descompacta
                if response.info().get('Content-Encoding') == 'gzip':
                    raw_data = gzip.decompress(raw_data)
                    
                # Lê o JSON (note que esta linha fica na mesma direção do IF de cima)
                dados_brt = json.loads(raw_data.decode('utf-8'))
                
                # --- CONTA A QUANTIDADE REAL DE ÔNIBUS BRT ---
                if isinstance(dados_brt, dict):
                    # Se for um dicionário, procura a lista lá dentro
                    for valor in dados_brt.values():
                        if isinstance(valor, list):
                            qtd_brt = len(valor)
                            break
                else:
                    qtd_brt = len(dados_brt)
                    
                logging.debug(f"Dados BRT baixados: {qtd_brt} ônibus encontrados")
            else:
                logging.error(f"Erro ao acessar API do BRT: Código {response.getcode()}")
                time.sleep(30)
                continue

    except Exception as e:
        logging.error(f"Erro ao baixar API: {e}. Tentando novamente em 30s...")
        time.sleep(30)
        continue
    # --- UNIFICAÇÃO DOS DADOS (SPPO + BRT) ---
    dados = []

    # 1. Extrai SPPO
    if 'dados_sppo' in locals():
        if isinstance(dados_sppo, list):
            dados.extend(dados_sppo)
        elif isinstance(dados_sppo, dict):
            # Se for dicionário, extrai a primeira lista que encontrar
            for valor in dados_sppo.values():
                if isinstance(valor, list):
                    dados.extend(valor)
                    break

    # 2. Extrai BRT (resolve o problema do JSON empacotado)
    if 'dados_brt' in locals():
        if isinstance(dados_brt, list):
            dados.extend(dados_brt)
        elif isinstance(dados_brt, dict):
            # Entra no JSON e puxa a lista de veículos não importa o nome da chave
            for valor in dados_brt.values():
                if isinstance(valor, list):
                    dados.extend(valor)
                    break

    logging.debug(f"Total de veículos combinados para processamento: {len(dados)}")
    # --- FILTRO DE DUPLICATAS (NOVA API) ---
    dados_unicos = {}
    for ob in dados:
        o_id = str(ob.get('id_veiculo') or ob.get('ordem') or ob.get('codigo') or '').strip()
        if not o_id:
            continue
            
    # Extrai a hora dessa coordenada para comparar
        if ob.get('datetime'):
            dt_s = str(ob.get('datetime'))[:19].replace('T', ' ')
            try:
                dt_obj = datetime.strptime(dt_s, "%Y-%m-%d %H:%M:%S")
                # Avisa que é UTC e extrai o timestamp correto
                ts = dt_obj.replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                ts = 0
        else:
            ts = int(ob.get('datahora', 0)) / 1000.0
            
        # Se já esbarramos nesse ônibus na lista, verifica qual coordenada é mais nova
        if o_id in dados_unicos:
            if ts <= dados_unicos[o_id]['_ts_temp']:
                continue # A que já guardamos é mais nova, então ignora essa
                
        ob['_ts_temp'] = ts
        dados_unicos[o_id] = ob

    # Substitui a lista suja pela lista limpa com apenas 1 posição por ônibus
    dados = list(dados_unicos.values())
    logging.debug(f"Total de veículos únicos após limpar duplicatas: {len(dados)}")
    # ---------------------------------------

    nova_memoria = {}
        
    # Limpeza memória (remove ônibus antigos)
    for ord_bus, m in memoria.items():
        if AGORA - m.get('ultima_atualizacao', AGORA) < TEMPO_RETENCAO_MEMORIA:
            nova_memoria[ord_bus] = m
        else:
            logging.debug(f"Removendo ônibus {ord_bus} da memória (expirado)")

    # --- PROCESSAMENTO PRINCIPAL ---
    total_processados = 0
    total_ignorados = 0

    for onibus in dados:
        # Tenta pegar 'servico' (nova API). Se vier vazio ou null, tenta 'linha' (BRT antigo).
        linha_raw = onibus.get('servico') or onibus.get('linha') or ''
        linha_original = str(linha_raw).strip()
        
        linha_numeros = extrair_numero_linha(linha_original)

        # --- FILTRO: SÓ RASTREIA SE ESTIVER NA LISTA ---
        if LINHAS_MONITORADAS and (linha_numeros not in LINHAS_MONITORADAS):
            total_ignorados += 1
            continue

        # A API do BRT geralmente envia a direção pronta no campo 'sentido' ou 'trajeto'
        sentido_api = str(onibus.get('sentido', onibus.get('trajeto', ''))).strip()
        
        nome_variavel_rota = f"ROTA_{linha_numeros}"
        tem_rota = hasattr(rotas_onibus, nome_variavel_rota)
        
        # Se não tem rota (SPPO falharia aqui) E não tem sentido da API (BRT falharia aqui), descarta.
        if not tem_rota and not sentido_api:
            total_ignorados += 1
            continue

        linha_identificador = linha_numeros
        
    # A nova API usa 'id_veiculo'. Mantemos 'ordem' e 'codigo' como fallback para o BRT.
        ordem_raw = onibus.get('id_veiculo') or onibus.get('ordem') or onibus.get('codigo') or ''
        ordem = str(ordem_raw).strip()
        
    # 3. Processa coordenadas e Data/Hora real
        try:
            lat = float(str(onibus.get('latitude', '0')).replace(',', '.'))
            lon = float(str(onibus.get('longitude', '0')).replace(',', '.'))
            velocidade = float(onibus.get('velocidade', '0'))
            
            # Lê a chave nova que agora vem em UTC verdadeiro
            if onibus.get('datetime'):
                dt_str = str(onibus.get('datetime'))[:19].replace('T', ' ')
                dt_obj = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                
                # Avisa o Python que a hora é UTC. O .timestamp() converte 
                # automaticamente para o formato universal usado pelo time.time()
                timestamp_gps = dt_obj.replace(tzinfo=timezone.utc).timestamp()
                
            else:
                datahora_ms = int(onibus.get('datahora', time.time() * 1000))
                timestamp_gps = datahora_ms / 1000.0
                
        except (ValueError, TypeError) as e:
            logging.debug(f"Erro ao converter coordenadas do ônibus {ordem}: {e}")
            continue
        
        idade_gps_minutos = (AGORA - timestamp_gps) / 60.0
        if idade_gps_minutos > 10.0:
            logging.debug(f"Ônibus {ordem} ignorado: Sinal de GPS velho ({idade_gps_minutos:.1f} min atrás)")
            continue

        if not ordem or lat == 0.0 or lon == 0.0:
            logging.debug(f"Ônibus {ordem} ignorado: dados incompletos")
            continue

        total_processados += 1
        
    # --- RECUPERA MEMÓRIA DO ÔNIBUS ---
        mem = memoria.get(ordem, {})
        if mem.get('linha') and mem.get('linha') != linha_identificador:
            logging.debug(f"Ônibus {ordem} mudou de linha. Limpando histórico anterior.")
            mem = {}
            
    # --- NOVO: FILTRO DE ÔNIBUS PARADO ---
        lat_mem = mem.get('lat', 0.0)
        lon_mem = mem.get('lon', 0.0)
        tempo_parado_desde = mem.get('tempo_parado_desde', AGORA)

        if lat == lat_mem and lon == lon_mem:
            minutos_parado = (AGORA - tempo_parado_desde) / 60.0
            if minutos_parado > 15.0:
                logging.debug(f"Ônibus {ordem} ignorado: Parado no mesmo lugar há {minutos_parado:.1f} min")
                
                # Salva na memória para não perder o contador, mas pula o envio pro MQTT
                mem['ultima_atualizacao'] = AGORA
                mem['tempo_parado_desde'] = tempo_parado_desde  # <-- ADICIONE APENAS ESTA LINHA AQUI!
                nova_memoria[ordem] = mem
                continue
        else:
            # Ônibus se moveu! Reseta o cronômetro
            tempo_parado_desde = AGORA
            
        # GARANTA QUE ESTAS 4 LINHAS ESTÃO AQUI:
        lat_ancora = mem.get('lat_ancora', lat)
        lon_ancora = mem.get('lon_ancora', lon)
        direcao_texto = mem.get('direcao_texto', 'Calculando...')
        confirmacoes = mem.get('confirmacoes', 0)

    # --- CÁLCULO DE DIREÇÃO (BRT vs SPPO) ---
        if not tem_rota:
            # LÓGICA FALLBACK / BRT: Ignora rotas_onibus.py e usa APENAS MAPA_DESTINOS
            dest_ida, dest_volta = MAPA_DESTINOS.get(linha_identificador, ("Ida", "Volta"))
            
            sentido_lower = sentido_api.lower()
            if "ida" in sentido_lower or sentido_lower == "i":
                direcao_texto = dest_ida
            elif "volta" in sentido_lower or sentido_lower == "v":
                direcao_texto = dest_volta
            else:
                direcao_texto = sentido_api

            progresso_anterior = mem.get("progresso", None)
            segmento_atual = mem.get("segmento", 0)
            dist_rota = mem.get("distancia_rota", 0.0)

            lat_ancora = lat
            lon_ancora = lon
        else:
            # ===== NOVA LÓGICA SPPO (MAP MATCHING) =====
            rota = getattr(rotas_onibus, nome_variavel_rota)

            # Calcula o ponto da rota mais próximo da casa (faz isso só 1x por linha)
            if ponto_onibus_lat != 0 and linha_identificador not in PROGRESSO_CASA:
                prog_casa, _, _ = progresso_na_rota(ponto_onibus_lat, ponto_onibus_lon, rota)
                PROGRESSO_CASA[linha_identificador] = prog_casa

            try:
                progresso_atual, segmento_atual, dist_rota = progresso_na_rota(
                    lat, lon, rota
                )
            except Exception as e:
                logging.error(f"Erro calculando progresso da rota para ônibus {ordem}: {e}")
                continue

            progresso_anterior = mem.get("progresso", None)

            dest_ida, dest_volta = MAPA_DESTINOS.get(
                linha_identificador, ("Ida", "Volta")
            )

            # AQUI ENTRA A ETAPA 4: Aproveitamos o sentido que a nova API envia
            if sentido_api:
                sentido_lower = sentido_api.lower()
                if "ida" in sentido_lower or sentido_lower == "i":
                    direcao_texto = dest_ida
                elif "volta" in sentido_lower or sentido_lower == "v":
                    direcao_texto = dest_volta
                else:
                    direcao_texto = sentido_api
            else:
                # Fallback antigo: Se a API parar de mandar sentido, tenta adivinhar pelo movimento
                LIMIAR_METROS = 20
                if progresso_anterior is None:
                    progresso_anterior = progresso_atual

                delta = progresso_atual - progresso_anterior
                
                if linha_identificador not in COMPRIMENTOS_ROTAS:
                    COMPRIMENTOS_ROTAS[linha_identificador] = calcular_comprimento_total(rota)

                COMPRIMENTO_ROTA = COMPRIMENTOS_ROTAS[linha_identificador]

                if abs(delta) > COMPRIMENTO_ROTA * 0.7:
                    delta = 0

                if abs(delta) >= LIMIAR_METROS:
                    direcao_medida = dest_ida if delta > 0 else dest_volta

                    if direcao_texto == "Calculando...":
                        direcao_texto = direcao_medida
                        confirmacoes = 0
                    elif direcao_medida != direcao_texto:
                        confirmacoes += 1
                        if confirmacoes >= CONFIRMACOES_NECESSARIAS:
                            direcao_texto = direcao_medida
                            confirmacoes = 0
                    else:
                        confirmacoes = 0

            # Atualiza memória
            progresso_anterior = progresso_atual
            lat_ancora = lat
            lon_ancora = lon
            
        # Calcula distância reta agora para usar no fallback e salvar
        dist_reta_atual = calcular_distancia(lat, lon, ponto_onibus_lat, ponto_onibus_lon) if ponto_onibus_lat != 0 else 0

        # --- SALVA NA NOVA MEMÓRIA ---
        nova_memoria[ordem] = {
            'linha': linha_identificador,
            'lat': lat,
            'lon': lon,
            'lat_ancora': lat_ancora,
            'lon_ancora': lon_ancora,
            'direcao_texto': direcao_texto,
            'confirmacoes': confirmacoes,
            'progresso': progresso_anterior,
            'segmento': segmento_atual,
            'distancia_rota': round(dist_rota, 1),
            'dist_casa': dist_reta_atual,
            'tempo_parado_desde': tempo_parado_desde,
            'ultima_atualizacao': AGORA
        }

    # --- CALCULA TEMPO ATÉ CASA ---
        if ponto_onibus_lat == 0 or ponto_onibus_lon == 0:
            dist_real = "unknown"
            tempo = "unknown"
        else:
            esta_aproximando = False
            
    # 1. Se tem rota (SPPO), usa seu cálculo super preciso de progresso
            if tem_rota:
                progresso_casa = PROGRESSO_CASA.get(linha_identificador, 0)
                
                # A distância real pela rota (em km) é a diferença absoluta
                dist_real = abs(progresso_casa - progresso_atual) / 1000.0 
                
                # Verifica a direção: O ônibus está indo para a casa?
                if direcao_texto == dest_ida and progresso_atual < progresso_casa:
                    # Ida: Progresso aumenta. Se for menor que a casa, ainda vai chegar nela.
                    esta_aproximando = True
                elif direcao_texto == dest_volta and progresso_atual > progresso_casa:
                    # Volta: Progresso diminui. Se for maior que a casa, está voltando para ela.
                    esta_aproximando = True
                    
            # 2. Se for BRT (ou se falhar a rota), usa o fallback de distância reta
            else:
                dist_real = dist_reta_atual * FATOR_CURVAS
                
                # Puxa a distância do ciclo anterior. Se a nova for menor, está chegando.
                dist_anterior = mem.get('dist_casa', dist_reta_atual + 0.1)
                esta_aproximando = dist_reta_atual < (dist_anterior + 0.05) # 50m de tolerância

            # 3. Processa o tempo final
            if esta_aproximando:
                if VELOCIDADE_MEDIA_ONIBUS > 0:
                    tempo_bruto = (dist_real / VELOCIDADE_MEDIA_ONIBUS) * 60
                    idade_minutos = max(0, (AGORA - timestamp_gps) / 60.0)
                    tempo = max(1, round(tempo_bruto - idade_minutos))
                else:
                    tempo = "unknown"
                    logging.warning("VELOCIDADE_MEDIA_ONIBUS é zero, tempo não calculado")
            else:
                # Se já passou ou está indo pro outro lado, ignora
                tempo = "unknown"
                dist_real = "unknown"
            

    # --- FORMATA O NOME DA LINHA COM ESPAÇOS ---
        nome_linha_formatado = formatar_nome_linha(linha_identificador)

    # --- CRIA O TEXTO DE EXIBIÇÃO AQUI NO PYTHON ---
        if tempo == "unknown":
            texto_exibicao = f"Sentido {direcao_texto}"
        else:
            texto_exibicao = f"Chega em {tempo} min • Sentido {direcao_texto}"
        
    # --- ENVIA CONFIGURAÇÃO DO SENSOR (COM RETAIN) ---
        linha_memoria = mem.get('linha') # Puxa a linha antiga salva na memória
        
        # Se for um ônibus novo OU se ele mudou de linha, atualiza o config no HA
        if ordem not in memoria or linha_memoria != linha_identificador:
            sensor_name = nome_linha_formatado
            sensor_unique_id = f"onibus_{ordem.lower()}"
            
            # Agora o Home Assistant é "burro": ele só pega o texto que o Python já mastigou
            template_exibicao = "{{ value_json.texto_exibicao }}"
            
            enviar_mqtt(f"homeassistant/sensor/{sensor_unique_id}/config", {
                "name": sensor_name,
                "unique_id": sensor_unique_id,
                "state_topic": f"frota/onibus/{ordem}/state",
                "value_template": template_exibicao,
                "json_attributes_topic": f"frota/onibus/{ordem}/state",
                "icon": "mdi:bus",
                "expire_after": 600
            }, retain=True)
            
    # --- ENVIA ESTADO ATUAL ---
        estado = {
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "velocidade": velocidade,
            "ordem": ordem,
            "destino": direcao_texto,
            "distancia_km": round(dist_real, 1) if dist_real != "unknown" else "unknown",
            "tempo_minutos": tempo,
            "texto_exibicao": texto_exibicao # <-- Enviando a string pronta pro HA
        }
        
        enviar_mqtt(f"frota/onibus/{ordem}/state", estado)

        if dist_real == "unknown":
                logging.debug(f"Ônibus {ordem} (linha {nome_linha_formatado}) processado: {direcao_texto}")
        else:
                logging.debug(f"Ônibus {ordem} (linha {nome_linha_formatado}) processado: {direcao_texto}, {dist_real:.1f}km, {tempo}min")
                
    # --- SALVA MEMÓRIA (COM SEGURANÇA) ---

    memoria = nova_memoria
    try:
        tmp = ARQUIVO_MEMORIA + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(nova_memoria, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ARQUIVO_MEMORIA)
        logging.debug(f"Memória salva: {len(nova_memoria)} ônibus ativos")
    except Exception as e:
        logging.error(f"Erro salvando memória: {e}")

    # Atualiza a referência da memória para o próximo ciclo
    # --- RESUMO FINAL ---
    logging.debug(f"Processamento concluído: {total_processados} ônibus processados, {total_ignorados} ignorados")
    time.sleep(INTERVALO_ATUALIZACAO)
