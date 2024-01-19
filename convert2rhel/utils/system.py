__metaclass__ = type

import errno
import json
import logging
import multiprocessing
import os
import shutil
import sys

from functools import wraps

from convert2rhel.exceptions import UnableToSerialize
from convert2rhel.utils import TMP_DIR
from convert2rhel.utils.format import get_traceback_str
from convert2rhel.utils.term import run_subprocess


loggerinst = logging.getLogger(__name__)


def mkdir_p(path):
    """Create all missing directories for the path and raise no exception
    if the path exists.
    """
    try:
        os.makedirs(path)
    except OSError as err:
        if err.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def require_root():
    if os.geteuid() != 0:
        print("The tool needs to be run under the root user.")
        print("\nNo changes were made to the system.")
        sys.exit(1)


def log_traceback(debug):
    """Log a traceback either to both a file and stdout, or just file, based
    on the debug parameter.
    """
    traceback_str = get_traceback_str()
    if debug:
        # Print the traceback to the user when debug option used
        loggerinst.debug(traceback_str)
    else:
        # Print the traceback to the log file in any way
        loggerinst.file(traceback_str)


def remove_orphan_folders():
    """Even after removing redhat-release-* package, some of its folders are
    still present, are empty, and that blocks us from installing centos-release
    pkg back. So, for now, we are removing them manually.
    """
    rh_release_paths = [
        "/usr/share/redhat-release",
        "/usr/share/doc/redhat-release",
    ]

    def is_dir_empty(path):
        return not os.listdir(path)

    for path in rh_release_paths:
        if os.path.exists(path) and is_dir_empty(path):
            os.rmdir(path)


def remove_tmp_dir():
    """Remove temporary folder (TMP_DIR), not needed post-conversion."""
    try:
        shutil.rmtree(TMP_DIR)
        loggerinst.info("Temporary folder %s removed" % TMP_DIR)
    except OSError as err:
        loggerinst.warning("Failed removing temporary folder %s\nError (%s): %s" % (TMP_DIR, err.errno, err.strerror))
    except TypeError:
        loggerinst.warning("TypeError error while removing temporary folder %s" % TMP_DIR)


class Process(multiprocessing.Process):
    """Overrides the implementation of the multiprocessing.Process class.

    This class is being overriden to be able to catch all type of exceptions in
    order to not interrupt the conversion if it is not intended to. The
    original behaviour from `multiprocess.Process` is that the code running
    inside the child process will handle the exceptions, so in our case, if we
    raise SystemExit because we are using `logger.critical`, we wouldn't have a
    chance to catch that and enter the rollback.

    .. note::
        Code taken from https://stackoverflow.com/a/63773140
    """

    def __init__(self, *args, **kwargs):
        """Default constructor for the class"""
        multiprocessing.Process.__init__(self, *args, **kwargs)
        self._pconn, self._cconn = multiprocessing.Pipe()
        self._exception = None

    def run(self):
        """Overrides the `run` method to catch exceptions raised in child.

        .. important::
            Exceptions that bubble up to this point will deadlock if the
            traceback are over 64KiB in size. It is not a good idea to let
            unhandled exceptions go up this point as it could cause the threads
            to lock indefinitely.
            Link to comment: https://stackoverflow.com/questions/19924104/python-multiprocessing-handling-child-errors-in-parent/33599967#comment113491531_33599967
        """
        try:
            multiprocessing.Process.run(self)
            self._cconn.send(None)
        # Here, `SystemExit` inherits from `BaseException`, which is too
        # broad to catch as it involves for-loop exceptions. The idea here
        # is to catch `SystemExit` *and* any `Exception` that shows up as we do
        # a lot of logger.critical() and they do raise `SystemExit`.
        except (Exception, SystemExit) as e:
            try:
                import cPickle as pickle
            except ImportError:
                import pickle

            try:
                self._cconn.send(e)
            except pickle.PicklingError:
                self._cconn.send(UnableToSerialize("Child process raised %s: %s" % (type(e), str(e))))

    @property
    def exception(self):
        if self._pconn.poll():
            self._exception = self._pconn.recv()
        return self._exception


