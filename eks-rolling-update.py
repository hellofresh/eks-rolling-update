import logging
import boto3
import subprocess
import requests
import argparse
import time
import shutil
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from config import app_config


logging.basicConfig(
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)


class RollingUpdateException(Exception):
    def __init__(self, message, asg_name):
        self.message = message
        self.asg_name = asg_name


def get_k8s_nodes():
    config.load_kube_config()
    k8s_api = client.CoreV1Api()
    logging.info("Getting k8s nodes...")
    response = k8s_api.list_node()
    logging.info("Current k8s node count is {}".format(len(response.items)))
    return response.items


def get_node_by_instance_id(k8s_nodes, instance_id):
    """
    Returns a K8S node name given an instance id. Expects the output of
    list_nodes as in input
    """
    node_name = ""
    logging.info('Searching for k8s node name by instance id...')
    for k8s_node in k8s_nodes:
        if instance_id in k8s_node.spec.provider_id:
            logging.info('InstanceId {} is node {} in kuberentes land'.format(instance_id, k8s_node.metadata.name))
            node_name = k8s_node.metadata.name
    if not node_name:
        logging.info("Could not find a k8s node name for that instance id. Exiting")
        raise Exception("Could not find a k8s node name for that instance id. Exiting")
    return node_name


def get_asgs(cluster_tag):
    logging.info('Describing autoscaling groups...')
    client = boto3.client('autoscaling')
    paginator = client.get_paginator('describe_auto_scaling_groups')
    page_iterator = paginator.paginate(
        PaginationConfig={'PageSize': 100}
    )
    asg_query = "AutoScalingGroups[] | [?contains(Tags[?Key==`kubernetes.io/cluster/{}`].Value, `owned`)]".format(cluster_tag)
    # filter for only asgs with kube cluster tags
    filtered_asgs = page_iterator.search(asg_query)
    return filtered_asgs


def modify_k8s_autoscaler(action):
    import kubernetes.client
    config.load_kube_config()
    k8s_api = client.CoreV1Api()
    # Configure API key authorization: BearerToken
    configuration = kubernetes.client.Configuration()
    # create an instance of the API class
    k8s_api = kubernetes.client.AppsV1Api(kubernetes.client.ApiClient(configuration))
    if action == 'pause':
        logging.info('Pausing k8s autoscaler...')
        body = {'spec': {'replicas': 0}}
    elif action == 'resume':
        logging.info('Resuming k8s autoscaler...')
        body = {'spec': {'replicas': 2}}
    else:
        logging.info('Invalid k8s autoscaler option')
        quit()
    try:
        k8s_api.patch_namespaced_deployment(
            app_config['AUTOSCALER_DEPLOYMENT'],
            app_config['AUTOSCALER_NAMESPACE'],
            body
        )
        logging.info('K8s autoscaler modified to replicas: {}'.format(body['spec']['replicas']))
    except ApiException as e:
        logging.info('Scaling of k8s autoscaler failed. Error code was {}, {}. Exiting.'.format(e.reason, e.body))
        quit()

def delete_node(node_name):
    """
    Deletes a kubernetes node from the cluster
    """
    import kubernetes.client
    config.load_kube_config()
    k8s_api = client.CoreV1Api()
    # Configure API key authorization: BearerToken
    configuration = kubernetes.client.Configuration()
    # create an instance of the API class
    k8s_api = kubernetes.client.CoreV1Api(kubernetes.client.ApiClient(configuration))
    logging.info("Deleting k8s node {}...".format(node_name))
    try:
        if not app_config['DRY_RUN']:
            api_response = k8s_api.delete_node(node_name)
        else:
            api_response = k8s_api.delete_node(node_name, dry_run="true")
        logging.info("Node deleted")
    except ApiException as e:
        logging.info("Exception when calling CoreV1Api->delete_node: {}".format(e))


def drain_node(node_name):
    """
    Executes kubectl commands to drain the node. We are not using the api
    because the draining functionality is done client side and to
    replicate the same functionality here would be too time consuming
    """
    logging.info('Draining worker node {}...'.format(node_name))
    if app_config['DRY_RUN']:
        result = subprocess.run([
            'kubectl', 'drain', node_name,
            '--ignore-daemonsets',
            '--delete-local-data',
            '--dry-run'
            ]
        )
    else:
        result = subprocess.run([
            'kubectl', 'drain', node_name,
            '--ignore-daemonsets',
            '--delete-local-data'
            ]
        )
    # If returncode is non-zero, raise a CalledProcessError.
    if result.returncode != 0:
        raise Exception("Node not drained properly. Exiting")


