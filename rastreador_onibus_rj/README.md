# Home Assistant Add-on: Rio Bus Tracker (Data.Rio)

![Suporta arquitetura aarch64][aarch64-shield] ![Suporta arquitetura amd64][amd64-shield]

Rastreamento de ônibus em tempo real e cálculo de previsão de chegada para o Rio de Janeiro (SPPO e BRT) diretamente no Home Assistant.

## Sobre

**Rio Bus Tracker** é um complemento personalizado do Home Assistant que se integra à API *Mobilidade.Rio* para trazer dados de transporte público em tempo real para sua casa inteligente.

Ao executar `onibus.py` em segundo plano, este complemento monitora a geolocalização em tempo real de linhas específicas de ônibus no Rio de Janeiro. Ele calcula o progresso de cada ônibus ao longo de sua rota, determina seu sentido e calcula o Tempo Estimado de Chegada (ETA) ao ponto de ônibus configurado próximo à sua casa.

O complemento envia essas atualizações diretamente ao Home Assistant usando MQTT Auto-Discovery, criando entidades de sensores individuais para cada ônibus ativo nas linhas monitoradas.

### Principais funcionalidades
* **Rastreamento em tempo real:** Suporta tanto ônibus convencionais (SPPO) quanto sistemas BRT usando a API unificada Mobilidade.Rio.
* **Cálculo de previsão de chegada (ETA):** Estima os tempos de chegada com base na distância da rota e na velocidade média configurada.
* **Correspondência de rotas:** Usa dados de rotas predefinidos (`rotas_onibus.py` e `mapa_destinos.py`) para identificar com precisão os sentidos dos ônibus e filtrar dados incorretos de GPS.
* **MQTT Auto-Discovery:** Cria e atualiza automaticamente entidades `sensor.onibus_<id>` no Home Assistant com um estado limpo e formatado (por exemplo, "Chega em 5 min • Sentido Centro").
* **Filtragem inteligente:** Ignora sinais de GPS antigos, ônibus estacionados e entradas duplicadas da API para manter sua instância do Home Assistant organizada e com bom desempenho.

## Configuração

Este complemento requer uma configuração básica pela interface do Home Assistant antes de ser iniciado.

### Mapa de opções (`options.json`)

* `linhas_monitoradas` (lista): Uma lista de strings contendo os números das linhas de ônibus que você deseja monitorar (por exemplo, `["554", "309"]`).
* `ponto_onibus_lat` (float): A latitude do ponto de ônibus onde você está esperando.
* `ponto_onibus_lon` (float): A longitude do ponto de ônibus onde você está esperando.
* `velocidade_media_onibus` (float): Velocidade média estimada do ônibus em km/h para calcular o ETA (Padrão: `18.0`).
* `intervalo_de_atualizacao_segundos` (int): Frequência com que o complemento consulta a API Mobilidade.Rio (Padrão: `30`).
* `confirmacoes_necessarias` (int): Número de verificações consecutivas de GPS necessárias para confirmar uma mudança de sentido do ônibus (Padrão: `2`).
* `tempo_retencao_memoria` (int): Por quanto tempo (em segundos) o estado de um ônibus é mantido na memória antes de ser descartado caso ele pare de transmitir (Padrão: `3600`).
* `log_level` (string): Defina como `info`, `warning` ou `debug` para solucionar problemas (Padrão: `warning`).

## Requisitos
* Uma integração **MQTT Broker** ativa no Home Assistant.
* A variável de ambiente `SUPERVISOR_TOKEN` do Home Assistant deve estar acessível (gerenciada automaticamente pelo ambiente do complemento).

## Como funciona (detalhes internos)
O script principal (`onibus.py`) busca dados em `https://its.mobilidade.rio/v1/geolocalizacao/veiculos`. Ele calcula a distância de Haversine e projeções ortogonais para associar o ônibus ao segmento correto da rota. Em seguida, envia um payload JSON formatado para o serviço MQTT interno do Home Assistant usando a API do Supervisor.

---

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
