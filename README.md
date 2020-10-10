<p align="center">
  <img height="150px" src="./logo.png"  alt="EKS Rolling Update" title="EKS Rolling Update">
</p>

# EKS Rolling Update

EKS Rolling Update is a utility for updating the launch configuration or template of worker nodes in an EKS cluster.

[![Build Status](https://travis-ci.org/hellofresh/eks-rolling-update.svg?branch=master)](https://travis-ci.org/hellofresh/eks-rolling-update)


- [Intro](#intro)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Contributing](#contributing)
- [License](#license)


<a name="intro"></a>
# Intro

EKS Rolling Update is a utility for updating the launch configuration or template of worker nodes in an EKS cluster. It
updates worker nodes in a rolling fashion and performs health checks of your EKS cluster to ensure no disruption to service.
To achieve this, it performs the following actions:

* Pauses Kubernetes Autoscaler (Optional)
* Finds a list of worker nodes that do not have a launch config or template that matches their ASG
* Scales up the desired capacity
* Ensures the ASGs are healthy and that the new nodes have joined the EKS cluster
* Cordons the outdated worker nodes
* Suspends AWS Autoscaling actions while update is in progress
* Drains outdated EKS outdated worker nodes one by one
* Terminates EC2 instances of the worker nodes one by one
* Detaches EC2 instances from the ASG one by one
* Scales down the ASG to original count (in case of failure)
* Resumes AWS Autoscaling actions
* Resumes Kubernetes Autoscaler (Optional)

<a name="requirements"></a>
## Requirements

* [kubectl](https://kubernetes.io/docs/tasks/tools/install-kubectl/) installed
* `KUBECONFIG` environment variable set, or config available in `${HOME}/.kube/config` per default
* AWS credentials [configured](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/configuration.html#guide-configuration)

### IAM Requirements

The following IAM permissions are required:

```
autoscaling:DescribeAutoScalingGroups
autoscaling:TerminateInstanceInAutoScalingGroup
autoscaling:SuspendProcesses
autoscaling:ResumeProcesses
autoscaling:UpdateAutoScalingGroup
autoscaling:CreateOrUpdateTags
autoscaling:DeleteTags
ec2:DescribeLaunchTemplates
ec2:DescribeInstance
```

<a name="installation"></a>
## Installation

### From PyPi

```
pip3 install eks-rolling-update
```

### From source

```
virtualenv -p python3 venv
source venv/bin/activate
pip3 install -r requirements.txt
```

<a name="usage"></a>
## Usage

```
usage: eks_rolling_update.py [-h] --cluster_name CLUSTER_NAME [--plan]

Rolling update on cluster

optional arguments:
  -h, --help            show this help message and exit
  --cluster_name CLUSTER_NAME, -c CLUSTER_NAME
                        the cluster name to perform rolling update on
  --plan, -p            perform a dry run to see which instances are out of
                        date
```

Example:

```
eks_rolling_update.py -c my-eks-cluster
```

## Configuration

| Environment Variable       | Description                                                                                                           | Default                                  |
|----------------------------|-----------------------------------------------------------------------------------------------------------------------|------------------------------------------|
| K8S_AUTOSCALER_ENABLED     | If True Kubernetes Autoscaler will be paused before running update                                                    | False                                    |
| K8S_AUTOSCALER_NAMESPACE   | Namespace where Kubernetes Autoscaler is deployed                                                                     | "default"                                |
| K8S_AUTOSCALER_DEPLOYMENT  | Deployment name of Kubernetes Autoscaler                                                                              | "cluster-autoscaler"                     |
| K8S_AUTOSCALER_REPLICAS    | Number of replicas to scale back up to after Kubernentes Autoscaler paused                                            | 2                                        |
| ASG_DESIRED_STATE_TAG      | Temporary tag which will be saved to the ASG to store the state of the EKS cluster prior to update                    | eks-rolling-update:desired_capacity      |
| ASG_ORIG_CAPACITY_TAG      | Temporary tag which will be saved to the ASG to store the state of the EKS cluster prior to update                    | eks-rolling-update:original_capacity     |
| ASG_ORIG_MAX_CAPACITY_TAG  | Temporary tag which will be saved to the ASG to store the state of the EKS cluster prior to update                    | eks-rolling-update:original_max_capacity |
| ASG_WAIT_FOR_DETACHMENT    | If True, waits for detachment to fully complete (draining connections etc) after terminating instance and detaching   | True                                     |
| ASG_USE_TERMINATION_POLICY | Use ASG termination policy (instance terminate/detach handled by ASG according to configured termination policy)      | False                                    |
| CLUSTER_HEALTH_WAIT        | Number of seconds to wait after ASG has been scaled up before checking health of the cluster                          | 90                                       |
| CLUSTER_HEALTH_RETRY       | Number of attempts to validate the health of the cluster after ASG has been scaled                                    | 1                                        |
| GLOBAL_MAX_RETRY           | Number of attempts of a health or termination check                                                                   | 12                                       |
| GLOBAL_HEALTH_WAIT         | Number of seconds to wait before retrying a health check                                                              | 20                                       |
| BETWEEN_NODES_WAIT         | Number of seconds to wait after removing a node before continuing on                                                  | 0                                        |
| RUN_MODE                   | See Run Modes section below                                                                                           | 1                                        |
| DRY_RUN                    | If True, only a query will be run to determine which worker nodes are outdated without running an update operation    | False                                    |
| EXCLUDE_NODE_LABEL_KEYS    | List of space-delimited keys for node labels. Nodes with a label using one of these keys will be excluded from the node count when scaling the cluster. | "spotinst.io/node-lifecycle" |
| EXTRA_DRAIN_ARGS           | Additional space-delimited args to supply to the `kubectl drain` function, e.g `--force=true`. See `kubectl drain -h` | ""                                       |
| MAX_ALLOWABLE_NODE_AGE     | The max age each node allowed to be. This works with `RUN_MODE` 4 as node rolling is updating based on age of node    | 6                                        |
| INSTANCE_WAIT_FOR_STOPPING | Wait for terminated instances to be in `stopping` or `shutting-down` state as well as `terminated` or `stopped`       | False                                    |
| BATCH_SIZE                 | Instances to scale the ASG by at a time. When set to 0, batching is disabled.                                         | 0                                        |
| ASG_NAMES                 | List of space-delimited ASG names. Out of ASGs attached to the cluster, only these will be processed for rolling update. If this is left empty all ASGs of the cluster will be processed. | "" |

## Run Modes

There are a number of different values which can be set for the `RUN_MODE` environment variable.

`1` is the default.

| Mode Number   | Description                                                                                     |
|---------------|-------------------------------------------------------------------------------------------------|
| 1             | Scale up and cordon the outdated nodes of each ASG one-by-one, just before we drain them.       |
| 2             | Scale up and cordon the outdated nodes of all ASGs all at once at the beginning of the run.     |
| 3             | Cordon the outdated nodes of all ASGs at the beginning of the run but scale each ASG one-by-one.|
| 4             | Roll EKS nodes based on age instead of launch config (works with `MAX_ALLOWABLE_NODE_AGE` with default 6 days value). |


Each of them have different advantages and disadvantages.
* Scaling up all ASGs at once may cause AWS EC2 instance limits to be exceeded
* Only cordoning the nodes on a per-ASG basis will mean that pods are likely to be moved more than once
* Cordoning the nodes for all ASGs at once could cause issues if new pods needs to start during the process

## Batching

EKS Rolling Update can batch scale-out the ASG to progressively reach the desired instance count before it begins
draining the nodes.

This is intended for use in cases where a large ASG scale-out may result in instances failing to register with
EKS. Such a scenario is more likely to occur with larger ASGs where (for example) a 100 instance ASG may be asked
to scale to 200 (temporarily). Users may find that some instances never register, and this causes EKS Rolling
Update to hang indefinitely waiting for the registered EKS node count to match the instance count.

If this happens, you may want to consider batching.

For example, if the ASG will be scaled from 100 instances to 200 instances, specifying a batch size of 10 will
result in the ASG first scaling to 110, then 120, 130, etc instances until 200 is reached. Once the desired
count is reached, the tool will proceed with the normal draining/scale-in operations.

## Examples

* Plan

```
$ python eks_rolling_update.py --cluster_name YOUR_EKS_CLUSTER_NAME --plan
```

* Apply Changes

```
$ python eks_rolling_update.py --cluster_name YOUR_EKS_CLUSTER_NAME
```

* Cluster Autoscaler

If using `cluster-autoscaler`, you must let `eks-rolling-update` know that cluster-autoscaler is running in your cluster by exporting the following environment variables:

```
$ export  K8S_AUTOSCALER_ENABLED=1 \
          K8S_AUTOSCALER_NAMESPACE="CA_NAMESPACE" \
          K8S_AUTOSCALER_DEPLOYMENT="CA_DEPLOYMENT_NAME"
```

* Disable operations on `cluster-autoscaler`

```
$ unset K8S_AUTOSCALER_ENABLED
```

* Configure tool via `.env` file

Rather than using environment variables, you can use a `.env` file within your working directory to load
updater settings. e.g:

```
$ cat .env
DRY_RUN=1
```

<a name="docker"></a>
## Docker

Although no public Docker image is currently published for this project, feel free to use the included [Dockerfile](Dockerfile) to build your own image.

```bash
make docker-dist version=1.0.DEV
```

After building the image, run using the command
```bash
docker run -ti --rm \
  -e AWS_DEFAULT_REGION \
  -v "${HOME}/.aws:/root/.aws" \
  -v "${HOME}/.kube/config:/root/.kube/config" \
  eks-rolling-update:latest \
  -c my-cluster
```

Pass in any additional environment variables and options as described elsewhere in this file.

<a name="contributing"></a>
## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct, and the process for submitting pull requests to us.

<a name="licence"></a>
## License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details
