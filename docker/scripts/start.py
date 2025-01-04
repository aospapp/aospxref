#!/usr/bin/env python3

import logging
import os
import queue
import shutil
import signal
import subprocess
import tempfile
import threading
import time

from opengrok_tools.config_merge import merge_config_files
from opengrok_tools.deploy import deploy_war
from opengrok_tools.utils.commandsequence import COMMAND_PROPERTY, ENV_PROPERTY
from opengrok_tools.utils.exitvals import SUCCESS_EXITVAL
from opengrok_tools.utils.indexer import Indexer
from opengrok_tools.utils.log import (
    get_class_basename,
    get_console_logger,
    get_log_level,
)
from opengrok_tools.utils.opengrok import (
    add_project,
    delete_project,
    get_configuration,
    get_repos,
    list_projects,
)
from requests import ConnectionError, get

import docker_config

fs_root = os.path.abspath(".").split(os.path.sep)[0] + os.path.sep
tomcat_root = os.path.join(fs_root, "usr", "local", "tomcat")

OPENGROK_BASE_DIR = os.path.join(fs_root, "opengrok")
OPENGROK_LIB_DIR = os.path.join(OPENGROK_BASE_DIR, "lib")
OPENGROK_DATA_ROOT = os.path.join(OPENGROK_BASE_DIR, "data")
OPENGROK_SRC_ROOT = os.path.join(OPENGROK_BASE_DIR, "src")
BODY_INCLUDE_FILE = os.path.join(OPENGROK_DATA_ROOT, "body_include")
OPENGROK_CONFIG_DIR = os.path.join(OPENGROK_BASE_DIR, "etc")
OPENGROK_WEBAPPS_DIR = os.path.join(tomcat_root, "webapps")
OPENGROK_JAR = os.path.join(OPENGROK_LIB_DIR, "opengrok.jar")

AOSPAPP_BASE_DIR = os.path.join(fs_root, "aospapp")
ROOT_WAR = os.path.join(AOSPAPP_BASE_DIR, "ROOT.war")

task_queue = queue.Queue()


def format_url_root(logger, url_root):
    """
    Set URL root and URI based on input
    :param logger: logger instance
    :param url_root: input
    :return: URI and URL root
    """
    if not url_root:
        url_root = "/"

    if " " in url_root:
        logger.warn("Deployment path contains spaces. Deploying to root")
        url_root = "/"

    # Remove leading and trailing slashes
    if url_root.startswith("/"):
        url_root = url_root[1:]
    if url_root.endswith("/"):
        url_root = url_root[:-1]

    uri = "http://localhost:8080/" + url_root
    #
    # Make sure URI ends with slash. This is important for the various API
    # calls, notably for those that check the HTTP error code.
    # Normally accessing the URI without the terminating slash results in
    # HTTP redirect (code 302) instead of success (200).
    #
    if not uri.endswith("/"):
        uri = uri + "/"

    return uri, url_root


def deploy_opengrok(logger, url_root, config_file):
    """
    Deploy the web application, will regenerate webapps dir
    :param logger: logger instance
    :param url_root: web app URL root
    :param config_file: config file path
    """

    logger.info("Deploying web application for {}".format(url_root))
    webapps_dir = os.path.join(tomcat_root, "webapps")
    if not os.path.isdir(webapps_dir):
        raise Exception("{} is not a directory".format(webapps_dir))

    for item in os.listdir(webapps_dir):
        subdir = os.path.join(webapps_dir, item)
        if os.path.isdir(subdir):
            logger.debug("Removing '{}' directory recursively".format(subdir))
            shutil.rmtree(subdir)

    deploy_war(
        logger,
        os.path.join(OPENGROK_LIB_DIR, "source.war"),
        os.path.join(OPENGROK_WEBAPPS_DIR, url_root + ".war"),
        config_file,
        None,
    )


def wait_for_tomcat(logger, uri):
    """
    Active/busy waiting for Tomcat to come up.
    Currently, there is no upper time bound.
    """
    logger.info("Waiting for Tomcat to start")

    while True:
        try:
            ret = get(uri)
            status = ret.status_code
        except ConnectionError:
            status = 0

        if status != 200:
            logger.debug(
                "Got status {} for {}, sleeping for 1 second".format(status, uri)
            )
            time.sleep(1)
        else:
            break

    logger.info("Tomcat is ready")


