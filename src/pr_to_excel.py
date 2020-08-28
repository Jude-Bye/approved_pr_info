import requests
import abc
import copy
from typing import List, TypedDict, Tuple, Generic, TypeVar, Optional, Type
from types import TracebackType
from datetime import datetime
import dateutil.parser
import traceback
import os
import xlsxwriter


####################################
### Utility types and functions
####################################


class Defines:
    """ 'Constant' variables used in this file """
    API_ENDPOINT = "https://api.github.com/graphql"
    TOKEN_LENGTH = len(
        (DEFAULT_TOKEN := "0000000000000000000000000000000000000000"))
    TOKEN_FILE_ENCODING = 'utf-8'
    DEFAULT_OUTPUT_EXCEL = './pr_info.xlsx'
    DEFAULT_DATE_STR = "0001-01-01T00:00:00Z"

    XLSX_DATE_TIME_FORMAT = 'hh:mm dd/mm/yy'
    XLSX_EMPTY_CELL = 'N/A'
    XLSX_COLUMN_WIDTH = 20

    PR_MERGED_STATE = 'MERGED'
    PR_APPROVED_STATE = 'APPROVED'
    PR_CLOSED_STATE = 'CLOSED'


def parse_iso_date(iso8601date: str) -> Tuple[datetime, Optional[Exception]]:
    try:
        return dateutil.parser.isoparse(iso8601date), None
    except Exception as err:
        return dateutil.parser.isoparse(Defines.DEFAULT_DATE_STR), err


def run_query(query: str, variables: Optional[str], headers: dict) -> dict:
    """ Sends http request to github graphql api """

    requestJson: dict = {'query': query}
    if variables is not None:
        requestJson['variables'] = variables

    request = requests.post(Defines.API_ENDPOINT, json=requestJson, headers=headers)
    if request.status_code == 200:
        jsonResult = request.json()
        if 'errors' in jsonResult:
            raise RuntimeError(f'Query returned errors: {jsonResult}')
        return jsonResult
    else:
        raise RuntimeError(f'Query failed to run by returning code of "{request.status_code}"'
                           f', reason: "{request.reason}", query was: "{query}"')


####################################
### Json dictionary types
####################################


class ActorJson(TypedDict):
    login: str


NodeType = TypeVar('NodeType')


class GraphQlNodeJson(Generic[NodeType]):  # , TypedDict):
    node: NodeType


class GraphQlListJson(Generic[NodeType]):  # , TypedDict):
    totalCount: int
    edges: List[GraphQlNodeJson[NodeType]]


class PullRequestJson_Review(TypedDict):
    author: ActorJson
    createdAt: str


class PullRequestJson(TypedDict):
    author: ActorJson
    createdAt: str
    state: str
    mergedAt: Optional[str]
    mergedBy: Optional[ActorJson]
    approvedReviews: GraphQlListJson[PullRequestJson_Review]
    closed: bool
    title: str


class PullRequestJson_PullRequests(TypedDict):
    pullRequests: GraphQlListJson[PullRequestJson]


class PullRequestJson_Repository(TypedDict):
    repository: PullRequestJson_PullRequests


class PullRequestJson_RepositoryOwner(TypedDict):
    repositoryOwner: PullRequestJson_Repository


class PullRequestQueryJson(TypedDict):
    data: PullRequestJson_RepositoryOwner


####################################
### PullRequest class
####################################


class PullRequest:

    class Review:
        def __init__(self, author: str, createdAt: datetime):
            self.author = author
            self.createdAt = createdAt

    def __init__(self, prJson: PullRequestJson):
        self.author: str            = prJson['author']['login']
        self.createdAt: datetime    = parse_iso_date(prJson['createdAt'])[0]
        self.title: str             = prJson['title']
        self.closed: bool           = prJson['closed']
        self.state: str
        self.firstReview: Optional[PullRequest.Review]
        self.mergedAt: Optional[datetime]
        self.mergedBy: Optional[ActorJson]

        if prJson['approvedReviews']['totalCount'] == 0:
            self.firstReview        = None
            self.state              = prJson['state']
        else:
            reviewNode = prJson['approvedReviews']['edges'][0]['node']

            self.firstReview: PullRequest.Review = PullRequest.Review(reviewNode['author']['login'],
                                                                      parse_iso_date(reviewNode['createdAt'])[0])
            if prJson['state'] != Defines.PR_MERGED_STATE:
                self.state          = Defines.PR_APPROVED_STATE
            else:
                self.state          = prJson['state']

        if prJson['mergedAt'] is None:
            self.mergedAt = None
            self.mergedBy = None
        else:
            self.mergedAt = parse_iso_date(prJson['mergedAt'])[0]
            self.mergedBy = prJson['mergedBy']['login']

        self.title = prJson['title']
 
    @staticmethod
    def create_if_approved_or_merged(prJson: PullRequestJson):
        if prJson['state'] == Defines.PR_MERGED_STATE or prJson['approvedReviews']['totalCount'] > 0:
            return PullRequest(prJson)
        else:
            return None

    @staticmethod
    def create_list_of_approved_or_merged(queryJson: PullRequestQueryJson):
        prJsonList: GraphQlListJson[PullRequestJson] = queryJson['data']['repositoryOwner']['repository']['pullRequests']
        outputList: List[PullRequest] = []
        for prJson in prJsonList['edges']:
            try:
                result = PullRequest.create_if_approved_or_merged(prJson['node'])
                if result is not None:
                    outputList.append(result)
            except Exception as err:
                traceback.print_exc()
                print(err)
            
        return outputList