def terminate_instance(instance_id):
    logging.info('Terminating ec2 instance {}...'.format(instance_id))
    client = boto3.client('ec2')
    try:
        response = client.terminate_instances(
            InstanceIds=[instance_id],
            DryRun=app_config['DRY_RUN']
        )
        if response['ResponseMetadata']['HTTPStatusCode'] == requests.codes.ok:
            logging.info('Termination of instance succeeded.')
        else:
            logging.info('Termination of instance failed. Response code was {}. Exiting.'.format(response['ResponseMetadata']['HTTPStatusCode']))
            raise Exception('Termination of instance failed. Response code was {}. Exiting.'.format(response['ResponseMetadata']['HTTPStatusCode']))

    except client.exceptions.ClientError as e:
        if 'DryRunOperation' not in str(e):
            raise


def is_asg_healthy(asg_name, max_retry=app_config['MAX_RETRY'], wait=app_config['WAIT']):
    retry_count = 1
    client = boto3.client('autoscaling')
    while retry_count < max_retry:
        asg_healthy = True
        retry_count += 1
        logging.info('Checking asg {} instance health...'.format(asg_name))
        response = client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[asg_name], MaxRecords=1
        )
        instances = response['AutoScalingGroups'][0]['Instances']
        for instance in instances:
            logging.info('Instance {} - {}'.format(
                instance['InstanceId'],
                instance['HealthStatus']
            ))
            if instance['HealthStatus'] != 'Healthy':
                asg_healthy = False
        if asg_healthy:
            break
        time.sleep(wait)
    else:
        logging.info('asg {} - Healthy.'.format(asg_name))
    return asg_healthy


def is_asg_scaled(asg_name, desired_capacity):
    is_scaled = False
    client = boto3.client('autoscaling')
    logging.info('Checking asg {} instance count...'.format(asg_name))
    response = client.describe_auto_scaling_groups(
        AutoScalingGroupNames=[asg_name], MaxRecords=1
    )
    actual_instances = response['AutoScalingGroups'][0]['Instances']
    if len(actual_instances) != desired_capacity:
        logging.info('Asg {} does not have enough running instances to proceed'.format(asg_name))
        logging.info('Actual instances: {} Desired instances: {}'.format(
            len(actual_instances),
            desired_capacity)
        )
        is_scaled = False
    else:
        logging.info('Asg {} scaled OK'.format(asg_name))
        logging.info('Actual instances: {} Desired instances: {}'.format(
            len(actual_instances),
            desired_capacity)
        )
        is_scaled = True
    return is_scaled


def modify_aws_autoscaling(asg_name, action):
    """
    Suspends or resumes ASG autoscaling
    """
    client = boto3.client('autoscaling')
    logging.info('Modifying asg {} autoscaling to {} ...'.format(
        asg_name,
        action)
    )
    if not app_config['DRY_RUN']:

        if action == "suspend":
            response = client.suspend_processes(
                AutoScalingGroupName=asg_name,
                ScalingProcesses=['Launch', 'ReplaceUnhealthy'])
        elif action == "resume":
            response = client.resume_processes(
                AutoScalingGroupName=asg_name,
                ScalingProcesses=['Launch', 'ReplaceUnhealthy'])
        else:
            logging.info('Invalid scaling option')

        if response['ResponseMetadata']['HTTPStatusCode'] != requests.codes.ok:
            logging.info('AWS asg modification operation did not succeed. Exiting.')
            raise Exception('AWS asg modification operation did not succeed. Exiting.')
    else:
        logging.info('Skipping asg modification due to dry run flag set')
        response = {'message': 'dry run only'}

    return response


def scale_asg(asg_name, current_desired_capacity, new_desired_capacity, new_max_size):
    """
    Changes the desired capacity of an asg
    """
    logging.info('Setting asg desired capacity from {} to {} and max size to {}...'.format(
        current_desired_capacity,
        new_desired_capacity,
        new_max_size
        )
    )
    client = boto3.client('autoscaling')
    if not app_config['DRY_RUN']:
        response = client.update_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            DesiredCapacity=new_desired_capacity,
            MaxSize=new_max_size)
        if response['ResponseMetadata']['HTTPStatusCode'] != requests.codes.ok:
            logging.info('AWS scale up operation did not succeed. Exiting.')
            raise Exception('AWS scale up operation did not succeed. Exiting.')
    else:
        logging.info('Skipping asg scaling due to dry run flag set')
        response = {'message': 'dry run only'}


