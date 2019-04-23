app_config = {
    'CLUSTER_HEALTH_WAIT': 60,
    'DRAIN_WAIT': 60,
    'AUTOSCALER_NAMESPACE': 'kube-system',
    'AUTOSCALER_DEPLOYMENT': 'cluster-autoscaler-aws-cluster-autoscaler',
    'ASG_STATE_TAG': 'eks-rolling-update:desired_capacity',
    'MAX_RETRY': 5,
    'WAIT': 60,
    'DRY_RUN': False
}