####################################
### PromptArg classes - handlers of process arguments
####################################


class PromptArg(abc.ABC):
    def __init__(self, key_name: str, cmd_text: str, p_type: str):
        self.key_name: str = key_name
        self.cmd_text: str = cmd_text
        self.type: str     = p_type

    @abc.abstractmethod
    def apply_arg(self, targetKey: str, targetDict: dict):
        pass
        
    def read_args(self, iterIndex: int, args: Tuple[str]) -> Tuple[int, Optional[Exception]]:
        pass


class RepoPromptArg(PromptArg):
    CMD_TEXT = f'-{(  KEY_NAME := "repos"  )}'
    TYPE = 'r_a'

    def __init__(self):
        super().__init__(RepoPromptArg.KEY_NAME, RepoPromptArg.CMD_TEXT, RepoPromptArg.TYPE)
        self.repoList: List[str] = []
        self.type = RepoPromptArg.TYPE

    def apply_arg(self, targetKey: str, targetDict: dict):
        targetDict[targetKey] = targetDict[targetKey] + copy.copy(self.repoList)

    def read_args(self, iterIndex: int, args: Tuple[str]) -> Tuple[int, Optional[Exception]]:
        err: Optional[Exception] = None
        try:
            lastIndex = len(args) - 1
            oldCount = len(self.repoList)
            newIndex = iterIndex + 1
            
            while newIndex < lastIndex and args[newIndex][0] != '-':
                self.repoList.append(args[newIndex])
                newIndex = newIndex + 1
            else:
                newIndex = newIndex - 1 

            if len(self.repoList) == oldCount:
                err = RuntimeError('No new repositories were found')
        except Exception as exc:
            traceback.print_exc()
            err = exc
            newIndex = iterIndex
       
        return newIndex, err


class ApiTokenPromptArg(PromptArg):
    CMD_TEXT = f'-{(  KEY_NAME := "api_token"  )}'
    TYPE = 'at_a'

    def __init__(self):
        super().__init__(ApiTokenPromptArg.KEY_NAME, ApiTokenPromptArg.CMD_TEXT, ApiTokenPromptArg.TYPE)
        self.token = Defines.DEFAULT_TOKEN
        self.type = ApiTokenPromptArg.TYPE

    def apply_arg(self, targetKey: str, targetDict: dict):
        targetDict[targetKey] = self.token

    def read_args(self, iterIndex: int, args: List[str]) -> Tuple[int, Optional[Exception]]:
        newIndex = iterIndex
        err: Optional[Exception]
        try:
            if self.cmd_text != args[newIndex]:
                return newIndex, RuntimeError('Given argument does not match cmd_text: '
                                              f'"{self.cmd_text}" vs "{args[newIndex]}"')
        
            newIndex = newIndex + 1
            if not isinstance(args[newIndex], str):
                return newIndex, RuntimeError(f'Invalid token argument: "{args[newIndex]}"')

            tokenString = args[newIndex]
            if os.path.exists(tokenString):
                with open(tokenString, 'rb') as tokenFile:
                    self.token = str(tokenFile.read(Defines.TOKEN_LENGTH), Defines.TOKEN_FILE_ENCODING)
            else:
                if len(tokenString) != Defines.TOKEN_LENGTH:
                    raise RuntimeError(f'Token argument, is not an existing directory nor a key of proper length')
                self.token = tokenString

            return newIndex, None
        except Exception as error:
            traceback.print_exc()
            err = error

        return iterIndex, err


