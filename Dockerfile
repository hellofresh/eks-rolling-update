FROM python:3-alpine3.10 as builder
ARG VERSION
RUN apk add --no-cache curl make && \
    curl -LO  https://amazon-eks.s3-us-west-2.amazonaws.com/1.14.6/2019-08-22/bin/linux/amd64/aws-iam-authenticator && \
    chmod +x aws-iam-authenticator && \
    curl -LO https://storage.googleapis.com/kubernetes-release/release/$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl && \
    chmod +x kubectl

COPY . .
RUN make dist version=${VERSION}

FROM python:3-alpine3.10

COPY --from=builder /aws-iam-authenticator /kubectl /usr/local/bin/
COPY --from=builder /dist/*.whl /tmp

RUN apk add --no-cache bash
RUN pip3 install --no-cache-dir \
        awscli \
        /tmp/*.whl && \
        rm -rf /tmp/* && \
  AWS_DEFAULT_REGION=us-east-1 eks_rolling_update.py -h

WORKDIR /app
ENTRYPOINT ["eks_rolling_update.py"]
