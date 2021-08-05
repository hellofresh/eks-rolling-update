import boto3
import time
import datetime
import requests
from .logger import logger
from eksrollup.config import app_config

client = boto3.client('autoscaling')
ec2_client = boto3.client('ec2')


def get_all_asgs(cluster_tag):
    """
    Queries AWS and returns all ASG's matching kubernetes.io/cluster/<cluster_tag> = owned
    """
    return get_asgs(cluster_tag, [])


def get_asgs(cluster_tag, asg_names=app_config['ASG_NAMES']):
    """
    Queries AWS and find ASG's matching kubernetes.io/cluster/<cluster_tag> = owned
    If asg_names is not empty, returns only asgs that are inside that list, else return all above asgs
    """
    logger.info('Describing autoscaling groups...')
    paginator = client.get_paginator('describe_auto_scaling_groups')
    page_iterator = paginator.paginate(
        PaginationConfig={'PageSize': 100}
    )
    asg_query = "AutoScalingGroups[] | [?contains(Tags[?Key==`kubernetes.io/cluster/{}`].Value, `owned`)]".format(cluster_tag)
    # filter for only asgs with kube cluster tags
    filtered_asgs = page_iterator.search(asg_query)
    if asg_names:
        # select only asgs provided in asg_names
        specific_asgs = []
        for asg in filtered_asgs:
            if asg['AutoScalingGroupName'] in asg_names:
                specific_asgs.append(asg)
        filtered_asgs = specific_asgs
    return filtered_asgs


def get_launch_template(lt_name):
    """
    Queries AWS and returns the details of a given Launch Template
    """
    logger.info(f'Describing launch template for {lt_name}...')
    response = ec2_client.describe_launch_templates(LaunchTemplateNames=[lt_name])
    return response['LaunchTemplates'][0]


def terminate_instance_in_asg(instance_id):
    """
    Terminates EC2 instance given an instance ID
    """
    if not app_config['DRY_RUN']:
        logger.info('Terminating ec2 instance in ASG {}...'.format(instance_id))
        try:
            response = client.terminate_instance_in_auto_scaling_group(
                InstanceId=instance_id,
                ShouldDecrementDesiredCapacity=True
            )
            if response['ResponseMetadata']['HTTPStatusCode'] == requests.codes.ok:
                logger.info('Termination signal for instance is successfully sent.')
            else:
                logger.info('Termination signal for instance has failed. Response code was {}. Exiting.'.format(response['ResponseMetadata']['HTTPStatusCode']))
                raise Exception('Termination of instance failed. Response code was {}. Exiting.'.format(response['ResponseMetadata']['HTTPStatusCode']))

        except client.exceptions.ClientError as e:
            if 'DryRunOperation' not in str(e):
                raise


def is_asg_healthy(asg_name, max_retry=app_config['GLOBAL_MAX_RETRY'], wait=app_config['GLOBAL_HEALTH_WAIT']):
    """
    Checks that all instances in an ASG have a HealthStatus of healthy. Returns False if not
    """
    retry_count = 1
    asg_healthy = False
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
    if not app_config['DRY_RUN']:
        response = client.update_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            DesiredCapacity=new_desired_capacity,
            MaxSize=new_max_size)
        if response['ResponseMetadata']['HTTPStatusCode'] != requests.codes.ok:
            logger.info('AWS scale up operation did not succeed. Exiting.')
            raise Exception('AWS scale up operation did not succeed. Exiting.')
    else:
        logger.info('Skipping asg scaling due to dry run flag set')


def save_asg_tags(asg_name, key, value):
    """
    Adds a tag to asg for later retrieval
    """
    logger.info('Saving tag to asg key: {}, value : {}...'.format(key, value))
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
            logger.info('AWS asg tag modification operation did not succeed. Exiting.')
            raise Exception('AWS asg tag modification operation did not succeed. Exiting.')
    else:
        logger.info('Skipping asg tag modification due to dry run flag set')
        response = {'message': 'dry run only'}
    return response


def instance_outdated_launchconfiguration(instance_obj, asg_lc_name):
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


def instance_outdated_launchtemplate(instance_obj, asg_lt_name, asg_lt_version):
    """
    Checks that the launch template on an instance matches a given string and version. This is often configured in the
    auto scaling group as $Latest or $Default which we can resolve to an actual version number through the
    describe_launch_templates boto3 method (wrapped in get_launch_template).
    """
    instance_id = instance_obj['InstanceId']
    try:
        lt_name = instance_obj['LaunchTemplate']['LaunchTemplateName']
        lt_version = int(instance_obj['LaunchTemplate']['Version'])
    except KeyError:
        logger.info("Instance id {} missing launch template does not match asg launch template of '{}'".format(instance_id, asg_lt_name))
        return True

    if lt_name != asg_lt_name:
        logger.info("Instance id {} launch template of '{}' does not match asg launch template of '{}'".format(instance_id, lt_name, asg_lt_name))
        return True
    elif asg_lt_version == "$Latest":
        latest_lt_version = get_launch_template(asg_lt_name)['LatestVersionNumber']
        if lt_version != latest_lt_version:
            logger.info(
                "Instance id {} launch template version of '{}' does not match asg launch template version of '{}'".format(instance_id, lt_version, latest_lt_version))
            return True
    elif asg_lt_version == "$Default":
        default_lt_version = get_launch_template(asg_lt_name)['DefaultVersionNumber']
        if lt_version != default_lt_version:
            logger.info(
                "Instance id {} launch template version of '{}' does not match asg launch template version of '{}'".format(instance_id, lt_version, default_lt_version))
            return True
    elif lt_version != int(asg_lt_version):
        logger.info(f"Instance id {instance_id} has a different launch configuration version to the ASG")
        return True

    logger.info("Instance id {} : OK ".format(instance_id))
    return False


