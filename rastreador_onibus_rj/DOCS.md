# Home Assistant App: Rastreador de Ônibus do Rio de Janeiro

Este app (anteriormente chamado de *add-on*) permite acompanhar ônibus convencionais (SPPO) e BRT do Rio de Janeiro no Home Assistant. Ele consulta dados de geolocalização, identifica o sentido dos veículos e estima o tempo de chegada a um ponto de referência.

Os resultados são publicados por MQTT e os sensores são criados automaticamente usando **MQTT Discovery**.

## Instalação

Siga estas etapas para instalar o app no Home Assistant:

1. Em **Configurações > Apps**, abra a loja de aplicativos.
2. Caso o projeto esteja em um repositório personalizado, adicione o endereço desse repositório à loja.
3. Localize **Rastreador de Ônibus** e selecione **Instalar**.
4. Aguarde a instalação e abra a aba **Configuração**.

> **Importante:** estas etapas pressupõem que o projeto já foi empacotado e publicado como um app do Home Assistant. O arquivo `onibus.py`, sozinho, não é instalável. A execução também depende dos módulos `mapa_destinos.py` e `rotas_onibus.py` e dos arquivos de empacotamento do app.

## Como usar

1. Instale e configure um broker MQTT, como o **Mosquitto**, e a integração **MQTT** no Home Assistant.
2. Confirme que a descoberta automática (**MQTT Discovery**) está habilitada com o prefixo padrão `homeassistant`.
3. Na aba **Configuração** do app, informe as linhas que deseja monitorar e as coordenadas do seu ponto de ônibus.
4. Ajuste, se necessário, a velocidade média, o intervalo de atualização e os demais parâmetros.
5. Salve as opções e **inicie** o app.
6. Acesse a aba **Log** para verificar a inicialização e eventuais erros.
7. Vá até **Configurações > Dispositivos e serviços > MQTT** ou **Ferramentas de desenvolvedor > Estados** para encontrar os sensores dos veículos.

Os sensores são criados à medida que veículos válidos são encontrados na API. Portanto, eles podem não aparecer imediatamente, especialmente quando nenhuma das linhas monitoradas possui registros válidos.

## Configuração do app

As opções são fornecidas pela aba **Configuração** e lidas pelo programa em `/data/options.json` na inicialização.

Exemplo de configuração:

```yaml
linhas_monitoradas:
  - "810"
  - "554"
  - "613"
ponto_onibus_lat: -22.9000
ponto_onibus_lon: -43.2000
velocidade_media_onibus: 18.0
confirmacoes_necessarias: 2
tempo_retencao_memoria: 3600
intervalo_de_atualizacao_segundos: 30
log_level: info
```

> As coordenadas do exemplo são **ilustrativas**. Substitua-as pela localização do ponto que deseja monitorar. Os nomes e valores padrão descritos abaixo foram verificados no `onibus.py`. A obrigatoriedade de cada campo na interface depende do `config.yaml` do app, que não foi disponibilizado para análise.

### Opção: `linhas_monitoradas`

Lista dos números das linhas que serão monitoradas. Os números devem ser informados como **texto**, por exemplo, `"810"` e `"554"`.

- **Padrão no código:** `[]` (lista vazia).
- Quando a lista está vazia, o script não filtra por número de linha; os demais critérios de validação continuam sendo aplicados.
- Para linhas SPPO sem sentido informado pela API, é necessária uma geometria correspondente em `rotas_onibus.py`.

### Opção: `ponto_onibus_lat`

Latitude do ponto de ônibus utilizado como referência para as estimativas de chegada.

- **Padrão no código:** `0.0`.
- Deve ser informada em graus decimais, como `-22.9000`.

### Opção: `ponto_onibus_lon`

Longitude do ponto de ônibus utilizado como referência para as estimativas de chegada.

- **Padrão no código:** `0.0`.
- Deve ser informada em graus decimais, como `-43.2000`.

Se qualquer uma das coordenadas estiver definida como `0`, o script não calcula a previsão de chegada e retorna `unknown` para o tempo e a distância.

### Opção: `velocidade_media_onibus`

Velocidade média utilizada para estimar o tempo até o ponto de referência.

- **Padrão no código:** `18.0`.
- **Unidade:** quilômetros por hora (km/h).
- Deve ser maior que zero para produzir uma previsão numérica.

Essa velocidade é uma referência configurável, **não** a velocidade instantânea recebida do GPS. A estimativa não considera diretamente trânsito, semáforos, paradas ou horários oficiais.

