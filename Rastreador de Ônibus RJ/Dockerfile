FROM python:3.11-alpine

ENV TZ=America/Sao_Paulo
RUN apk add --no-cache tzdata

# Cria a pasta de trabalho do aplicativo
WORKDIR /app

# Copia todos os arquivos da pasta do add-on para dentro do container
COPY . /app/

# Dá permissão de execução para o script
RUN chmod a+x /app/run.sh

CMD [ "/app/run.sh" ]