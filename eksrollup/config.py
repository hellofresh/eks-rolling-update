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
    'K8S_CONTEXT': os.getenv('K8S_CONTEXT', None),
    'K8S_PROXY_BYPASS': str_to_bool(os.getenv('K8S_PROXY_BYPASS', False)),
    'ASG_DESIRED_STATE_TAG': os.getenv('ASG_DESIRED_STATE_TAG', 'eks-rolling-update:desired_capacity'),
    'ASG_ORIG_CAPACITY_TAG': os.getenv('ASG_ORIG_CAPACITY_TAG', 'eks-rolling-update:original_capacity'),
    'ASG_ORIG_MAX_CAPACITY_TAG': os.getenv('ASG_ORIG_MAX_CAPACITY_TAG', 'eks-rolling-update:original_max_capacity'),
    'ASG_USE_TERMINATION_POLICY': str_to_bool(os.getenv('ASG_USE_TERMINATION_POLICY', False)),
    'INSTANCE_WAIT_FOR_STOPPING': str_to_bool(os.getenv('INSTANCE_WAIT_FOR_STOPPING', False)),
    'CLUSTER_HEALTH_WAIT': int(os.getenv('CLUSTER_HEALTH_WAIT', 90)),
    'CLUSTER_HEALTH_RETRY': int(os.getenv('CLUSTER_HEALTH_RETRY', 1)),
    'GLOBAL_MAX_RETRY': int(os.getenv('GLOBAL_MAX_RETRY', 12)),
    'GLOBAL_HEALTH_WAIT': int(os.getenv('GLOBAL_HEALTH_WAIT', 20)),
    'BETWEEN_NODES_WAIT': int(os.getenv('BETWEEN_NODES_WAIT', 0)),
    'RUN_MODE': int(os.getenv('RUN_MODE', 1)),
    'DRY_RUN': str_to_bool(os.getenv('DRY_RUN', False)),
    'EXCLUDE_NODE_LABEL_KEYS': os.getenv('EXCLUDE_NODE_LABEL_KEYS', 'spotinst.io/node-lifecycle').split(),
    'EXTRA_DRAIN_ARGS': os.getenv('EXTRA_DRAIN_ARGS', '').split(),
    'MAX_ALLOWABLE_NODE_AGE': int(os.getenv('MAX_ALLOWABLE_NODE_AGE', 6)),
    'TAINT_NODES': str_to_bool(os.getenv('TAINT_NODES', False)),
    'BATCH_SIZE': int(os.getenv('BATCH_SIZE', 0)),
    'ENFORCED_DRAINING': str_to_bool(os.getenv('ENFORCED_DRAINING', False)),
    'ASG_NAMES': os.getenv('ASG_NAMES', '').split()
}
