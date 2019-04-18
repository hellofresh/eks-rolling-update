# EKS Rolling Update

EKS Rolling Update is a script that will update worker nodes in an EKS cluster in a rolling fashion.
To achieve this, it performs the following actions:

* Pauses Kubernetes Autoscaler
* Finds a list of worker nodes per ASG that do not have a launch config that matches the ASG
* Scales up the ASG with new instances
* Ensures the ASG are healthy and that they have joined the EKS cluster
* Suspends AWS Autoscaling actions
* Drains EKS worker nodes
* Terminates EC2 instances of the worker nodes
* Scales down the ASG to original count
* Resumes AWS Autoscaling actions
* Resumes Kubernetes Autoscaler

## Requirements

* kubectl
* KUBECONFIG environment variable set
* Valid AWS credentials set

## Installation

Install

```
virtualenv -p python3 venv
source venv/bin/activate
pip3 install -r requirements.txt
```

Set KUBECONFIG

```
export KUBECONFIG=~/.kube/config
```

## Usage

```
eks-rolling-update.py [-h] --cluster_name CLUSTER_NAME

Rolling update on cluster

optional arguments:
  -h, --help            show this help message and exit
  --cluster_name CLUSTER_NAME, -c CLUSTER_NAME
                        the cluster name to perform rolling update on
```

Example:

```
eks-rolling-update.py -c platform-ahoy-eks
```