def save_asg_tags(asg_name, key, value):
    """
    Adds a tag to asg for later retrieval
    """
    logging.info('Saving tag to asg key: {}, value : {}...'.format(key, value))
    client = boto3.client('autoscaling')
    if not app_config['DRY_RUN']:
        response = client.create_or_update_tags(
            Tags=[
                {
                    'Key': key,
                    'Value': str(value),
                    'ResourceId': asg_name,
                    'ResourceType': 'auto-scaling-group',
                    'PropagateAtLaunch': False
                },
            ]
        )
        if response['ResponseMetadata']['HTTPStatusCode'] != requests.codes.ok:
            logging.info('AWS asg tag modification operation did not succeed. Exiting.')
            raise Exception('AWS asg tag modification operation did not succeed. Exiting.')
    else:
        logging.info('Skipping asg tag modification due to dry run flag set')
        response = {'message': 'dry run only'}


def delete_asg_tags(asg_name, key):
    """
    Deletes a tag from asg
    """
    logging.info('Deleting tag from asg key: {}...'.format(key))
    client = boto3.client('autoscaling')
    if not app_config['DRY_RUN']:
        response = client.delete_tags(
            Tags=[
                {
                    'Key': key,
                    'ResourceId': asg_name,
                    'ResourceType': 'auto-scaling-group'
                },
            ]
        )
        if response['ResponseMetadata']['HTTPStatusCode'] != requests.codes.ok:
            logging.info('AWS asg tag modification operation did not succeed. Exiting.')
            raise Exception('AWS asg tag modification operation did not succeed. Exiting.')
    else:
        logging.info('Skipping asg tag modification due to dry run flag set')
        response = {'message': 'dry run only'}


def instance_outdated(instance_obj, asg_lc_name):
    # only one launch config is kept so on some instances it may not actually exist. Making the launch config empty
    lc_name = instance_obj.get('LaunchConfigurationName')
    instance_id = instance_obj['InstanceId']
    if lc_name != asg_lc_name:
        logging.info("Instance id {} launch config of '{}' does not match asg launch config of '{}'".format(
                instance_id,
                lc_name,
                asg_lc_name)
            )
        return True
    else:
        logging.info("Instance id {} : OK ".format(instance_id))
        return False


def instance_terminated(instance_id, max_retry=app_config['MAX_RETRY'], wait=app_config['WAIT']):
    client = boto3.client('ec2')
    retry_count = 1
    while retry_count < max_retry:
        is_instance_terminated = True
        logging.info('Checking instance {} is terminated...'.format(instance_id))
        retry_count += 1
        response = client.describe_instances(
            InstanceIds=[instance_id]
        )
        state = response['Reservations'][0]['Instances'][0]['State']
        stop_states = ['terminated', 'stopped']
        if state['Name'] not in stop_states:
            is_instance_terminated = False
            logging.info('Instance {} is still running, checking again...'.format(instance_id))
        else:
            logging.info('Instance {} terminiated!'.format(instance_id))
            is_instance_terminated = True
            break
        time.sleep(wait)
    return is_instance_terminated


def k8s_nodes_ready(max_retry=app_config['MAX_RETRY'], wait=app_config['WAIT']):
    logging.info('Checking k8s nodes health status...')
    retry_count = 1
    while retry_count < max_retry:
        # reset healthy nodes after every loop
        healthy_nodes = True
        retry_count += 1
        nodes = get_k8s_nodes()
        for node in nodes:
            conditions = node.status.conditions
            for condition in conditions:
                if condition.type == "Ready" and condition.status == "False":
                    logging.info("Node {} is not healthy - Ready: {}".format(
                        node.metadata.name,
                        condition.status)
                    )
                    healthy_nodes = False
                elif condition.type == "Ready" and condition.status == "True":
                    # condition status is a string
                    logging.info("Node {}: Ready".format(node.metadata.name))
        if healthy_nodes:
            logging.info('All k8s nodes are healthy')
            break
        logging.info('Retrying node health...')
        time.sleep(wait)
    return healthy_nodes