class NumberOfRequestsPromptArg(PromptArg):
    CMD_TEXT = f'-{(  KEY_NAME := "pr_n"  )}'
    TYPE = 'prn_a'

    def __init__(self):
        super().__init__(NumberOfRequestsPromptArg.KEY_NAME, NumberOfRequestsPromptArg.CMD_TEXT,
                         NumberOfRequestsPromptArg.TYPE)
        self.count = 10

    def apply_arg(self, targetKey: str, targetDict: dict):
        targetDict[targetKey] = self.count

    def read_args(self, iterIndex: int, argv: List[str]) -> (int, Exception):
        if self.cmd_text != argv[iterIndex]:
            return iterIndex, \
                   RuntimeError(f'Given argument does not match key_name: "{self.key_name}" vs "{argv[iterIndex]}"')

        newIndex = iterIndex + 1
        try:
            nValue = int(argv[newIndex])
            if nValue > 0:
                self.count = nValue
                return newIndex, None
            else:
                return iterIndex, RuntimeError(f'Invalid pull requests count value: {nValue}')
        except Exception as err:
            traceback.print_exc()
            return iterIndex, err


class OutFilenamePromptArg(PromptArg, abc.ABC):
    CMD_TEXT = f'-{(  KEY_NAME := "out_filename"  )}'


####################################
### Main functionality
####################################


class Defines_CMD:
    SWITCHES = {
        RepoPromptArg.CMD_TEXT: RepoPromptArg(),
        ApiTokenPromptArg.CMD_TEXT: ApiTokenPromptArg(),
        NumberOfRequestsPromptArg.CMD_TEXT: NumberOfRequestsPromptArg()
    }


def generate_excel(argv: Tuple[str]):
    inputDict = {
        RepoPromptArg.CMD_TEXT: [],
        ApiTokenPromptArg.CMD_TEXT: Defines.DEFAULT_TOKEN,
        NumberOfRequestsPromptArg.CMD_TEXT: 10,
        OutFilenamePromptArg.CMD_TEXT: Defines.DEFAULT_OUTPUT_EXCEL
    }
    iterIndex = 1
    argvCount = len(argv)
    usedSwitches = set()

    while iterIndex < argvCount:
        cmdSwitch: PromptArg
        cmdKey: str               = argv[iterIndex]

        if cmdKey not in Defines_CMD.SWITCHES:
            raise RuntimeError(f'Unknown switch: "{cmdKey}"')
        elif cmdKey in usedSwitches:
            raise RuntimeError(f'Duplicate switch: "{cmdKey}"')
        else:
            cmdSwitch = Defines_CMD.SWITCHES[cmdKey]
            iterIndex, err = cmdSwitch.read_args(iterIndex, argv)
            if err is not None:
                raise err 
            cmdSwitch.apply_arg(cmdKey, inputDict)
        
        iterIndex = iterIndex + 1
        usedSwitches.add(cmdKey)

    headers = {'Authorization': f'token {inputDict[ApiTokenPromptArg.CMD_TEXT]}'}

    with PRExcelWriter(inputDict[OutFilenamePromptArg.CMD_TEXT]) as excelWriter:
        for repoPath in inputDict[RepoPromptArg.CMD_TEXT]:            
            resultJson: PullRequestQueryJson  = fetch_json(repoPath, inputDict, headers)
            resultList: List[PullRequest]     = PullRequest.create_list_of_approved_or_merged(resultJson)

            print(f'\n-- Writing pr\'s for repo: [ {repoPath} ]--', end='')
            excelWriter.add_new_repo(repoPath, len(resultList))
            print(f'\n-- Number of merged|approved pull requests: [ {len(resultList)} ]--')
            for pr in resultList:
                print(f'\n-- Writing new merged|approved pull request: [ {pr.title} ] --')
                excelWriter.add_new_pull_request(pr)


_fetch_json_query = """
query(
    $repoOwner: String!, 
    $repoName: String!,
    $pr_n: Int!
    ) {
  repositoryOwner(login: $repoOwner) {
    repository(name: $repoName) {
      pullRequests(first: $pr_n, states: [OPEN, CLOSED, MERGED], orderBy: { field: CREATED_AT, direction: DESC }) {
        totalCount
        edges {
          node {
            createdAt
            title
            author {
              login
            }
            closed
            closedAt
            mergedBy {
              login
            }
            mergedAt
            state
            approvedReviews: reviews(last: 100, states: [APPROVED]) {
              totalCount
              edges {
                node {
                  author {
                    login
                  }
                  createdAt
                }
              }
            }
          }
        }
      }
    }
  }
}"""


def fetch_json(repoPath: str, inputDict: dict, headers: dict) -> PullRequestQueryJson:
    repo_owner, repo_name = repoPath.split('/')

    variables = f"""{{
    "repoOwner": "{repo_owner}",
    "repoName": "{repo_name}",
    "pr_n": {inputDict[NumberOfRequestsPromptArg.CMD_TEXT]}
}}
"""
    print(f'Variables for next query: {variables}')
    try:
        print('-- Sending api request... --')
        result = run_query(_fetch_json_query, variables, headers)
        print('-- Success --')
        return result
    except Exception as err:
        print('-- http request function has thrown an error! --')
        raise err
    

