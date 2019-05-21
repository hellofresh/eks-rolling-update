from dotenv import load_dotenv
import os
load_dotenv()

app_config = {
    'AUTOSCALER_NAMESPACE': os.getenv('AUTOSCALER_NAMESPACE'),
    'AUTOSCALER_DEPLOYMENT': os.getenv('AUTOSCALER_DEPLOYMENT'),
    'ASG_DESIRED_STATE_TAG': 'eks-rolling-update:desired_capacity',
    'ASG_ORIG_CAPACITY_TAG': 'eks-rolling-update:original_capacity',
    'CLUSTER_HEALTH_WAIT': os.getenv('CLUSTER_HEALTH_WAIT', 90),
    'GLOBAL_MAX_RETRY': os.getenv('GLOBAL_MAX_RETRY', 12),
    'GLOBAL_HEALTH_WAIT': os.getenv('GLOBAL_HEALTH_WAIT', 20),
    'DRY_RUN': os.getenv('DRY_RUN', True)
}
