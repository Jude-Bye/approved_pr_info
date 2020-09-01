from pr_info_gatherer.const_defines import Defines
from pr_info_gatherer.common import enum_with_checks, warn_assert, UserInputError
import abc
import copy
from typing import List, Tuple, Optional, Union
from enum import IntEnum
import os

####################################
### CommandLineArgParser classes - handlers of process arguments
####################################


class CommandLineArgParser(abc.ABC):
    """ Base class for command line switch parsers """

    def __init__(self, key_name: str, cmd_text: str, p_type: str):
        self.key_name: str = key_name
        self.cli_text: str = cmd_text
        self.type: str = p_type

    @abc.abstractmethod
    def apply_arg(self, targetKey: str, targetDict: dict):
        pass

    @abc.abstractmethod
    def read_args(self, iterIndex: int, args: Tuple[str]) -> Tuple[int, Optional[Exception]]:
        pass

    def validate_cmd_text(self, comp: str):
        if self.cli_text != comp:
            raise UserInputError(f'Given argument does not match cmd_text: "{self.cli_text}" vs "{comp}"')

    @staticmethod
    def _read_args_until_next_command(iterIndex: int, argv: Tuple[str], switchName: str, expectedCount: int = -1) \
            -> Tuple[int, List[str]]:
        count = len(argv)
        i = iterIndex
        retVal: List[str] = []

        while i < count and argv[i][0] != '-':
            if not isinstance(argv[i], str):
                raise UserInputError(f'Invalid argument type: {type(argv[i])}')
            retVal.append(argv[i])
            i += 1

        gatheredCount = i - iterIndex
        if gatheredCount <= 0:
            raise UserInputError(f'No arguments were provided for switch \'{switchName}\'')
        if expectedCount > 0:
            warn_assert(gatheredCount == expectedCount, lambda: 'Unexpected count of arguments for '
                                                                f'switch[{switchName}] -> "{gatheredCount}"')
        return i - 1, retVal


class RepoCLArg(CommandLineArgParser):
    """ Command line switch parser that gathers list of repositories """

    CLI_TEXT = f'-{(KEY_NAME := "repos")}'
    TYPE = 'r_a'

    def __init__(self):
        super().__init__(RepoCLArg.KEY_NAME, RepoCLArg.CLI_TEXT, RepoCLArg.TYPE)
        self.repoList: List[str] = []

    def apply_arg(self, targetKey: str, targetDict: dict):
        targetDict[targetKey] = targetDict[targetKey] + copy.copy(self.repoList)

    def read_args(self, iterIndex: int, argv: Tuple[str]) -> Tuple[int, Optional[Exception]]:
        err: Optional[Exception] = None
        try:
            self.validate_cmd_text(argv[iterIndex])
            newIndex, repos = CommandLineArgParser._read_args_until_next_command(iterIndex + 1, argv, self.cli_text)
            self.repoList.extend(repos)
        except Exception as exc:
            err = exc
            newIndex = iterIndex

        return newIndex, err


class ApiTokenCLArg(CommandLineArgParser):
    """ Command line switch parser that reads api token, be it via filepath or valid token string """

    CLI_TEXT = f'-{(KEY_NAME := "api_token")}'
    TYPE = 'at_a'

    def __init__(self):
        super().__init__(ApiTokenCLArg.KEY_NAME, ApiTokenCLArg.CLI_TEXT, ApiTokenCLArg.TYPE)
        self.token = Defines.DEFAULT_TOKEN

    def apply_arg(self, targetKey: str, targetDict: dict):
        targetDict[targetKey] = self.token

    def read_args(self, iterIndex: int, argv: Tuple[str]) -> Tuple[int, Optional[Exception]]:
        try:
            self.validate_cmd_text(argv[iterIndex])

            newIndex, gatheredArgs = CommandLineArgParser._read_args_until_next_command(iterIndex + 1, argv, self.cli_text, 1)
            tokenString = gatheredArgs[0]

            if os.path.exists(tokenString):
                with open(tokenString, 'rb') as tokenFile:
                    self.token = str(tokenFile.read(Defines.TOKEN_LENGTH), Defines.TOKEN_FILE_ENCODING)
            else:
                if len(tokenString) != Defines.TOKEN_LENGTH:
                    raise UserInputError(f'Token argument, is not an existing directory nor a key of proper length')
                self.token = tokenString

            return newIndex, None
        except Exception as err:
            return iterIndex, err


