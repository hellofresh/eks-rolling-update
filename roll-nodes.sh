#!/usr/bin/env bash

# This script allows you to roll an EKS cluster manually given a cluster as an input

main(){
  ###
  # Entrypoint of this script
  # Arguments:
  #   $1: The EKS cluster name you want to roll
  #   $2: Region
  #   $3: Run Mode - Look for "Run Mode" in the README.md - Default is 1
  # Returns:
  #   None
  ###

  # Checking that the AWS_PROFILE is set
  [ -z "$AWS_PROFILE" ] && echo "AWS_PROFILE is not set" && exit 1
  CLUSTER=$1
  REGION=$2
  RUN_MODE=${3-1} # Takes the 3rd argument, if it is not set, sets it to the number 1 (not $1)

  if [ $# -eq 2 ] || [ $# -eq 3 ]; then
    docker run --rm -it \
      --entrypoint="/bin/sh" \
      -e AWS_PROFILE=$AWS_PROFILE \
      -e AWS_DEFAULT_REGION=$REGION \
      -e K8S_AUTOSCALER_ENABLED=true \
      -e K8S_AUTOSCALER_NAMESPACE=kube-system \
      -e K8S_AUTOSCALER_DEPLOYMENT=cluster-autoscaler-aws-cluster-autoscaler \
      -e K8S_AUTOSCALER_REPLICAS=1 \
      -e RUN_MODE=$RUN_MODE \
      -v ~/.aws:/root/.aws \
      $(docker build -q .) \
      -c "echo ${RUN_MODE};aws eks update-kubeconfig --name ${CLUSTER}; python eks_rolling_update.py -c ${CLUSTER} --plan"
  else
    echo "Usage: $0 CLUSTER_NAME AWS_REGION RUN_MODE (Optional)"
    exit 1
  fi
}

main "$@"
