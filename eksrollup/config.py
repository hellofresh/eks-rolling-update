from dotenv import load_dotenv
from distutils.util import strtobool
import os
load_dotenv('{}/.env'.format(os.getcwd()))


def str_to_bool(val):
    return val if type(val) is bool else bool(strtobool(val))


app_config = {
    'K8S_AUTOSCALER_ENABLED': str_to_bool(os.getenv('K8S_AUTOSCALER_ENABLED', False)),
    'K8S_AUTOSCALER_NAMESPACE': os.getenv('K8S_AUTOSCALER_NAMESPACE', 'default'),
    'K8S_AUTOSCALER_DEPLOYMENT': os.getenv('K8S_AUTOSCALER_DEPLOYMENT', 'cluster-autoscaler'),
    'K8S_AUTOSCALER_REPLICAS': int(os.getenv('K8S_AUTOSCALER_REPLICAS', 2)),
    'ASG_DESIRED_STATE_TAG': 'eks-rolling-update:desired_capacity',
    'ASG_ORIG_CAPACITY_TAG': 'eks-rolling-update:original_capacity',
    'ASG_ORIG_MAX_CAPACITY_TAG': 'eks-rolling-update:original_max_capacity',
    'ASG_WAIT_FOR_DETACHMENT': str_to_bool(os.getenv('ASG_WAIT_FOR_DETACHMENT', True)),
    'ASG_USE_TERMINATION_POLICY': str_to_bool(os.getenv('ASG_USE_TERMINATION_POLICY', False)),
    'CLUSTER_HEALTH_WAIT': int(os.getenv('CLUSTER_HEALTH_WAIT', 90)),
    'GLOBAL_MAX_RETRY': int(os.getenv('GLOBAL_MAX_RETRY', 12)),
    'GLOBAL_HEALTH_WAIT': int(os.getenv('GLOBAL_HEALTH_WAIT', 20)),
    'BETWEEN_NODES_WAIT': int(os.getenv('BETWEEN_NODES_WAIT', 0)),
    'RUN_MODE': int(os.getenv('RUN_MODE', 1)),
    'DRY_RUN': str_to_bool(os.getenv('DRY_RUN', False)),
    'EXCLUDE_NODE_LABEL_KEY': 'spotinst.io/node-lifecycle',
    'EXTRA_DRAIN_ARGS': os.getenv('EXTRA_DRAIN_ARGS', '').split()
}
