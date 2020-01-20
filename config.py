from dotenv import load_dotenv
import os
load_dotenv()

app_config = {
    'K8S_AUTOSCALER_ENABLED': bool(os.getenv('K8S_AUTOSCALER_ENABLED', False)),
    'K8S_AUTOSCALER_NAMESPACE': os.getenv('K8S_AUTOSCALER_NAMESPACE','default'),
    'K8S_AUTOSCALER_DEPLOYMENT': os.getenv('K8S_AUTOSCALER_DEPLOYMENT','cluster-autoscaler'),
    'ASG_DESIRED_STATE_TAG': 'eks-rolling-update:desired_capacity',
    'ASG_ORIG_CAPACITY_TAG': 'eks-rolling-update:original_capacity',
    'ASG_ORIG_MAX_CAPACITY_TAG': 'eks-rolling-update:original_max_capacity',
    'CLUSTER_HEALTH_WAIT': int(os.getenv('CLUSTER_HEALTH_WAIT', 90)),
    'GLOBAL_MAX_RETRY': int(os.getenv('GLOBAL_MAX_RETRY', 12)),
    'GLOBAL_HEALTH_WAIT': int(os.getenv('GLOBAL_HEALTH_WAIT', 20)),
    'BETWEEN_NODES_WAIT': int(os.getenv('BETWEEN_NODES_WAIT', 0)),
    'RUN_MODE': int(os.getenv('RUN_MODE', 1)),
    'DRY_RUN': bool(os.getenv('DRY_RUN', False)),
    'EXCLUDE_NODE_LABEL_KEY': 'spotinst.io/node-lifecycle'
}