### Opção: `confirmacoes_necessarias`

Quantidade de confirmações de movimento necessária para mudar o sentido calculado de um veículo quando a API não informa esse dado.

- **Padrão no código:** `2`.
- O recurso é aplicado à lógica de inferência de sentido baseada no percurso registrado em `rotas_onibus.py`.

### Opção: `tempo_retencao_memoria`

Tempo de retenção do histórico de um veículo na memória do rastreador.

- **Padrão no código:** `3600`.
- **Unidade:** segundos (3600 segundos = 1 hora).

O histórico permite comparar posições entre ciclos e acompanhar alterações no sentido. Não é o mesmo que o tempo de expiração dos sensores MQTT.

### Opção: `intervalo_de_atualizacao_segundos`

Tempo de espera entre o término de um ciclo de processamento e o começo do próximo.

- **Padrão no código:** `30`.
- **Unidade:** segundos.

As próprias consultas à API e as publicações MQTT também levam tempo. Portanto, um valor de `30` **não garante** que o estado de cada sensor seja atualizado exatamente a cada 30 segundos.

### Opção: `log_level`

Define a quantidade de informações mostradas no log do app.

- **Padrão no código:** `warning`.
- **Valores reconhecidos:** `debug`, `info`, `warning`, `error` e `critical`.
- Use `info` para acompanhar o funcionamento habitual e `debug` para investigar problemas.

O nível `debug` pode expor nos logs opções configuradas e detalhes do processamento. Utilize-o somente quando necessário.

## Configuração do Home Assistant

### MQTT

O app precisa de um broker MQTT e da integração MQTT configurada no Home Assistant. Ele **não se conecta diretamente ao broker**: as publicações são encaminhadas pela API do Home Assistant, utilizando o serviço `mqtt.publish`.

O ambiente de execução precisa disponibilizar o `SUPERVISOR_TOKEN` e permitir acesso à API interna. No manifesto `config.yaml` do app, a opção relevante é:

```yaml
homeassistant_api: true
```

> Esse trecho é apenas uma configuração necessária à integração com a API, **não** um manifesto completo. Não é necessário inserir manualmente um token de acesso pessoal no script.

### Sensores criados automaticamente

O app cria **um sensor para cada veículo**, e não um sensor único por linha. O nome de cada sensor é o número da linha com os dígitos separados por espaços, por exemplo, `8 1 0`.

Exemplo ilustrativo de um veículo identificado como `A12345`:

**Tópico MQTT Discovery:**

```text
homeassistant/sensor/onibus_a12345/config
```

**Tópico de estado:**

```text
frota/onibus/A12345/state
```

**Exemplo de estado exibido:**

```text
Chega em 8 min • Sentido Destino da ida
```

Quando não é possível calcular o tempo até o ponto:

```text
Sentido Destino da volta
```

**Atributos disponíveis:**

| Atributo | Descrição |
| --- | --- |
| `latitude` | Latitude atual do veículo. |
| `longitude` | Longitude atual do veículo. |
| `velocidade` | Velocidade informada pela API. |
| `ordem` | Identificador do veículo. |
| `destino` | Sentido ou destino identificado. |
| `distancia_km` | Distância estimada até o ponto, em quilômetros, ou `unknown`. |
| `tempo_minutos` | Tempo estimado de chegada, em minutos, ou `unknown`. |
| `texto_exibicao` | Texto exibido como estado principal do sensor. |

O código atual **não publica o número da linha como um atributo `linha`**. O número aparece no nome cadastrado via MQTT Discovery. O `entity_id` final é definido pelo Home Assistant e pode variar.

O app define `expire_after: 600` no MQTT Discovery. Assim, um sensor fica **indisponível após 10 minutos sem nova publicação de estado**; isso não o exclui automaticamente do registro de entidades.

### Exemplo de cartão para o painel

Depois de descobrir o `entity_id` real em **Ferramentas de desenvolvedor > Estados**, você pode adicionar um cartão de entidades ao seu painel:

```yaml
type: entities
title: Ônibus monitorado
entities:
  - entity: sensor.exemplo_onibus
    name: Próximo ônibus
```

Substitua `sensor.exemplo_onibus` pelo identificador real da entidade criada no seu Home Assistant.

### Exemplo de automação de chegada

A automação abaixo envia uma notificação quando o tempo estimado de um veículo passa para menos de 6 minutos:

