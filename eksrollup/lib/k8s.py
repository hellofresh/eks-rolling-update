from kubernetes import client, config
from kubernetes.client.rest import ApiException
import os
import subprocess
import time
import sys
from .logger import logger
from eksrollup.config import app_config


def ensure_config_loaded():

    kube_config = os.getenv('KUBECONFIG')
    if kube_config and os.path.isfile(kube_config):
        try:
            config.load_kube_config(context=app_config['K8S_CONTEXT'])
        except config.ConfigException:
            raise Exception("Could not configure kubernetes python client")
    else:
        try:
            config.load_incluster_config()
        except config.ConfigException:
            try:
                config.load_kube_config(context=app_config['K8S_CONTEXT'])
            except config.ConfigException:
                raise Exception("Could not configure kubernetes python client")

    proxy_url = os.getenv('HTTPS_PROXY', os.getenv('HTTP_PROXY', None))
    if proxy_url and not app_config['K8S_PROXY_BYPASS']:
        logger.info(f"Setting proxy: {proxy_url}")
        client.Configuration._default.proxy = proxy_url


def get_k8s_nodes(exclude_node_label_keys=app_config["EXCLUDE_NODE_LABEL_KEYS"]):
    """
    Returns a list of kubernetes nodes
    """
    ensure_config_loaded()

    k8s_api = client.CoreV1Api()
    logger.info("Getting k8s nodes...")
    response = k8s_api.list_node()
    if exclude_node_label_keys is not None:
        nodes = []
        for node in response.items:
            if all(key not in node.metadata.labels for key in exclude_node_label_keys):
                nodes.append(node)
        response.items = nodes
    logger.info("Current k8s node count is {}".format(len(response.items)))
    return response.items


def get_node_by_instance_id(k8s_nodes, instance_id):
    """
    Returns a K8S node name given an instance id. Expects the output of
    list_nodes as in input
    """
    node_name = ""
    logger.info('Searching for k8s node name by instance id...')
    for k8s_node in k8s_nodes:
        if instance_id in k8s_node.spec.provider_id:
            logger.info('InstanceId {} is node {} in kubernetes land'.format(instance_id, k8s_node.metadata.name))
            node_name = k8s_node.metadata.name
    if not node_name:
        logger.info("Could not find a k8s node name for that instance id. Exiting")
        raise Exception("Could not find a k8s node name for that instance id. Exiting")
    return node_name


def modify_k8s_autoscaler(action):
    """
    Pauses or resumes the Kubernetes autoscaler
    """

    ensure_config_loaded()

    # Configure API key authorization: BearerToken
    # create an instance of the API class
    k8s_api = client.AppsV1Api()
    if action == 'pause':
        logger.info('Pausing k8s autoscaler...')
        body = {'spec': {'replicas': 0}}
    elif action == 'resume':
        logger.info('Resuming k8s autoscaler...')
        body = {'spec': {'replicas': app_config['K8S_AUTOSCALER_REPLICAS']}}
    else:
        logger.info('Invalid k8s autoscaler option')
        sys.exit(1)
    try:
        k8s_api.patch_namespaced_deployment(
            app_config['K8S_AUTOSCALER_DEPLOYMENT'],
            app_config['K8S_AUTOSCALER_NAMESPACE'],
            body
        )
        logger.info('K8s autoscaler modified to replicas: {}'.format(body['spec']['replicas']))
    except ApiException as e:
        logger.info('Scaling of k8s autoscaler failed. Error code was {}, {}. Exiting.'.format(e.reason, e.body))
        sys.exit(1)


def delete_node(node_name):
    """
    Deletes a kubernetes node from the cluster
    """

    ensure_config_loaded()

    # create an instance of the API class
    k8s_api = client.CoreV1Api()
    logger.info("Deleting k8s node {}...".format(node_name))
    try:
        if not app_config['DRY_RUN']:
            k8s_api.delete_node(node_name)
        else:
            k8s_api.delete_node(node_name, dry_run="true")
        logger.info("Node deleted")
    except ApiException as e:
        logger.info("Exception when calling CoreV1Api->delete_node: {}".format(e))


def cordon_node(node_name):
    """
    Cordon a kubernetes node to avoid new pods being scheduled on it
    """

    ensure_config_loaded()

    # create an instance of the API class
    k8s_api = client.CoreV1Api()
    logger.info("Cordoning k8s node {}...".format(node_name))
    try:
        api_call_body = client.V1Node(spec=client.V1NodeSpec(unschedulable=True))
        if not app_config['DRY_RUN']:
            k8s_api.patch_node(node_name, api_call_body)
        else:
            k8s_api.patch_node(node_name, api_call_body, dry_run=True)
        logger.info("Node cordoned")
    except ApiException as e:
        logger.info("Exception when calling CoreV1Api->patch_node: {}".format(e))