####################################
### Excel writer class
####################################


class PRExcelWriter:
    COLUMN_LABELS = {
        'author': 0,
        'created_at': 1,
        'state': 2,
        'first_approved_by': 3,
        'first_approved_review_created_at': 4,
        'merged_by': 5,
        'merged_at': 6,
        'is_closed': 7,
        'title': 8
    }
    
    def __init__(self, filename: str):
        self.__excelWb = xlsxwriter.Workbook(filename=filename)
        self.__excelWorkSheet = self.__excelWb.add_worksheet('Merged|Approved pull requests')
        self.__line = 0

        self.__date_format = self.__excelWb.add_format({'num_format': Defines.XLSX_DATE_TIME_FORMAT})
        self.__excelWorkSheet.remove_timezone = True
        for _, v in PRExcelWriter.COLUMN_LABELS.items():
            self.__excelWorkSheet.set_column(0, v, Defines.XLSX_COLUMN_WIDTH)

    def __enter__(self):
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException],
                 exc_trace: Optional[TracebackType]) -> None:
        if exc_val is not None:
            print(f'PRWriterError: {exc_val}')
            traceback.print_exc()
        self.__excelWb.close()

    def add_new_repo(self, repo_path: str, nOfApprovedPrs: int) -> None:
        if self.__line != 0:
            self.__line = self.__line + 2

        if self.__excelWorkSheet.write(self.__line, 0, repo_path) == -1:
            raise RuntimeError(f'Could not add repo_path: "{repo_path}", line: {self.__line}')

        if nOfApprovedPrs > 0:
            self.__line = self.__line + 1
            for k, v in PRExcelWriter.COLUMN_LABELS.items():
                if self.__excelWorkSheet.write(self.__line, v, k):
                    raise RuntimeError(f'Could not add column: "{k}", line: {self.__line}')
        else:
            if self.__excelWorkSheet.write_string(self.__line, 1, 'no approved pr\'s'):
                raise RuntimeError(f'Could not add column: "{1}", line: {self.__line}')

        self.__line = self.__line + 1

    def add_new_pull_request(self, pr: PullRequest) -> None:
        ws = self.__excelWorkSheet
        cl = PRExcelWriter.COLUMN_LABELS

        # write info about author, date and state
        print('writing author: ',
              end=f"{  ws.write(self.__line, cl['author'], pr.author)   }\n")
        print('writing pr date: ',
              end=f"{ ws.write_datetime(self.__line, cl['created_at'], pr.createdAt, self.__date_format)   }\n")
        print('writing state: ',
              end=f"{     ws.write_string(self.__line, cl['state'], pr.state)   }\n")

        # write first review information
        if pr.firstReview is not None:
            print('writing first approved review date: ',
                  end=f"{ ws.write_string(self.__line, cl['first_approved_by'], pr.firstReview.author) }\n")
            print('writing first approved review date: ',
                  end=f"{ ws.write_datetime(self.__line, cl['first_approved_review_created_at'], pr.firstReview.createdAt, self.__date_format) }\n")
        else:
            print('writing NULL first approved review date: ',
                  end=f"{ ws.write_string(self.__line, cl['first_approved_by'], Defines.XLSX_EMPTY_CELL) }\n")
            print('writing NULL first approved review date: ',
                  end=f"{ ws.write_string(self.__line, cl['first_approved_review_created_at'], Defines.XLSX_EMPTY_CELL) }\n")

        # write info about merging
        if pr.mergedAt is not None:
            print('writing merge author: ',
                  end=f"{ ws.write_string(self.__line, cl['merged_by'], pr.mergedBy) }\n")
            print('writing merge date: ',
                  end=f"{ ws.write_datetime(self.__line, cl['merged_at'], pr.mergedAt, self.__date_format) }\n")
        else:
            print('writing NULL merge author: ',
                  end=f"{ ws.write_string(self.__line, cl['merged_by'], Defines.XLSX_EMPTY_CELL) }\n")
            print('writing NULL merge date: ',
                  end=f"{ ws.write_string(self.__line, cl['merged_at'], Defines.XLSX_EMPTY_CELL) }\n")

        # write boolean=pr is closed and write pr title
        print('writing if pr is closed: ',
              end=f"{ ws.write_boolean(self.__line, cl['is_closed'], pr.closed) }\n")
        print('writing pr title: ',
              end=f"{ ws.write_string(self.__line, cl['title'], pr.title) }\n")

        self.__line = self.__line + 1
