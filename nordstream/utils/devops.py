import logging
from nordstream.cicd.devops import DevOps
from nordstream.utils.log import logger

def listOrgs(token):
    response = DevOps.getOrgs(token)
    logger.info("User orgs:")
    for org in response:
        logger.raw(f"\t- {org.get('AccountName')}\n", logging.INFO)