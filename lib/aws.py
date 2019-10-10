import boto3
import time
import requests
from lib.logger import logger
from config import app_config

client = boto3.client('autoscaling')
ec2_client = boto3.client('ec2')


def get_asgs(cluster_tag):
    """
    Queries AWS and returns all ASG's matching kubernetes.io/cluster/<cluster_tag> = owned
    """
    logger.info('Describing autoscaling groups...')
    paginator = client.get_paginator('describe_auto_scaling_groups')
    page_iterator = paginator.paginate(
        PaginationConfig={'PageSize': 100}
    )
    asg_query = "AutoScalingGroups[] | [?contains(Tags[?Key==`kubernetes.io/cluster/{}`].Value, `owned`)]".format(cluster_tag)
    # filter for only asgs with kube cluster tags
    filtered_asgs = page_iterator.search(asg_query)
    return filtered_asgs


def terminate_instance(instance_id):
    """
    Terminates EC2 instance given an instance ID
    """
    logger.info('Terminating ec2 instance {}...'.format(instance_id))
    try:
        response = ec2_client.terminate_instances(
            InstanceIds=[instance_id],
            DryRun=app_config['DRY_RUN']
        )
        if response['ResponseMetadata']['HTTPStatusCode'] == requests.codes.ok:
            logger.info('Termination of instance succeeded.')
        else:
            logger.info('Termination of instance failed. Response code was {}. Exiting.'.format(response['ResponseMetadata']['HTTPStatusCode']))
            raise Exception('Termination of instance failed. Response code was {}. Exiting.'.format(response['ResponseMetadata']['HTTPStatusCode']))

    except client.exceptions.ClientError as e:
        if 'DryRunOperation' not in str(e):
            raise


def is_asg_healthy(asg_name, max_retry=app_config['GLOBAL_MAX_RETRY'], wait=app_config['GLOBAL_HEALTH_WAIT']):
    """
    Checks that all instances in an ASG have a HealthStatus of healthy. Returns False if not
    """
    retry_count = 1
    while retry_count < max_retry:
        asg_healthy = True
        retry_count += 1
        logger.info('Checking asg {} instance health...'.format(asg_name))
        response = client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[asg_name], MaxRecords=1
        )
        instances = response['AutoScalingGroups'][0]['Instances']
        for instance in instances:
            logger.info('Instance {} - {}'.format(
                instance['InstanceId'],
                instance['HealthStatus']
            ))
            if instance['HealthStatus'] != 'Healthy':
                asg_healthy = False
        if asg_healthy:
            break
        time.sleep(wait)
    else:
        logger.info('asg {} - Healthy.'.format(asg_name))
    return asg_healthy


def is_asg_scaled(asg_name, desired_capacity):
    """
    Checks that the number of EC2 instances in an ASG matches desired capacity
    """
    is_scaled = False
    logger.info('Checking asg {} instance count...'.format(asg_name))
    response = client.describe_auto_scaling_groups(
        AutoScalingGroupNames=[asg_name], MaxRecords=1
    )
    actual_instances = response['AutoScalingGroups'][0]['Instances']
    if len(actual_instances) != desired_capacity:
        logger.info('Asg {} does not have enough running instances to proceed'.format(asg_name))
        logger.info('Actual instances: {} Desired instances: {}'.format(
            len(actual_instances),
            desired_capacity)
        )
        is_scaled = False
    else:
        logger.info('Asg {} scaled OK'.format(asg_name))
        logger.info('Actual instances: {} Desired instances: {}'.format(
            len(actual_instances),
            desired_capacity)
        )
        is_scaled = True
    return is_scaled


def modify_aws_autoscaling(asg_name, action):
    """
    Suspends or resumes ASG autoscaling
    """
    logger.info('Modifying asg {} autoscaling to {} ...'.format(
        asg_name,
        action)
    )
    if app_config['DRY_RUN'] is not True:

        if action == "suspend":
            response = client.suspend_processes(
                AutoScalingGroupName=asg_name,
                ScalingProcesses=['Launch', 'ReplaceUnhealthy'])
        elif action == "resume":
            response = client.resume_processes(
                AutoScalingGroupName=asg_name,
                ScalingProcesses=['Launch', 'ReplaceUnhealthy'])
        else:
            logger.info('Invalid scaling option')
            raise Exception('Invalid scaling option')

        if response['ResponseMetadata']['HTTPStatusCode'] != requests.codes.ok:
            logger.info('AWS asg modification operation did not succeed. Exiting.')
            raise Exception('AWS asg modification operation did not succeed. Exiting.')
    else:
        logger.info('Skipping asg modification due to dry run flag set')
        response = {'message': 'dry run only'}

    return response


def scale_asg(asg_name, current_desired_capacity, new_desired_capacity, new_max_size):
    """
    Changes the desired capacity of an asg
    """
    logger.info('Setting asg desired capacity from {} to {} and max size to {}...'.format(current_desired_capacity, new_desired_capacity, new_max_size))
    if app_config['DRY_RUN'] is not True:
        response = client.update_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            DesiredCapacity=new_desired_capacity,
            MaxSize=new_max_size)
        if response['ResponseMetadata']['HTTPStatusCode'] != requests.codes.ok:
            logger.info('AWS scale up operation did not succeed. Exiting.')
            raise Exception('AWS scale up operation did not succeed. Exiting.')
    else:
        logger.info('Skipping asg scaling due to dry run flag set')
        response = {'message': 'dry run only'}


