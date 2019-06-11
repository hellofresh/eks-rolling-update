FROM python:3.7.2-alpine3.9

RUN apk add --update --upgrade --no-cache curl bash && pip install awscli
ARG AWS_IAM_AUTHENTICATOR_VERSION=1.11.5
RUN curl -o /usr/local/bin/aws-iam-authenticator https://amazon-eks.s3-us-west-2.amazonaws.com/${AWS_IAM_AUTHENTICATOR_VERSION}/2018-12-06/bin/linux/amd64/aws-iam-authenticator; \
    chmod +x /usr/local/bin/aws-iam-authenticator

# Installing kubectl on the container
RUN curl -o kubectl https://storage.googleapis.com/kubernetes-release/release/$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl && chmod +x ./kubectl && mv ./kubectl /usr/local/bin/kubectl
RUN mkdir /app
WORKDIR /app
COPY requirements.txt .
RUN pip3 install -r requirements.txt
COPY lib ./lib
COPY config.py eks_rolling_update.py ./
