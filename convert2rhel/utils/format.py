__metaclass__ = type

import logging
import sys
import traceback

from convert2rhel.utils import OBFUSCATION_STRING


loggerinst = logging.getLogger(__name__)


class DictWListValues(dict):
    """Python 2.4 replacement for Python 2.5+ collections.defaultdict(list)."""

    def __getitem__(self, item):
        if item not in iter(self.keys()):
            self[item] = []

        return super(DictWListValues, self).__getitem__(item)


def get_traceback_str():
    """Get a traceback of an exception as a string."""
    exc_type, exc_value, exc_traceback = sys.exc_info()
    return "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))


def hide_secrets(
    args, secret_options=frozenset(("--username", "--password", "--activationkey", "--org", "-u", "-p", "-k", "-o"))
):
    """
    Replace secret values passed through a command line with asterisks.

    This function takes a list of command line arguments and returns a new list containing where any secret value is
    replaced with a fixed size of asterisks (*).

    Terminology:
     - an argument is one of whitespace delimited strings of an executed cli command
       Example: `ls -a -w 10 dir` ... four arguments (-a, -w, 10, dir)
     - an option is a subset of arguments that start with - or -- and modify the behavior of a cli command
       Example: `ls -a -w 10 dir` ... two options (-a, -w)
     - an option parameter is the argument following an option if the option requires a value
       Example: `ls -a -w 10 dir` ... one option parameter (10)

    :param: args: A list of command line arguments which may contain secret values.
    :param: secret_options: A set of command line options requiring sensitive or private information.
    :returns: A new list of arguments with secret values hidden.
    """
    sanitized_list = []
    hide_next = False
    for arg in args:
        if hide_next:
            # This is a parameter of a secret option
            arg = OBFUSCATION_STRING
            hide_next = False

        elif arg in secret_options:
            # This is a secret option => mark its parameter (the following argument) to be obfuscated
            hide_next = True

        else:
            # Handle the case where the secret option and its parameter are both in one argument ("--password=SECRET")
            for option in secret_options:
                if arg.startswith(option + "="):
                    arg = "{0}={1}".format(option, OBFUSCATION_STRING)

        sanitized_list.append(arg)

    if hide_next:
        loggerinst.debug(
            "Passed arguments had an option, '{0}', without an expected secret parameter".format(sanitized_list[-1])
        )

    return sanitized_list


def format_sequence_as_message(sequence_of_items):
    """
    Format a sequence of items for display to the user.

    :param sequence_of_items: Sequence of items which should be formatted for
        a message to be printed to the user.
    :type sequence_of_items: Sequence
    :returns: Items formatted appropriately for end user output.
    :rtype: str
    """
    if len(sequence_of_items) < 1:
        message = ""
    elif len(sequence_of_items) == 1:
        message = sequence_of_items[0]
    elif len(sequence_of_items) == 2:
        message = " and ".join(sequence_of_items)
    else:
        message = ", ".join(sequence_of_items[:-1]) + ", and " + sequence_of_items[-1]

    return message


def flatten(dictionary, parent_key=False, separator="."):
    """Turn a nested dictionary into a flattened dictionary.

    .. note::
        If we detect a empty dictionary or list, this function will append a "null" as a value to the key.

    :param dictionary: The dictionary to flatten
    :param parent_key: The string to prepend to dictionary's keys
    :param separator: The string used to separate flattened keys
    :return: A flattened dictionary
    """

    items = []
    for key, value in dictionary.items():
        new_key = str(parent_key) + separator + key if parent_key else key

        if isinstance(value, dict):
            if not value:
                items.append((new_key, "null"))
            else:
                items.extend(flatten(value, new_key, separator).items())
        elif isinstance(value, list):
            if not value:
                items.append((new_key, "null"))
            else:
                for k, v in enumerate(value):
                    items.extend(flatten({str(k): v}, new_key).items())
        else:
            items.append((new_key, value))
    return dict(items)