def save_asg_tags(asg_name, key, value):
    """
    Adds a tag to asg for later retrieval
    """
    logger.info('Saving tag to asg key: {}, value : {}...'.format(key, value))
    if app_config['DRY_RUN'] is not True:
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
            logger.info('AWS asg tag modification operation did not succeed. Exiting.')
            raise Exception('AWS asg tag modification operation did not succeed. Exiting.')
    else:
        logger.info('Skipping asg tag modification due to dry run flag set')
        response = {'message': 'dry run only'}
    return response


def delete_asg_tags(asg_name, key):
    """
    Deletes a tag from asg
    """
    logger.info('Deleting tag from asg key: {}...'.format(key))
    if app_config['DRY_RUN'] is not True:
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
            logger.info('AWS asg tag modification operation did not succeed. Exiting.')
            raise Exception('AWS asg tag modification operation did not succeed. Exiting.')
    else:
        logger.info('Skipping asg tag modification due to dry run flag set')
        response = {'message': 'dry run only'}
    return response


def instance_outdated(instance_obj, asg_lc_name):
    """
    Checks that the launch configuration on an instance matches a given string
    """
    # only one launch config is kept so on some instances it may not actually exist. Making the launch config empty
    lc_name = instance_obj.get('LaunchConfigurationName')
    instance_id = instance_obj['InstanceId']
    if lc_name != asg_lc_name:
        logger.info("Instance id {} launch config of '{}' does not match asg launch config of '{}'".format(instance_id, lc_name, asg_lc_name))
        return True
    else:
        logger.info("Instance id {} : OK ".format(instance_id))
        return False


def instance_terminated(instance_id, max_retry=app_config['GLOBAL_MAX_RETRY'], wait=app_config['GLOBAL_HEALTH_WAIT']):
    """
    Checks that an ec2 instance is terminated or stopped given an InstanceID
    """
    retry_count = 1
    while retry_count < max_retry:
        is_instance_terminated = True
        logger.info('Checking instance {} is terminated...'.format(instance_id))
        retry_count += 1
        response = ec2_client.describe_instances(
            InstanceIds=[instance_id]
        )
        state = response['Reservations'][0]['Instances'][0]['State']
        stop_states = ['terminated', 'stopped']
        if state['Name'] not in stop_states:
            is_instance_terminated = False
            logger.info('Instance {} is still running, checking again...'.format(instance_id))
        else:
            logger.info('Instance {} terminiated!'.format(instance_id))
            is_instance_terminated = True
            break
        time.sleep(wait)
    return is_instance_terminated


def plan_asgs(asgs):
    """
    Checks to see which asgs are out of date
    """
    for asg in asgs:
        logger.info('*** Checking autoscaling group {} ***'.format(asg['AutoScalingGroupName']))
        asg_lc_name = asg['LaunchConfigurationName']
        instances = asg['Instances']
        # return a list of outdated instances
        outdated_instances = []
        for instance in instances:
            if instance_outdated(instance, asg_lc_name):
                outdated_instances.append(instance)
        logger.info('Found {} outdated instances'.format(
            len(outdated_instances))
        )


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


def count_all_cluster_instances(cluster_name):
    """
    Returns the total number of ec2 instances in a k8s cluster
    """
    count = 0
    asgs = get_asgs(cluster_name)
    for asg in asgs:
        count += len(asg['Instances'])
    logger.info("Current asg instance count in cluster is: {}. K8s node count should match this number".format(count))
    return count


def detach_instance(instance_id, asg_name):
    """
    Detach EC2 instance from ASG given an instance ID and an ASG name
    """
    logger.info('Detaching ec2 instance {} from asg {}...'.format(instance_id, asg_name))
    try:
        response = client.detach_instances(
            InstanceIds=[instance_id],
            AutoScalingGroupName=asg_name,
            ShouldDecrementDesiredCapacity=True
        )
        if response['ResponseMetadata']['HTTPStatusCode'] == requests.codes.ok:
            logger.info('Instance detachement from ASG succeeded.')
        else:
            logger.info('Instance detachement from ASG failed. Response code was {}. Exiting.'.format(response['ResponseMetadata']['HTTPStatusCode']))
            raise Exception('Instance detachement from ASG failed. Response code was {}. Exiting.'.format(response['ResponseMetadata']['HTTPStatusCode']))

    except client.exceptions.ClientError as e:
        if 'DryRunOperation' not in str(e):
            raise


def instance_detached(instance_id, max_retry=app_config['GLOBAL_MAX_RETRY'], wait=app_config['GLOBAL_HEALTH_WAIT']):
    """
    Checks that an ec2 instance is detached from any asg given an InstanceID
    """
    retry_count = 1
    while retry_count < max_retry:
        is_instance_detached = True
        logger.info('Checking instance {} is detached...'.format(instance_id))
        retry_count += 1
        response = client.describe_auto_scaling_instances(
            InstanceIds=[instance_id], MaxRecords=1
        )
        if len(response['AutoScalingInstances']) != 0:
            is_instance_detached = False
            logger.info('Instance {} is still attached, checking again...'.format(instance_id))
        else:
            logger.info('Instance {} detached!'.format(instance_id))
            is_instance_detached = True
            break
        time.sleep(wait)
    return is_instance_detached