class NumberOfRequestsCLArg(CommandLineArgParser):
    """ Command line switch parser that reads number of pull requests for api request """

    CLI_TEXT = f'-{(KEY_NAME := "pr_n")}'
    TYPE = 'prn_a'

    def __init__(self):
        super().__init__(NumberOfRequestsCLArg.KEY_NAME, NumberOfRequestsCLArg.CLI_TEXT,
                         NumberOfRequestsCLArg.TYPE)
        self.count = 10

    def apply_arg(self, targetKey: str, targetDict: dict):
        targetDict[targetKey] = self.count

    def read_args(self, iterIndex: int, argv: Tuple[str]) -> (int, Exception):
        try:
            self.validate_cmd_text(argv[iterIndex])
            newIndex, gatheredArgs = CommandLineArgParser._read_args_until_next_command(iterIndex + 1, argv, self.cli_text, 1)

            nValue = int(gatheredArgs[0])
            if nValue > 0:
                self.count = nValue
                return newIndex, None
            else:
                return iterIndex, RuntimeError(f'Invalid pull requests count value: {nValue}')
        except Exception as err:
            return iterIndex, err


@enum_with_checks
class FileMode(IntEnum):
    """
    Enum for possible file modes:
    * placeholder - used as dummy initializer
    * single - used to tell formatter to output to single file, named by user(name can also come from default value)
    * single_sheets - same as single, but each repository is written to separate sheet
    * split_auto - used to tell formatter to output to multiple files, and name them automatically
    """

    placeholder = -1,
    single = 0
    single_sheets = 1,
    split_auto = 2


class FileModeCLArg(CommandLineArgParser):
    """
    Command switch parser that reads file mode and
    possible additional arguments for file modes(filename for example)
    """

    CLI_TEXT = f'-{(KEY_NAME := "file_mode")}'
    TYPE = 'fl_m'

    def __init__(self):
        super().__init__(FileModeCLArg.KEY_NAME, FileModeCLArg.CLI_TEXT,
                         FileModeCLArg.TYPE)
        self.filemode = FileMode.placeholder
        self.args: List[Union[str, FileMode]] = []

    def read_args(self, iterIndex: int, argv: Tuple[str]) -> Tuple[int, Optional[Exception]]:
        try:
            self.validate_cmd_text(argv[iterIndex])

            (newIndex, (filemodeStr, *restArgs)) = \
                CommandLineArgParser._read_args_until_next_command(iterIndex + 1, argv, self.cli_text)
            if not FileMode.has_name(filemodeStr):
                return iterIndex, RuntimeError(f'Unknown file mode: {filemodeStr}')
            else:
                mode = FileMode[filemodeStr]
                if mode == FileMode.single or mode == FileMode.single_sheets:
                    warn_assert(len(restArgs) == 1, lambda: 'More than one filename string was provided, '
                                                            f'n = {len(restArgs)}')
                    self.args = [restArgs[0]]
                elif mode == FileMode.split_auto:
                    warn_assert(len(restArgs) == 0, lambda: 'Number of provided arguments is not zero with '
                                                            f'filemode = split_auto, n = {len(restArgs)}')
                    self.args = []

                self.filemode = mode

            return newIndex, None
        except Exception as error:
            return iterIndex, error

    def apply_arg(self, targetKey: str, targetDict: dict):
        targetDict[targetKey] = [self.filemode] + self.args


class ApiEndpointCLArg(CommandLineArgParser):
    """ Command line switch parser that reads api endpoint string """

    CLI_TEXT = f'-{(KEY_NAME := "api_endpoint")}'
    TYPE = 'api_ep'

    def __init__(self):
        super().__init__(ApiEndpointCLArg.KEY_NAME, ApiEndpointCLArg.CLI_TEXT,
                         ApiEndpointCLArg.TYPE)
        self.filemode = FileMode.placeholder
        self.endpoint = Defines.DEFAULT_API_ENDPOINT

    def read_args(self, iterIndex: int, argv: Tuple[str]) -> Tuple[int, Optional[Exception]]:
        try:
            self.validate_cmd_text(argv[iterIndex])
            newIndex, (endpoint,) = CommandLineArgParser._read_args_until_next_command(iterIndex + 1, argv, self.cli_text, 1)
            self.endpoint = endpoint
            return newIndex, None
        except Exception as error:
            return iterIndex, error

    def apply_arg(self, targetKey: str, targetDict: dict):
        targetDict[targetKey] = self.endpoint
