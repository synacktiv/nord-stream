import subprocess
from nordstream.utils.log import logger

"""
TODO: find an alternative to subprocess it's a bit crappy.
"""

"""
Return True if the command succeeds (returns 0), else return False.
"""

ATTACK_COMMIT_MSG = "Test deployment"
CLEAN_COMMIT_MSG = "Remove test deployment"
LOCAL_USERNAME = "nord-stream"
LOCAL_EMAIL = "nord-stream@localhost.com"


def gitRunCommand(command):
    try:
        # debug level
        if logger.level <= 10:
            logger.debug(f"Running: {command}")
            subprocess.run(command, shell=True, check=True)
        else:
            subprocess.run(command, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return False
    return True


def gitInitialization(branch, branchAlreadyExists=False):
    logger.verbose("Git init")

    gitRunCommand(f"git config user.Name {LOCAL_USERNAME}")
    gitRunCommand(f"git config user.email {LOCAL_EMAIL}")

    if branchAlreadyExists:
        gitRunCommand(f"git checkout {branch}")
        return

    gitRunCommand(f"git checkout --orphan {branch}")
    gitRunCommand(f"git pull origin {branch}")
    gitRunCommand("git rm . -rf")


def gitCleanRemote(branch):
    logger.verbose("Cleaning remote branch")
    gitRunCommand("git rm . -rf")
    gitRunCommand("git rm .github/ -rf")
    gitRunCommand(f"git commit -m '{CLEAN_COMMIT_MSG}'")
    gitRunCommand(f"git push -d origin {branch}")


def gitRemoteBranchExists(branch):
    logger.verbose("Checking if remote branch exists")
    return gitRunCommand(f"git ls-remote --exit-code origin {branch}")


def gitUndoLastPushedCommits(branch, pushedCommitsCount):
    for _ in range(pushedCommitsCount):
        gitRunCommand("git reset --hard HEAD~")

    if pushedCommitsCount and not gitRunCommand(f"git push -f origin {branch}"):
        logger.warning("Could not delete commit(s) pushed by the tool.")


def gitDeleteRemote(branch):
    logger.verbose("Git delete remote.")
    return subprocess.Popen(
        f"git push -d origin {branch}",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def gitPush(branch):
    logger.verbose("Pushing to remote branch")
    gitRunCommand("git add .")
    gitRunCommand(f"git commit -m '{ATTACK_COMMIT_MSG}'")
    return subprocess.Popen(
        f"git push origin {branch}",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def gitCreateEmptyFile(file):
    gitRunCommand(f"touch {file}")


def gitMvFile(src, dest):
    gitRunCommand(f"mv {src} {dest}")


def gitCpFile(src, dest):
    gitRunCommand(f"cp {src} {dest}")


def gitCreateDir(directory):
    gitRunCommand(f"mkdir -p {directory}")


def gitClone(url):
    gitRunCommand(f"git clone {url}")


def gitGetCurrentBranch():
    return (
        subprocess.Popen(
            "git rev-parse --abbrev-ref HEAD | tr -d '\n'",
            shell=True,
            stdout=subprocess.PIPE,
        )
        .communicate()[0]
        .decode("UTF-8")
    )


# not needed anymore
def gitIsGloalUserConfigured():
    res = subprocess.Popen(
        "git config --global user.Name",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    res.wait()
    if res.returncode != 0:
        return False

    return True


# not needed anymore
def gitIsGloalEmailConfigured():
    res = subprocess.Popen(
        "git config --global user.email",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    res.wait()
    if res.returncode != 0:
        return False

    return True