def k8s_nodes_count(desired_node_count,
                    max_retry=app_config['MAX_RETRY'], wait=app_config['WAIT']):
    logging.info('Checking k8s expected nodes are online after asg scaled up...')
    retry_count = 1
    while retry_count < max_retry:
        nodes_online = True
        retry_count += 1
        nodes = get_k8s_nodes()
        logging.info('Current k8s node count is {}'.format(len(nodes)))
        if len(nodes) != desired_node_count:
            nodes_online = False
            logging.info('Waiting for k8s nodes to reach count {}...'.format(desired_node_count))
            time.sleep(wait)
        else:
            logging.info('Reached desired k8s node count of {}'.format(len(nodes)))
            break
    return nodes_online


def validate_cluster_health(
        asg_name,
        new_desired_asg_capacity,
        desired_k8s_node_count):
    cluster_healthy = False
    # check if asg has enough nodes first before checking instance health
    if is_asg_scaled(asg_name, new_desired_asg_capacity):
        # if asg is healthy start draining and terminating instances
        if is_asg_healthy(asg_name):
            # check if k8s nodes are all online
            if k8s_nodes_count(desired_k8s_node_count):
                # check k8s nodes are healthy
                if k8s_nodes_ready():
                    logging.info('Cluster validation passed. Proceeding with node draining and termination...')
                    cluster_healthy = True
                else:
                    logging.info('Validation failed for cluster. Expected node count reached but nodes are not healthy.')
            else:
                nodes = get_k8s_nodes()
                logging.info('Current k8s node count is {}'.format(len(nodes)))
                logging.info('Validation failed for cluster. Current node count {} Expected node count {}.'.format(
                    len(nodes),
                    desired_k8s_node_count))
        else:
            logging.info(
                'Validation failed for asg {}.'
                'Instances not healthy'.format(asg_name))
    else:
        logging.info(
            'Validation failed for asg {}.'
            'Not enough instances online'.format(asg_name))
    return cluster_healthy

def get_asg_tag(tags, tag_name):
    """
    Returns a tag on a list of asg tags
    """
    result = {}
    for tag in tags:
        for key, val in tag.items():
            if val == tag_name:
                result = tag
    return result

def plan_asgs(asgs):
    """
    Checks to see which asgs are out of date
    """
    for asg in asgs:
        logging.info('*** Checking autoscaling group {} ***'.format(asg['AutoScalingGroupName']))
        asg_lc_name = asg['LaunchConfigurationName']
        instances = asg['Instances']
        # return a list of outdated instances
        outdated_instances = []
        for instance in instances:
            if instance_outdated(instance, asg_lc_name):
                outdated_instances.append(instance)
        logging.info('Found {} outdated instances'.format(
            len(outdated_instances))
        )


def count_all_cluster_instances(cluster_name):
    count = 0
    asgs = get_asgs(cluster_name)
    for asg in asgs:
        count += len(asg['Instances'])
    logging.info("Current asg instance count in cluster is: {}. K8s node count should match this number".format(count))
    return count