def refresh_projects(logger, uri, api_timeout):
    """
    Ensure each immediate source root subdirectory is a project.
    """
    webapp_projects = list_projects(logger, uri, timeout=api_timeout)
    if webapp_projects is None:
        return

    logger.debug("Projects from the web app: {}".format(webapp_projects))
    src_root = OPENGROK_SRC_ROOT

    # Add projects for top-level directories under source root.
    for item in os.listdir(src_root):
        logger.debug("Got item {}".format(item))
        if os.path.isdir(os.path.join(src_root, item)):
            if item in webapp_projects:
                action = "Refreshing"
            else:
                action = "Adding"
            logger.info(f"{action} project {item}")
            add_project(logger, item, uri, timeout=api_timeout)

            if logger.level == logging.DEBUG:
                repos = get_repos(logger, item, uri)
                if repos:
                    logger.debug(
                        "Project {} has these repositories: {}".format(item, repos)
                    )

    # Remove projects that no longer have source.
    for item in webapp_projects:
        if not os.path.isdir(os.path.join(src_root, item)):
            logger.info("Deleting project {}".format(item))
            delete_project(logger, item, uri, timeout=api_timeout)


def save_config(logger, uri, config_path, api_timeout):
    """
    Retrieve configuration from the web app and write it to file.
    :param logger: logger instance
    :param uri: web app URI
    :param config_path: file path
    """

    config = get_configuration(logger, uri, timeout=api_timeout)
    if config is None:
        return

    logger.info("Saving configuration to {}".format(config_path))
    with open(config_path, "w+") as config_file:
        config_file.write(config)


def merge_commands_env(commands, env):
    """
    Merge environment into command structure. If any of the commands has
    an environment already set, the env is merged in.
    :param commands: commands structure
    :param env: environment dictionary
    :return: updated commands structure
    """
    for entry in commands:
        cmd = entry.get(COMMAND_PROPERTY)
        if cmd:
            cmd_env = cmd.get(ENV_PROPERTY)
            if cmd_env:
                cmd_env.update(env)
            else:
                cmd[ENV_PROPERTY] = env

    return commands


def project_indexer(logger, project, uri, config_path):
    """
    Wrapper for running opengrok-sync.
    To be run in a thread/process in the background.
    """

    wait_for_tomcat(logger, uri)

    logger.info("Index starting: " + project)

    indexer_java_opts = docker_config.INDEXER_JAVA_OPTS
    if indexer_java_opts:
        indexer_java_opts = indexer_java_opts.split()

    indexer_options = [
        "-s",
        os.path.join(OPENGROK_SRC_ROOT, project),
        "-d",
        os.path.join(OPENGROK_DATA_ROOT, project),
        "-c",
        "/usr/local/bin/ctags",
        "-H",
        "-P",
        "-S",
        "-G",
        "-W",
        config_path,
        "-U",
        "http://localhost:8080/" + project,
    ]

    indexer = Indexer(
        indexer_options,
        java_opts=indexer_java_opts,
        jar=OPENGROK_JAR,
        logger=logger,
        doprint=True,
    )
    indexer.execute()
    ret = indexer.getretcode()
    if ret != SUCCESS_EXITVAL:
        logger.error(f"Command returned {ret}")
        logger.error(indexer.geterroutput())
        raise Exception("Failed to index")
    logger.info("Index done: " + project)


def create_bare_config(logger, aosp_project, config_file):
    """
    Create bare configuration file with a few basic settings.
    """

    indexer_java_opts = docker_config.INDEXER_JAVA_OPTS
    if indexer_java_opts:
        indexer_java_opts = indexer_java_opts.split()

    logger.info("Creating bare configuration in {}".format(config_file))
    indexer_options = [
        "-s",
        os.path.join(OPENGROK_SRC_ROOT, aosp_project),
        "-d",
        os.path.join(OPENGROK_DATA_ROOT, aosp_project),
        "-c",
        "/usr/local/bin/ctags",
        "--remote",
        "on",
        "-H",
        "-S",
        "-W",
        "-P",
        config_file,
        "--noIndex",
    ]

    indexer = Indexer(
        indexer_options,
        java_opts=indexer_java_opts,
        jar=OPENGROK_JAR,
        logger=logger,
        doprint=True,
    )
    indexer.execute()
    ret = indexer.getretcode()
    if ret != SUCCESS_EXITVAL:
        logger.error(f"Command returned {ret}")
        logger.error(indexer.geterroutput())
        raise Exception("Failed to create bare configuration")


def check_index_and_wipe_out(logger, project, config_file):
    """
    Check index by running the indexer. If the index does not match
    currently running version and the CHECK_INDEX environment variable
    is non-empty, wipe out the directories under data root.
    """
    indexer_java_opts = docker_config.INDEXER_JAVA_OPTS
    if indexer_java_opts:
        indexer_java_opts = indexer_java_opts.split()

    if docker_config.CHECK_INDEX and os.path.exists(config_file):
        logger.info("Checking if index matches current version")
        indexer_options = ["-R", config_file, "--checkIndex", "version"]
        indexer = Indexer(
            indexer_options,
            java_opts=indexer_java_opts,
            logger=logger,
            jar=OPENGROK_JAR,
            doprint=True,
        )
        indexer.execute()
        if indexer.getretcode() == 1:
            if not docker_config.TEST_MODE:
                logger.info("Wiping out data root")
                root = os.path.join(OPENGROK_DATA_ROOT, project)
                for entry in os.listdir(root):
                    path = os.path.join(root, entry)
                    if os.path.isdir(path):
                        try:
                            logger.info(f"Removing '{path}'")
                            shutil.rmtree(path)
                        except Exception as exc:
                            logger.error("cannot delete '{}': {}".format(path, exc))
            else:
                print("[TEST] ignore wiping data")


