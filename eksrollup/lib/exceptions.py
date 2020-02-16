class RollingUpdateException(Exception):
    def __init__(self, message, asg_name):
        self.message = message
        self.asg_name = asg_name