def run_as_child_process(func):
    """Decorator to execute functions as child process.

    This decorator will use `multiprocessing.Process` class to initiate the
    function as a child process to the parent process with the intention to
    execute that in its own process, thus, avoiding cases where libraries would
    install signal handlers that could be propagated to the main thread if they
    do not do a proper clean-up.

    .. note::
        This decorator is mostly intended to be used when dealing with
        functions that call directly `rpm` or `yum`.

        In `rpm` (version 4.11.3, RHEL 7), it's known that whenever there is a
        call to that library, it will install a global signal handler catching
        different types of signals, but most importantly, the SIGINT (Ctrl + C)
        one, which causes a problem during the conversion as we can't replace
        or override that signal as it was initiated in a C library rather than
        a python library.

        By using this decorator, `rpm` will install the signal handler in the
        child process and leave the parent one with the original signal
        handling that is initiated by python itself (or, whatever signal is
        registered when the conversion starts as well).

    .. important::
        It is important to know that if a function is using this decorator,
        then it won't be possible for that function to spawn new child
        processes inside their workflow. This is a limitation imposed by the
        `daemon` property used to spawn the the first child process (the
        function being decorated), as it won't let a grandchild process being
        created inside an child process.
        For more information about that, refer to the Python Multiprocessing
        docs: https://docs.python.org/2.7/library/multiprocessing.html#multiprocessing.Process.daemon

        For example::
            # A perfect normal function that spawn a child process
            def functionB():
                ...
                multiprocessing.Process(...)

            # If we want to use this decorator in `functionB()`, we would leave the child process of `functionB()` orphans when the parent process exits.
            @utils.run_as_child_process
            def functionB():
                ...
                multiprocessing.Process(...)
                ...

    :param func: Function attached to the decorator
    :type func: Callable
    :return: A internal callable wrapper
    :rtype: Callable
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        """
        Wrapper function to execute and control the function attached to the
        decorator.

        :arg args: Arguments tied to the function
        :type args: tuple
        :keyword kwargs: Named arguments tied to the function
        :type kwargs: dict

        :raises KeyboardInterrupt: Raises a `KeyboardInterrupt` if a SIGINT is
            caught during the execution of the child process. This exception
            will be re-raised to the stack once it is caught.
        :raises Exception: Raise any general exception that can occur during
            the execution of the child process.

        :return: If the Queue is not empty, return anything in it, otherwise,
            return `None`.
        :rtype: Any
        """

        def inner_wrapper(*args, **kwargs):
            """
            Inner function wrapper to execute decorated functions without the
            need to modify them to have a queue parameter.

            :param args: Arguments tied to the function
            :type args: tuple
            :param kwargs: Named arguments tied to the function
            :type kwargs: dict
            """
            func = kwargs.pop("func")
            queue = kwargs.pop("queue")
            result = func(*args, **kwargs)
            queue.put(result)

        queue = multiprocessing.Queue()
        kwargs.update({"func": func, "queue": queue})
        process = Process(target=inner_wrapper, args=args, kwargs=kwargs)

        # Running the process as a daemon prevents it from hanging if a SIGINT
        # is raised, as all childs will be terminated with it.
        # https://docs.python.org/2.7/library/multiprocessing.html#multiprocessing.Process.daemon
        process.daemon = True
        try:
            process.start()
            process.join()

            if process.exception:
                raise process.exception

            if process.is_alive():
                # If the process is still alive for some reason, try to
                # terminate it.
                process.terminate()

            if not queue.empty():
                # We don't need to block the I/O as we are mostly done with
                # the child process and no exception was raised, so we can
                # instantly retrieve the item that was in the queue.
                return queue.get(block=False)

            return None
        except KeyboardInterrupt:
            # We have to check if the process if alive, and if it is (most
            # probably it will be), then we can call for termination. On
            # Python2 it is most likely that some processes (That calls yum
            # API) will keep executing until they finish their execution and
            # ignore the call for termination issued by the parent. To avoid
            # having "zombie" processes, we need to wait for them to finish.
            loggerinst.warning("Terminating child process...")
            if process.is_alive():
                loggerinst.debug("Process with pid %s is alive", process.pid)
                process.terminate()

            loggerinst.debug("Process with pid %s exited", process.pid)

            # If there is a KeyboardInterrupt raised while the child process is
            # being executed, let's just re-raise it to the stack and move on.
            raise

    # Python2 and Python3 < 3.2 compatibility
    if not hasattr(wrapper, "__wrapped__"):
        wrapper.__wrapped__ = func

    return wrapper


def get_file_content(filename, as_list=False):
    """Return content of a file either as a list of lines or as a multiline
    string.
    """
    lines = []
    if not os.path.exists(filename):
        if not as_list:
            return ""
        return lines
    with open(filename, "r") as file_to_read:
        lines = file_to_read.readlines()
    if as_list:
        # remove newline character from each line
        return [x.strip() for x in lines]

    return "".join(lines)


def store_content_to_file(filename, content):
    """Write the content into the file.

    Accept string or list of strings (in that case every string will be written
    on separate line). In case the ending blankline is missing, the newline
    character is automatically appended to the file.
    """
    if isinstance(content, list):
        content = "\n".join(content)

    if len(content) > 0 and content[-1] != "\n":
        # append the missing newline to comply with standard about text files
        content += "\n"

    with open(filename, "w") as handler:
        handler.write(content)


def restart_system():
    from convert2rhel.toolopts import tool_opts

    if tool_opts.restart:
        run_subprocess(["reboot"])
    else:
        loggerinst.warning("In order to boot the RHEL kernel, restart of the system is needed.")


def write_json_object_to_file(path, data, mode=0o600):
    """Write a Json object to a file in the system.

    :param path: The path of the file to be written.
    :type path: str
    :param data: The JSON data that will be written.
    :type data: dict[str, Any]
    :param mode: The permissions for the file.
    :type mode: int
    """
    with open(path, mode="w") as handler:
        os.chmod(path, mode)
        json.dump(data, handler, indent=4)