def get_all_aosp_projects():
    return [entry for entry in os.listdir(OPENGROK_SRC_ROOT) if os.path.isdir(os.path.join(OPENGROK_SRC_ROOT, entry))]


def process_project(logger, log_level, project):
    logger.debug("AOSP_PROJECT = {}".format(project))
    uri, url_root = format_url_root(logger, project)
    logger.debug("\tURL_ROOT = {}".format(url_root))
    logger.debug("\tURI = {}".format(uri))
    config_file_path = os.path.join(OPENGROK_CONFIG_DIR, project, "configuration.xml")
    deploy_opengrok(logger, url_root, config_file_path)
    if not os.path.exists(config_file_path) or os.path.getsize(config_file_path) == 0:
        create_bare_config(logger, project, config_file_path)

    check_index_and_wipe_out(logger, project, config_file_path)

    #
    # If there is read-only configuration file, merge it with current
    # configuration.
    #
    read_only_config_file = docker_config.READONLY_CONFIG_FILE
    if read_only_config_file and os.path.exists(read_only_config_file):
        logger.info(
            "Merging read-only configuration from '{}' with current "
            "configuration in '{}'".format(read_only_config_file, config_file_path)
        )
        out_file_path = None
        with tempfile.NamedTemporaryFile(
                mode="w+", delete=False, prefix="merged_config"
        ) as tmp_out_fobj:
            out_file_path = tmp_out_fobj.name
            merge_config_files(
                read_only_config_file,
                config_file_path,
                out_file_path,
                jar=OPENGROK_JAR,
                loglevel=log_level,
            )

        if out_file_path and os.path.getsize(out_file_path) > 0:
            shutil.move(out_file_path, config_file_path)
        else:
            logger.warning(
                "Failed to merge read-only configuration, "
                "leaving the original in place"
            )
            if out_file_path:
                os.remove(out_file_path)

    indexer_args = (
        logger,
        project,
        uri,
        config_file_path,
    )

    logger.debug("Queue index thread")
    index_thread = threading.Thread(
        target=project_indexer, name="Indexer thread for " + project, args=indexer_args, daemon=True
    )
    task_queue.put(index_thread)


def indexer_worker():
    while not task_queue.empty():
        task = task_queue.get()
        task.start()
        task.join()


def main():
    log_level = docker_config.OPENGROK_LOG_LEVEL
    if log_level:
        log_level = get_log_level(log_level)
    else:
        log_level = logging.INFO

    logger = get_console_logger(get_class_basename(), log_level)

    logger.info("Welcome to opengrok env for aosp.app")

    try:
        with open(os.path.join(OPENGROK_BASE_DIR, "VERSION"), "r") as f:
            version = f.read()
            logger.info("Running version {}".format(version))
    except Exception:
        pass

    # Deploy ROOT.war
    deploy_war(
        logger,
        ROOT_WAR,
        os.path.join(OPENGROK_WEBAPPS_DIR, "ROOT.war"),
        None,
        None,
    )

    # Deploy opengrok for each aosp project
    aosp_projects = get_all_aosp_projects()
    for project in aosp_projects:
        if project.startswith("android-"):
            process_project(logger, log_level, project)

    task_thread = threading.Thread(
        target=indexer_worker, name="Indexer Worker thread", daemon=True
    )
    task_thread.start()

    # Start Tomcat last.
    logger.info("Starting Tomcat")
    tomcat_temp = os.path.join(OPENGROK_DATA_ROOT, "tomcat_temp")
    os.makedirs(tomcat_temp, exist_ok=True)
    tomcat_env = dict(os.environ)
    tomcat_env["CATALINA_TMPDIR"] = tomcat_temp
    tomcat_popen = subprocess.Popen(
        [os.path.join(tomcat_root, "bin", "catalina.sh"), "run"], env=tomcat_env
    )

    sigset = set()
    sigset.add(signal.SIGTERM)
    sigset.add(signal.SIGINT)
    signum = signal.sigwait(sigset)
    logger.info("Received signal {}".format(signum))
    if tomcat_popen:
        logger.info("Terminating Tomcat {}".format(tomcat_popen))
        tomcat_popen.terminate()


if __name__ == "__main__":
    main()