def taint_node(node_name):
    """
    Taint a kubernetes node to avoid new pods being scheduled on it
    """

    ensure_config_loaded()

    k8s_api = client.CoreV1Api()
    logger.info("Adding taint to k8s node {}...".format(node_name))
    try:
        taint = client.V1Taint(effect='NoSchedule', key='eks-rolling-update')
        api_call_body = client.V1Node(spec=client.V1NodeSpec(taints=[taint]))
        if not app_config['DRY_RUN']:
            k8s_api.patch_node(node_name, api_call_body)
        else:
            k8s_api.patch_node(node_name, api_call_body, dry_run=True)
        logger.info("Added taint to the node")
    except ApiException as e:
        logger.info("Exception when calling CoreV1Api->patch_node: {}".format(e))


def drain(node_name):
    """
    Drain pods from the given node
    """
    config.load_kube_config()
    v1 = client.CoreV1Api()
    if app_config['DRY_RUN'] is True:
        logger.info("node/{} drained (dry run)".format(node_name))
        return
    field_selector = 'spec.nodeName='+node_name
    ret = v1.list_pod_for_all_namespaces(watch=False,\
            field_selector=field_selector) 
    pods_to_evict=[]
    for pod in ret.items:
        if not pod.metadata.owner_references:
            logger.info("cannot delete Pods {} which is not managed byReplicationController, ReplicaSet, Job, DaemonSet orStatefulSet".format(pod.metadata.name))
            sys.exit(1)
        for owner_reference in pod.metadata.owner_references:
            if (owner_reference.controller and\
                owner_reference.kind != "DaemonSet"):
                logger.info("evicting pod {}/{}".format(pod.metadata.namespace, pod.metadata.name))
                pods_to_evict.append(pod)
            elif owner_reference.kind == "DaemonSet":
                logger.info("ignoring DaemonSet-managed Pods: {}/{}".format(pod.metadata.namespace, pod.metadata.name))
    while True:
        for pod in pods_to_evict:
            time.sleep(2)
            try:
                body = client.V1beta1Eviction(metadata=client.V1ObjectMeta(\
                    name=pod.metadata.name, namespace=pod.metadata.namespace))
                v1.create_namespaced_pod_eviction(name=pod.metadata.name,\
                    namespace=pod.metadata.namespace, body=body)
                logger.info("pod/{} evicted".format(pod.metadata.name))
            except ApiException as x:
                if x.status == 429:
                    logger.info("Failed to evict pod {}:{}".format(pod.metadata.name, loads(x.body)['details']))
                    continue
            try:
                p = v1.read_namespaced_pod(pod.metadata.name,\
                pod.metadata.namespace)
                #statefulset fall in this category
                if p.metadata.uid != pod.metadata.uid:
                    pods_to_evict.remove(pod)
                    continue
            except ApiException as x:
                #pod is gone, not found
                if x.status == 404:
                    pods_to_evict.remove(pod)
        if not pods_to_evict:
            logger.info("node/{} drained".format(node_name))
            break


def k8s_nodes_ready(max_retry=app_config['GLOBAL_MAX_RETRY'], wait=app_config['GLOBAL_HEALTH_WAIT']):
    """
    Checks that all nodes in a cluster are Ready
    """
    logger.info('Checking k8s nodes health status...')
    retry_count = 1
    healthy_nodes = False
    while retry_count < max_retry:
        # reset healthy nodes after every loop
        healthy_nodes = True
        retry_count += 1
        nodes = get_k8s_nodes()
        for node in nodes:
            conditions = node.status.conditions
            for condition in conditions:
                if condition.type == "Ready" and condition.status == "False":
                    logger.info("Node {} is not healthy - Ready: {}".format(
                        node.metadata.name,
                        condition.status)
                    )
                    healthy_nodes = False
                elif condition.type == "Ready" and condition.status == "True":
                    # condition status is a string
                    logger.info("Node {}: Ready".format(node.metadata.name))
        if healthy_nodes:
            logger.info('All k8s nodes are healthy')
            break
        logger.info('Retrying node health...')
        time.sleep(wait)
    return healthy_nodes


def k8s_nodes_count(desired_node_count, max_retry=app_config['GLOBAL_MAX_RETRY'], wait=app_config['GLOBAL_HEALTH_WAIT']):
    """
    Checks that the number of nodes in k8s cluster matches given desired_node_count
    """
    logger.info('Checking k8s expected nodes are online after asg scaled up...')
    retry_count = 1
    nodes_online = False
    while retry_count < max_retry:
        nodes_online = True
        retry_count += 1
        nodes = get_k8s_nodes()
        logger.info('Current k8s node count is {}'.format(len(nodes)))
        if len(nodes) != desired_node_count:
            nodes_online = False
            logger.info('Waiting for k8s nodes to reach count {}...'.format(desired_node_count))
            time.sleep(wait)
        else:
            logger.info('Reached desired k8s node count of {}'.format(len(nodes)))
            break
    return nodes_online