def update_asgs(asgs, cluster_name):
    for asg in asgs:
        logging.info('\n')
        logging.info('****  Starting rolling update for autoscaling group {}  ****'.format(asg['AutoScalingGroupName']))
        asg_name = asg['AutoScalingGroupName']
        asg_lc_name = asg['LaunchConfigurationName']
        asg_old_max_size = asg['MaxSize']
        instances = asg['Instances']
        asg_old_desired_capacity = asg['DesiredCapacity']
        asg_tags = asg['Tags']
        # return a list of outdated instances
        outdated_instances = []
        for instance in instances:
            if instance_outdated(instance, asg_lc_name):
                outdated_instances.append(instance)
        logging.info('Found {} outdated instances'.format(
            len(outdated_instances))
        )
        # skip to next asg if there are no outdated instances
        if len(outdated_instances) == 0:
            continue
        # remove any stale suspentions from asg that may be present
        modify_aws_autoscaling(asg_name, "resume")
        # check for previous run tag on asg
        asg_tag_desired_capacity = get_asg_tag(asg_tags, app_config["ASG_DESIRED_STATE_TAG"])
        if asg_tag_desired_capacity.get('Value'):
            logging.info('Found previous capacity value tag set on asg. Value: {}'.format(asg_tag_desired_capacity.get('Value')))
            logging.info('Maintaining previous capacity to not overscale')
            asg_new_desired_capacity = int(asg_tag_desired_capacity.get('Value'))
            asg_tag_original_capacity = get_asg_tag(asg_tags, app_config["ASG_ORIG_CAPACITY_TAG"])
            logging.info('Maintaining original old capacity from a previous run so we can scale back down to original size of: {}'.format(asg_tag_original_capacity.get('Value')))
            asg_old_desired_capacity = int(asg_tag_original_capacity.get('Value'))
        else:
            logging.info('No previous capacity value tag set on asg')
            # save original capacity to asg tags
            logging.info('Setting original capacity on asg')
            save_asg_tags(asg_name, app_config["ASG_ORIG_CAPACITY_TAG"], asg_old_desired_capacity)
            asg_new_desired_capacity = asg_old_desired_capacity + len(outdated_instances)
            # save new capacity to asg tags
            save_asg_tags(asg_name, app_config["ASG_DESIRED_STATE_TAG"], asg_new_desired_capacity)
        # only change the max size if the new capacity is bigger than current max
        if asg_new_desired_capacity > asg_old_max_size:
            asg_new_max_size = asg_new_desired_capacity
        else:
            # dont change the size
            asg_new_max_size = asg_old_max_size
        # get number of k8s nodes before we scale used later
        # to determine how many new nodes have been created
        k8s_nodes = get_k8s_nodes()
        # now scale up
        scale_asg(asg_name, asg_old_desired_capacity, asg_new_desired_capacity, asg_new_max_size)
        logging.info('Waiting for {} seconds for asg {} to scale before validating cluster health...'.format(app_config['CLUSTER_HEALTH_WAIT'], asg_name))
        time.sleep(app_config['CLUSTER_HEALTH_WAIT'])
        # check how many instances are running
        asg_instance_count = count_all_cluster_instances(cluster_name)
        # check cluster health before doing anything
        if validate_cluster_health(
            asg_name,
            asg_new_desired_capacity,
            asg_instance_count
        ):
            # pause aws autoscaling so new instances dont try
            # to spawn while instances are being terminated
            modify_aws_autoscaling(asg_name, "suspend")
            # start draining and terminating
            for outdated in outdated_instances:
                # catch any failures so we can resume aws autoscaling
                try:
                    # get the k8s node name instead of instance id
                    node_name = get_node_by_instance_id(k8s_nodes, outdated['InstanceId'])
                    drain_node(node_name)
                    delete_node(node_name)
                    terminate_instance(outdated['InstanceId'])
                    if not instance_terminated(outdated['InstanceId']):
                        raise Exception('Instance is failing to terminate. Cancelling out.')
                except Exception as e:
                    raise RollingUpdateException("Rolling update on asg failed", asg_name)

            # scaling cluster back down
            logging.info("Scaling asg back down to original state")
            scale_asg(asg_name, asg_new_desired_capacity, asg_old_desired_capacity, asg_old_max_size)
            # resume aws autoscaling
            modify_aws_autoscaling(asg_name, "resume")
            # remove aws tag
            delete_asg_tags(asg_name, app_config["ASG_DESIRED_STATE_TAG"])
            delete_asg_tags(asg_name, app_config["ASG_ORIG_CAPACITY_TAG"])
            logging.info('*** Rolling update of asg {} is complete! ***'.format(asg_name))
        else:
            logging.info('Exiting since asg healthcheck failed')
            raise Exception('Asg healthcheck failed')
    logging.info('All asgs processed')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Rolling update on cluster')
    parser.add_argument('--cluster_name', '-c', required=True,
                        help='the cluster name to perform rolling update on')
    parser.add_argument('--plan', '-p', nargs='?', const=True,
                        help='perform a dry run to see which instances are out of date')
    args = parser.parse_args()
    # check kubectl is installed
    kctl = shutil.which('kubectl')
    if not kctl:
        logging.info('kubectl is required to be installed before proceeding')
        quit()
    filtered_asgs = get_asgs(args.cluster_name)
    # perform a dry run
    if args.plan:
        plan_asgs(filtered_asgs)
    else:
        # perform real update
        # pause k8s autoscaler
        modify_k8s_autoscaler("pause")
        try:
            update_asgs(filtered_asgs, args.cluster_name)
            # resume autoscaler after asg updated
            modify_k8s_autoscaler("resume")
            logging.info('*** Rolling update of all asg is complete! ***')
        except RollingUpdateException as e:
            logging.info("Rolling update encountered an exception. Resuming aws autoscaling.")
            modify_aws_autoscaling(e.asg_name, "resume")
            # resume autoscaler no matter what happens
            modify_k8s_autoscaler("resume")
        except Exception as e:
            logging.info(e)
            logging.info('*** Rolling update of asg has failed. Exiting ***')
            # resume autoscaler no matter what happens
            modify_k8s_autoscaler("resume")
            quit()