def instance_outdated_age(instance_id, days_fresh):
    """
    Checks the age of an instance against the MAX_ALLOWABLE_NODE_AGE.
    """

    response = ec2_client.describe_instances(
        InstanceIds=[
            instance_id,
        ]
    )

    instance_launch_time = response['Reservations'][0]['Instances'][0]['LaunchTime']

    # gets the age of a node by days only:
    instance_age = ((datetime.datetime.now(instance_launch_time.tzinfo) - instance_launch_time).days)

    # gets the remaining age of a node in seconds (e.g. if node is y days and x seconds old this will only retrieve the x seconds):
    instance_age_remainder = ((datetime.datetime.now(instance_launch_time.tzinfo) - instance_launch_time).seconds)

    if instance_age > days_fresh:
        logger.info("Instance id {} launch age of '{}' day(s) is older than expected '{}' day(s)".format(instance_id, instance_age, days_fresh))
        return True
    elif (instance_age == days_fresh) and (instance_age_remainder > 0):
        logger.info("Instance id {} is older than expected '{}' day(s) by {} seconds.".format(instance_id, days_fresh, instance_age_remainder))
        return True
    else:
        logger.info("Instance id {} : OK ".format(instance_id))
        return False


def instance_terminated(instance_id, max_retry=app_config['GLOBAL_MAX_RETRY'], wait=app_config['GLOBAL_HEALTH_WAIT'],
                        wait_for_stopping=app_config['INSTANCE_WAIT_FOR_STOPPING']):
    """
    Checks that an ec2 instance is terminated or stopped given an InstanceID
    Overridable to detect shutting-down or stopped states
    """
    retry_count = 1
    is_instance_terminated = False
    while retry_count < max_retry:
        logger.info('Checking instance {} is terminated...'.format(instance_id))
        retry_count += 1
        response = ec2_client.describe_instances(
            InstanceIds=[instance_id]
        )
        state = response['Reservations'][0]['Instances'][0]['State']
        stop_states = ['terminated', 'stopped']
        stopping_states = ['shutting-down', 'stopping']

        if state['Name'] in stop_states or (wait_for_stopping and state['Name'] in stopping_states):
            logger.info('Instance {} {}!'.format(instance_id, state['Name']))
            is_instance_terminated = True
            break
        else:
            is_instance_terminated = False
            logger.info('Instance {} is {}, checking again...'.format(instance_id, state['Name']))

        time.sleep(wait)
    return is_instance_terminated


def plan_asgs(asgs):
    """
    Checks to see which asgs are out of date
    """
    asg_outdated_instance_dict = {}
    for asg in asgs:
        asg_name = asg['AutoScalingGroupName']
        logger.info('*** Checking autoscaling group {} ***'.format(asg_name))
        launch_type = ""
        asg_lc_name = ""
        asg_lt_name = ""
        asg_lt_version = ""
        if 'LaunchConfigurationName' in asg:
            launch_type = "LaunchConfiguration"
            asg_lc_name = asg['LaunchConfigurationName']
        elif 'LaunchTemplate' in asg:
            launch_type = "LaunchTemplate"
            asg_lt_name = asg['LaunchTemplate']['LaunchTemplateName']
            asg_lt_version = asg['LaunchTemplate']['Version']
        elif 'MixedInstancesPolicy' in asg:
            launch_type = "LaunchTemplate"
            asg_lt_name = asg['MixedInstancesPolicy']['LaunchTemplate']['LaunchTemplateSpecification'][
                'LaunchTemplateName']
            asg_lt_version = asg['MixedInstancesPolicy']['LaunchTemplate']['LaunchTemplateSpecification'][
                'Version']
        else:
            logger.error(f"Auto Scaling Group {asg_name} doesn't have LaunchConfigurationName or LaunchTemplate")

        instances = asg['Instances']
        # return a list of outdated instances
        outdated_instances = []
        for instance in instances:
            if launch_type == "LaunchConfiguration":
                if instance_outdated_launchconfiguration(instance, asg_lc_name):
                    outdated_instances.append(instance)
            elif launch_type == "LaunchTemplate":
                if instance_outdated_launchtemplate(instance, asg_lt_name, asg_lt_version):
                    outdated_instances.append(instance)
        logger.info('Found {} outdated instances'.format(
            len(outdated_instances))
        )
        asg_outdated_instance_dict[asg_name] = outdated_instances, asg

    return asg_outdated_instance_dict


def plan_asgs_older_nodes(asgs):
    """
    Checks to see which asgs are out of date
    """
    days_fresh = app_config['MAX_ALLOWABLE_NODE_AGE']

    asg_outdated_instance_dict = {}
    for asg in asgs:
        asg_name = asg['AutoScalingGroupName']
        logger.info('*** Checking for nodes older than {} days in autoscaling group {} ***'.format(days_fresh, asg_name))

        instances = asg['Instances']
        # return a list of outdated instances
        outdated_instances = []
        for instance in instances:
            if instance_outdated_age(instance['InstanceId'], days_fresh):
                outdated_instances.append(instance)
        logger.info('Found {} outdated instances'.format(
            len(outdated_instances))
        )
        asg_outdated_instance_dict[asg_name] = outdated_instances, asg

    return asg_outdated_instance_dict


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


def count_all_cluster_instances(cluster_name, predictive=False):
    """
    Returns the total number of ec2 instances in a k8s cluster
    """
    count = 0
    asgs = get_all_asgs(cluster_name)
    for asg in asgs:
        if predictive:
            count += asg['DesiredCapacity']
        else:
            count += len(asg['Instances'])
    logger.info("{} asg instance count in cluster is: {}. K8s node count should match this number".format("*** Predicted" if predictive else "Current", count))
    return count
