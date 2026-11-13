# Home Assistant Add-on: Rio Bus Tracker (Data.Rio)

![Supports aarch64 Architecture][aarch64-shield] ![Supports amd64 Architecture][amd64-shield]

Real-time bus tracking and ETA calculation for Rio de Janeiro (SPPO and BRT) directly in Home Assistant.

## About

**Rio Bus Tracker** is a custom Home Assistant add-on that integrates with the *Mobilidade.Rio* API to bring real-time public transportation data into your smart home. 

By running `onibus.py` in the background, this add-on monitors the live geolocation of specific bus lines in Rio de Janeiro. It calculates the progress of each bus along its route, determines its direction, and calculates the Estimated Time of Arrival (ETA) to your configured home bus stop.

The add-on seamlessly pushes these updates to Home Assistant using MQTT Auto-Discovery, creating individual sensor entities for every active bus on your monitored lines.

### Key Features
* **Live Tracking:** Supports both regular buses (SPPO) and BRT systems using the unified Mobilidade.Rio API.
* **ETA Calculation:** Estimates arrival times based on route distance and configured average speed.
* **Map Matching:** Uses predefined route data (`rotas_onibus.py` and `mapa_destinos.py`) to accurately pinpoint bus directions and filter out bad GPS data.
* **MQTT Auto-Discovery:** Automatically creates and updates `sensor.onibus_<id>` entities in Home Assistant with a clean, formatted state (e.g., "Chega em 5 min • Sentido Centro").
* **Smart Filtering:** Ignores old GPS signals, parked buses, and duplicate API entries to keep your Home Assistant instance clean and performant.

## Configuration

This add-on requires basic configuration through the Home Assistant UI before starting. 

### Options Map (`options.json`)

* `linhas_monitoradas` (list): A list of strings containing the bus line numbers you want to track (e.g., `["554", "309"]`).
* `ponto_onibus_lat` (float): The latitude of the bus stop you are waiting at.
* `ponto_onibus_lon` (float): The longitude of the bus stop you are waiting at.
* `velocidade_media_onibus` (float): Estimated average speed of the bus in km/h to calculate the ETA (Default: `18.0`).
* `intervalo_de_atualizacao_segundos` (int): How often the add-on polls the Mobilidade.Rio API (Default: `30`).
* `confirmacoes_necessarias` (int): Number of consecutive GPS checks required to confirm a bus's direction change (Default: `2`).
* `tempo_retencao_memoria` (int): How long (in seconds) to remember a bus's state before dropping it if it stops broadcasting (Default: `3600`).
* `log_level` (string): Set to `info`, `warning`, or `debug` for troubleshooting (Default: `warning`).

## Requirements
* An active **MQTT Broker** integration in Home Assistant.
* The Home Assistant `SUPERVISOR_TOKEN` environment variable must be accessible (handled automatically by the Add-on environment).

## How it works (Under the Hood)
The core script (`onibus.py`) fetches data from `https://its.mobilidade.rio/v1/geolocalizacao/veiculos`. It calculates the Haversine distance and orthogonal projections to map the bus to its correct segment on the route. It then pushes a formatted JSON payload to the internal Home Assistant MQTT service using the Supervisor API.

---

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