```yaml
alias: Avisar quando o ônibus estiver chegando
triggers:
  - trigger: numeric_state
    entity_id: sensor.exemplo_onibus
    attribute: tempo_minutos
    below: 6
    above: 0
actions:
  - action: notify.mobile_app_meu_celular
    data:
      title: Ônibus chegando
      message: "{{ states('sensor.exemplo_onibus') }}"
mode: single
```

Substitua o sensor e o serviço de notificação pelos existentes na sua instalação. O gatilho ocorre na passagem para a faixa configurada, não a cada atualização enquanto o valor permanecer nela.

## Funcionamento

A cada ciclo, o app consulta a [API centralizada de geolocalização da mobilidade do Rio de Janeiro](https://its.mobilidade.rio/v1/geolocalizacao/veiculos), considerando o minuto UTC atual e o anterior, tanto para SPPO quanto para BRT.

Antes de publicar os dados, o programa:

1. Elimina registros duplicados, mantendo a posição mais recente de cada veículo.
2. Filtra as linhas configuradas e descarta registros incompletos ou com GPS mais antigo que 10 minutos.
3. Deixa de publicar veículos cujas coordenadas permanecem exatamente iguais por mais de 15 minutos.
4. Identifica o sentido pela API ou, quando necessário, pelo deslocamento registrado na rota.
5. Estima a distância e o tempo até o ponto configurado e publica o resultado via MQTT.

Para linhas com geometria definida em `rotas_onibus.py`, o sistema calcula o progresso ao longo do trajeto. Quando não há geometria, mas a API fornece o sentido, o código utiliza uma estimativa baseada na distância em linha reta multiplicada por um fator de curvas fixo de `1.4`.

A previsão é **aproximada** e não representa um horário oficial de chegada.

## Solução de problemas

### O app não inicia

- Confira a aba **Log**.
- Verifique se os arquivos `mapa_destinos.py` e `rotas_onibus.py` estão presentes no pacote.
- Confira os tipos e os valores informados na aba **Configuração**.
- Se o log indicar ausência de token, revise o acesso do app à API do Home Assistant.

### Os sensores não aparecem

- Confirme que o broker MQTT e a integração MQTT estão funcionando.
- Verifique se o MQTT Discovery usa o prefixo `homeassistant`.
- Confira se a API está retornando veículos das linhas monitoradas.
- Utilize `log_level: debug` temporariamente para investigar registros descartados.
- Lembre-se de que sensores são criados por veículo, conforme os dados recebidos.

### O sensor aparece como `unavailable`

O sensor pode não ter recebido atualização durante 600 segundos. Isso pode acontecer quando o veículo sai da área de monitoramento, perde atualizações de GPS, permanece com as mesmas coordenadas por mais de 15 minutos ou deixa de aparecer na API.

### O sensor mostra apenas `Sentido ...`

Nesse caso, o tempo estimado está `unknown`. Confira se as coordenadas do ponto estão corretas, se a velocidade média é maior que zero e se o veículo está realmente se aproximando do ponto no sentido calculado.

### Erros na API ou no MQTT

Confira a conectividade com a API externa e a disponibilidade da integração MQTT. O programa realiza tentativas de publicação MQTT e, em caso de falha na consulta à API, aguarda antes de tentar novamente.

## Observações importantes

- O programa grava dados temporários da frota em `/dev/shm/memoria_frota.json`, mas a versão examinada **não recupera o arquivo ao iniciar**; após reiniciar o app, o histórico começa vazio.
- A configuração MQTT Discovery é publicada com retenção (`retain: true`), mas os estados dos veículos não são retidos.
- O app não cria por conta própria mapas, painéis, sensores agregados por linha nem notificações; os exemplos apresentados são configurações opcionais do Home Assistant.
- Alterações feitas nas opções exigem a **reinicialização do app**, pois são lidas na inicialização do script.

## Suporte

Em caso de problemas, consulte primeiro a aba **Log** do app e a [documentação da integração MQTT](https://www.home-assistant.io/integrations/mqtt/).

Outras fontes úteis:

- [Documentação de aplicativos do Home Assistant](https://developers.home-assistant.io/docs/apps/)
- [Comunidade do Home Assistant](https://community.home-assistant.io/)
- [Discord do Home Assistant](https://www.home-assistant.io/join-chat)

Para relatar um problema específico deste projeto, utilize a seção **Issues** do repositório GitHub em que o código foi publicado, caso esteja disponível.

## Licença

Este projeto foi desenvolvido para fins pessoais e educacionais. **Todos os direitos reservados ao autor.** A utilização, modificação ou distribuição do código-fonte por terceiros requer autorização prévia.
