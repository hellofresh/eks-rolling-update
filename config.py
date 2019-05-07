app_config = {
    'CLUSTER_HEALTH_WAIT': 90,
    'AUTOSCALER_NAMESPACE': 'kube-system',
    'AUTOSCALER_DEPLOYMENT': 'cluster-autoscaler-aws-cluster-autoscaler',
    'ASG_DESIRED_STATE_TAG': 'eks-rolling-update:desired_capacity',
    'ASG_ORIG_CAPACITY_TAG': 'eks-rolling-update:original_capacity',
    'MAX_RETRY': 12,
    'WAIT': 20,
    'DRY_RUN': False
}
