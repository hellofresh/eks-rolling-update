FROM python:3.7.2-alpine3.9

RUN apk add --update --upgrade --no-cache curl bash
# Installing kubectl on the container
RUN curl -o kubectl https://storage.googleapis.com/kubernetes-release/release/$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl && chmod +x ./kubectl && mv ./kubectl /usr/local/bin/kubectl
RUN mkdir /app
WORKDIR /app
COPY requirements.txt .
RUN pip3 install -r requirements.txt
COPY config.py .
COPY eks-rolling-update.py .
