from pr_info_gatherer.cli_args import RepoCLArg, ApiTokenCLArg, NumberOfRequestsCLArg, FileModeCLArg, \
    ApiEndpointCLArg, CommandLineArgParser, FileMode
from pr_info_gatherer.const_defines import Defines
from typing import Tuple


class Defines_CLI:
    """
    Defines for command line parsers:
        * SWITCHES - dictionary of all command line arguments parsers, key = parser's cmd_text
    """

    SWITCHES = {
        RepoCLArg.CLI_TEXT: RepoCLArg(),
        ApiTokenCLArg.CLI_TEXT: ApiTokenCLArg(),
        NumberOfRequestsCLArg.CLI_TEXT: NumberOfRequestsCLArg(),
        FileModeCLArg.CLI_TEXT: FileModeCLArg(),
        ApiEndpointCLArg.CLI_TEXT: ApiEndpointCLArg()
    }


def parse_cli_args(argv: Tuple[str]):
    """ Parses string cli arguments into a dictionary of transformed values """

    inputDict = {
        RepoCLArg.CLI_TEXT: [],
        ApiTokenCLArg.CLI_TEXT: Defines.DEFAULT_TOKEN,
        NumberOfRequestsCLArg.CLI_TEXT: 10,
        FileModeCLArg.CLI_TEXT: [FileMode.single_sheets],
        ApiEndpointCLArg.CLI_TEXT: Defines.DEFAULT_API_ENDPOINT
    }
    iterIndex = 1
    argvCount = len(argv)
    usedSwitches = set()

    while iterIndex < argvCount:
        cliSwitch: CommandLineArgParser
        cliKey: str = argv[iterIndex]

        if cliKey not in Defines_CLI.SWITCHES:
            raise RuntimeError(f'Unknown switch: "{cliKey}"')
        elif cliKey in usedSwitches:
            raise RuntimeError(f'Duplicate switch: "{cliKey}"')
        else:
            cliSwitch = Defines_CLI.SWITCHES[cliKey]
            iterIndex, err = cliSwitch.read_args(iterIndex, argv)
            if err is not None:
                raise err
            cliSwitch.apply_arg(cliKey, inputDict)

        iterIndex += 1
        usedSwitches.add(cliKey)

    return inputDict
