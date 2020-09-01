from pr_info_gatherer.const_defines import Defines
from typing import Tuple, Optional, Type, Callable
from datetime import datetime
from enum import IntEnum
import warnings
import requests
import dateutil.parser

####################################
### Utility types and functions
####################################


def parse_iso_date(iso8601date: str) -> Tuple[datetime, Optional[Exception]]:
    """ Wrapper for dateutils isoparse that returns possible error as a part of tuple """
    try:
        return dateutil.parser.isoparse(iso8601date), None
    except Exception as err:
        return dateutil.parser.isoparse(Defines.DEFAULT_DATE_STR), err


def run_query(query: str, variables: Optional[str], headers: dict, endpoint: str) -> dict:
    """ Sends http request to github graphql api """
    requestJson: dict = {'query': query}
    if variables is not None:
        requestJson['variables'] = variables

    request = requests.post(endpoint, json=requestJson, headers=headers)
    if request.status_code == 200:
        jsonResult = request.json()
        if 'errors' in jsonResult:
            raise RuntimeError(f'Query returned errors: {jsonResult}')
        return jsonResult
    else:
        if request.status_code == 401:
            raise UserInputError('Invalid token was provided')
        else:
            raise RuntimeError(f'Query failed to run by returning code of "{request.status_code}"'
                           f', reason: "{request.reason}", query was: "{query}"')


def enum_with_checks(targetEnum: Type[IntEnum]):
    """
    Decorator that adds to IntEnum class static methods:
        * has_value - returns true if enum has given int value
        * has_name  - returns true if enum has member with given name
    """

    values_set = set(item.value for item in targetEnum)
    targetEnum.has_value = staticmethod(lambda x: x in values_set)
    targetEnum.has_name = staticmethod(lambda x: x in targetEnum.__members__)

    return targetEnum


def warn_assert(value: bool, lazyMessage: Callable[[], str]):
    """ Prints warning if given value is false """
    if not value:
        warnings.warn(lazyMessage())

class UserInputError(Exception):
    pass

