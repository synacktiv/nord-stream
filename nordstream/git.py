import subprocess
from nordstream.utils.log import logger

"""
TODO: find an alternative to subprocess it's a bit crappy.
"""


class Git:

    USER = "nord-stream"
    EMAIL = "nord-stream@localhost.com"
    KEY_ID = None
    ATTACK_COMMIT_MSG = "Test deployment"
    CLEAN_COMMIT_MSG = "Remove test deployment"

    @staticmethod
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

    @classmethod
    def gitInitialization(cls, branch, branchAlreadyExists=False):
        logger.verbose("Git init")

        cls.gitRunCommand(f"git config user.Name {cls.USER}")
        cls.gitRunCommand(f"git config user.email {cls.EMAIL}")

        if cls.KEY_ID != None:
            cls.gitRunCommand(f"git config user.signingkey {cls.KEY_ID}")
            cls.gitRunCommand(f"git config commit.gpgsign true")

        if branchAlreadyExists:
            cls.gitRunCommand(f"git checkout {branch}")
            return

        cls.gitRunCommand(f"git checkout --orphan {branch}")
        cls.gitRunCommand(f"git pull origin {branch}")
        cls.gitRunCommand("git rm . -rf")

    @classmethod
    def gitCleanRemote(cls, branch, leaveOneFile=False):
        logger.verbose("Cleaning remote branch")
        cls.gitRunCommand("git rm . -rf")
        cls.gitRunCommand("git rm .github/ -rf")

        if leaveOneFile:
            cls.gitRunCommand(f"touch test_dev.txt")
            cls.gitRunCommand(f"git add -A")

        cls.gitRunCommand(f"git commit -m '{cls.CLEAN_COMMIT_MSG}'")

        if leaveOneFile:
            cls.gitRunCommand(f"git push origin {branch}")
        else:
            cls.gitRunCommand(f"git push -d origin {branch}")

    @classmethod
    def gitRemoteBranchExists(cls, branch):
        logger.verbose("Checking if remote branch exists")
        return cls.gitRunCommand(f"git ls-remote --exit-code origin {branch}")

    @classmethod
    def gitUndoLastPushedCommits(cls, branch, pushedCommitsCount):
        for _ in range(pushedCommitsCount):
            cls.gitRunCommand("git reset --hard HEAD~")

        if pushedCommitsCount and not cls.gitRunCommand(f"git push -f origin {branch}"):
            logger.warning(
                "Could not delete commit(s) pushed by the tool using hard reset and force push. Trying to revert commits."
            )

            cls.gitRunCommand("git pull")
            cls.gitRunCommand(f"git revert --no-commit HEAD~{pushedCommitsCount}..")

            cls.gitRunCommand(f"git commit -m '{cls.CLEAN_COMMIT_MSG}'")
            if pushedCommitsCount and not cls.gitRunCommand(f"git push origin {branch}"):
                logger.error("Error while trying to revert changes !")

    @staticmethod
    def gitDeleteRemote(branch):
        logger.verbose("Git delete remote.")
        return subprocess.Popen(
            f"git push -d origin {branch}",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    @classmethod
    def gitPush(cls, branch):
        logger.verbose("Pushing to remote branch")
        cls.gitRunCommand("git add .")
        cls.gitRunCommand(f"git commit -m '{cls.ATTACK_COMMIT_MSG}'")
        return subprocess.Popen(
            f"git push origin {branch}",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    @classmethod
    def gitCreateEmptyFile(cls, file):
        cls.gitRunCommand(f"touch {file}")

    @classmethod
    def gitMvFile(cls, src, dest):
        cls.gitRunCommand(f"mv {src} {dest}")

    @classmethod
    def gitCpFile(cls, src, dest):
        cls.gitRunCommand(f"cp {src} {dest}")

    @classmethod
    def gitCreateDir(cls, directory):
        cls.gitRunCommand(f"mkdir -p {directory}")

    @staticmethod
    def gitClone(url):
        res = subprocess.Popen(
            f"git clone {url}",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        res.wait()

        if res.returncode == 0:
            return True
        elif b"You appear to have cloned an empty repository" in res.communicate()[1].strip():
            return True
        else:
            return False

    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
