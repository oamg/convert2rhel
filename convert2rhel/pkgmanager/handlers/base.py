import abc

import six


@six.add_metaclass(abc.ABCMeta)
class TransactionHandlerBase:
    """Abstract class that defines a common interface for the handlers.

    This class is not meant to have actual code implementation, only abstract
    methods that will have a "contract" between the other transaction handlers
    classes that inherit it in their implementation, thus, overriding the
    actual usage of the public methods listed here.

    _base: yum.YumBase | dnf.Base
        Instance of the base class, either YumBase() or Base()
    _enabled_repos: list[str]
        List of repositories to be enabled.
    """

    @abc.abstractmethod
    def __init__(self):
        self._base = None
        self._enabled_repos = []

    @abc.abstractmethod
    def process_transaction(self, test_transaction=False):
        """Process the actual transaction for the base class.

        :param test_transaction: Determines if the transaction needs to be tested or not.
        :type test_transaction: bool
        """
        pass
