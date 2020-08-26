import requests
import abc
import copy
from typing import List, TypedDict, FrozenSet, Tuple, Generic, TypeVar
from datetime import datetime
import dateutil.parser
import traceback
import os
import xlsxwriter


####################################
### Utility types and functions
####################################


_DEFAULT_TOKEN = "0000000000000000000000000000000000000000"

class Defines:
    API_ENDPOINT = "https://api.github.com/graphql"
    DEFAULT_TOKEN = _DEFAULT_TOKEN
    TOKEN_LENGTH = len(_DEFAULT_TOKEN)
    TOKEN_ENCODING = 'utf-8'
    DEFAULT_OUTPUT_EXCEL = './pr_info.xlsx'
    DEFAULT_DATE_STR = "0001-01-01T00:00:00Z"
    XLSX_DATE_TIME_FORMAT = 'hh:mm dd/mm/yy'
    PR_MERGED_STATE = 'MERGED'
    PR_APPROVED_STATE = 'APPROVED'
    PR_CLOSED_STATE = 'CLOSED'


def parse_isodate(iso8601date: str) -> Tuple[datetime, Exception]:
    try:
        return dateutil.parser.isoparse(iso8601date), None
    except Exception as err:
        return dateutil.parser.isoparse(Defines.DEFAULT_DATE_STR), err


def date_to_ddmmyy_hhmm(date : datetime) -> str:
    return f'{date.day}/{date.month}/{date.year} {date.hour}:{date.minute}'


def run_query(query : str, variables: str, headers : dict) -> dict:
    """ Sends http request to github graphql api """

    requestJson = { 'query': query }
    if variables != None:
        requestJson['variables'] = variables

    request = requests.post(Defines.API_ENDPOINT, json=requestJson, headers=headers)
    if request.status_code == 200:
        jsonResult = request.json()
        if 'errors' in jsonResult:
            raise RuntimeError(f'Query returned errors: {jsonResult}')
        return jsonResult
    else:
        raise RuntimeError(f'Query failed to run by returning code of "{request.status_code}", reason: "{request.reason}", query was: "{query}"') 


####################################
### Json dictionary types
####################################


class ActorJson(TypedDict):
    login: str


NodeType = TypeVar('NodeType')


class GraphQlNodeJson(Generic[NodeType]):
    node: NodeType


class GraphQlListJson(Generic[NodeType]):
    totalCount: int
    edges: List[GraphQlNodeJson[NodeType]]


class _PullRequestJson_Review(TypedDict):
    author: ActorJson
    createdAt: str


class PullRequestJson(TypedDict):
    author: ActorJson
    createdAt: str
    state: str
    mergedAt: str
    mergedBy: ActorJson
    approvedReviews: GraphQlListJson[_PullRequestJson_Review]
    closed: bool
    title: str


class _PullRequestJson_Repository(TypedDict):
    pullRequests: GraphQlListJson[PullRequestJson]


class PullRequestQueryJson(TypedDict):
    repositoryOwner: _PullRequestJson_Repository


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
        self.createdAt: datetime    = parse_isodate(prJson['createdAt'])[0]
        self.title: str             = prJson['title']
        self.closed: bool           = prJson['closed']
        if prJson['approvedReviews']['totalCount'] == 0:
            self.firstReview        = None
            self.state: str         = prJson['state']
        else:
            reviewNode = prJson['approvedReviews']['edges'][0]['node']

            self.firstReview: PullRequest.Review = PullRequest.Review(reviewNode['author']['login'], parse_isodate(reviewNode['createdAt'])[0])
            if prJson['state'] != Defines.PR_MERGED_STATE:
                self.state: str     = Defines.PR_APPROVED_STATE
            else:
                self.state: str     = prJson['state']

        if prJson['mergedAt'] == None:
            self.mergedAt: datetime = None
            self.mergedBy: str = None
        else:
            self.mergedAt: datetime = parse_isodate(prJson['mergedAt'])[0]
            self.mergedBy: str = prJson['mergedBy']['login']

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
                if result != None:
                    outputList.append(result)
            except Exception as err:
                traceback.print_exc()
                print(err)
            
        return outputList


####################################
### PromptArg classes - handlers of proccess arguments
####################################


class PromptArg(abc.ABC):
    def __init__(self, key_name: str, type: str):
        self.key_name = key_name
        self.cmd_text = f'-{key_name}'
        self.type = type

    @abc.abstractmethod
    def apply_arg(self, targetKey: str, targetDict: dict):
        pass
        
    def read_args(self, iterIndex : int, args : Tuple[str]) -> (int, Exception):
        pass

_RepoPromptArg_KEY_NAME = 'repos'
class RepoPromptArg(PromptArg):
    KEY_NAME = _RepoPromptArg_KEY_NAME
    CMD_TEXT = f'-{_RepoPromptArg_KEY_NAME}'
    TYPE = 'r_a'

    def __init__(self):
        super().__init__(RepoPromptArg.KEY_NAME, RepoPromptArg.TYPE)
        self.repoList: List[str] = []
        self.type = RepoPromptArg.TYPE

    def apply_arg(self, targetKey: str, targetDict: dict):
        targetDict[targetKey] = targetDict[targetKey] + copy.copy(self.repoList)

    def read_args(self, iterIndex : int, args : Tuple[str]) -> (int, Exception):
        err: Exception = None
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


_ApiTokenPromptArg_KEY_NAME = 'api_token'
class ApiTokenPromptArg(PromptArg):
    KEY_NAME = _ApiTokenPromptArg_KEY_NAME
    CMD_TEXT = f'-{_ApiTokenPromptArg_KEY_NAME}'
    TYPE = 'at_a'

    def __init__(self):
        super().__init__(ApiTokenPromptArg.KEY_NAME, ApiTokenPromptArg.TYPE)
        self.token = Defines.DEFAULT_TOKEN
        self.type = ApiTokenPromptArg.TYPE

    def apply_arg(self, targetKey: str, targetDict: dict):
        targetDict[targetKey] = self.token

    def read_args(self, iterIndex : int, args : List[str]) -> (int, Exception):
        newIndex = iterIndex
        try:
            if self.cmd_text != args[newIndex]:
                return newIndex, RuntimeError(f'Given argument does not match cmd_text: "{self.cmd_text}" vs "{args[newIndex]}"')
        
            newIndex = newIndex + 1
            if not isinstance(args[newIndex], str):
                return newIndex, RuntimeError(f'Invalid token argument: "{args[newIndex]}"')

            tokenString = args[newIndex]
            if os.path.exists(tokenString):
                with open(tokenString, 'rb') as tokenFile:
                    self.token = str(tokenFile.read(Defines.TOKEN_LENGTH), 'utf-8')
            else:
                if len(tokenString) != Defines.TOKEN_LENGTH:
                    raise RuntimeError(f'Invalid token argument, it\'s not an existing directory nor a key of proper length')
                self.token = tokenString

            return newIndex, None
        except Exception as err:
            return iterIndex, err


_NumberOfRequestsPromptArg_KEY_NAME = 'pr_n'
class NumberOfRequestsPromptArg(PromptArg):
    KEY_NAME = _NumberOfRequestsPromptArg_KEY_NAME
    CMD_TEXT = f'-{_NumberOfRequestsPromptArg_KEY_NAME}'
    TYPE = 'pr_n'

    def __init__(self):
        super().__init__(NumberOfRequestsPromptArg.KEY_NAME, NumberOfRequestsPromptArg.TYPE)
        self.count = 10

    def apply_arg(self, targetKey: str, targetDict: dict):
        targetDict[targetKey] = self.count

    def read_args(self, iterIndex: int, argv: List[str]) -> (int, Exception):
        if self.cmd_text != argv[iterIndex]:
            return iterIndex, RuntimeError(f'Given argument does not match key_name: "{self.key_name}" vs "{argv[iterIndex]}"')

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


####################################
### Main functionality
####################################


class Defines_CMD:
    SWITCHES = {
        RepoPromptArg.CMD_TEXT: RepoPromptArg(),
        ApiTokenPromptArg.CMD_TEXT: ApiTokenPromptArg(),
        NumberOfRequestsPromptArg.CMD_TEXT: NumberOfRequestsPromptArg()
    }

class PullRequestQueryInputDict(TypedDict):
    repo_ls: List[str]
    api_token: str
    pr_n: int
    out_filename: str


def generate_excel(argv: Tuple[str]):
    inputDict: PullRequestQueryInputDict = {
        RepoPromptArg.CMD_TEXT: [],
        ApiTokenPromptArg.CMD_TEXT: Defines.DEFAULT_TOKEN,
        NumberOfRequestsPromptArg.CMD_TEXT: 10,
        'filename': Defines.DEFAULT_OUTPUT_EXCEL
    }
    iterIndex = 1
    argvCount = len(argv)

    usedSwitches = set()

    while iterIndex < argvCount:
        err : Exception        = None
        cmdSwitch : PromptArg  = None
        cmdKey: str            = argv[iterIndex]

        if cmdKey not in Defines_CMD.SWITCHES:
            raise RuntimeError(f'Unknown switch: "{cmdKey}"')
        elif cmdKey in usedSwitches:
            raise RuntimeError(f'Duplicate switch: "{cmdKey}"')
        else:
            cmdSwitch = Defines_CMD.SWITCHES[cmdKey]
            iterIndex, err = cmdSwitch.read_args(iterIndex, argv)
            if err != None:
                raise err 
            cmdSwitch.apply_arg(cmdKey, inputDict)
        
        iterIndex = iterIndex + 1
        usedSwitches.add(cmdKey)

    headers = { 'Authorization' : f'token {inputDict[ApiTokenPromptArg.CMD_TEXT]}' }

    with PRExcelWriter(inputDict['filename']) as excelWriter:
        for repoPath in inputDict[RepoPromptArg.CMD_TEXT]:            
            resultJson: PullRequestQueryJson  = fetch_json(repoPath, inputDict, headers)
            resultList: List[PullRequest]     = PullRequest.create_list_of_approved_or_merged(resultJson)

            print(f'\n-- Writing pr\'s for repo: [ {repoPath} ]--', end='')
            excelWriter.add_new_repo(repoPath, len(resultList))
            print(f'\n-- Number of approved|merged pull requests: [ {len(resultList)} ]--')
            for pr in resultList:
                print(f'\n-- Writing new approved pull request: [ {pr.title} ] --')
                excelWriter.add_new_pullrequest(pr)


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

def fetch_json(repoPath: str, inputDict: PullRequestQueryInputDict, headers: dict) -> PullRequestQueryJson:
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

_empty_excel_cell = 'N/A'
class PRExcelWriter:
    COLUMN_LABELS = {
        'author' : 0,
        'created_at' : 1,
        'state' : 2,
        'first_approved_by' : 3,
        'first_approved_review_created_at' : 4,
        'merged_by' : 5,
        'merged_at' : 6,
        'is_closed' : 7,
        'title' : 8
    }
    
    def __init__(self, filename: str):
        self.excelWb = xlsxwriter.Workbook(filename=filename)
        self.excelWorkSheet = self.excelWb.add_worksheet('Approved pull requests summary') 
        self.line = 0 

        self.excelWorkSheet.set_column(0, 0, 30)
        self.date_format = self.excelWb.add_format({'num_format': Defines.XLSX_DATE_TIME_FORMAT})
        self.excelWorkSheet.remove_timezone = True
        for _, v in PRExcelWriter.COLUMN_LABELS.items():
            self.excelWorkSheet.set_column(0, v, 20)

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception_value, tracebackObj):
        if exception_type != None:
            print(f'PRWriterError: {exception_value}')
            #print(tracebackObj.tb_frame.stack)
        self.excelWb.close()
        return self

    def add_new_repo(self, repo_path: str, nOfApprovedPrs: int):
        if self.line != 0:
            self.line = self.line + 2

        if self.excelWorkSheet.write(self.line, 0, repo_path) == -1:
            raise RuntimeError(f'Could not add repo_path: "{repo_path}", line: {self.line}')

        if nOfApprovedPrs > 0:
            self.line = self.line + 1
            for k, v in PRExcelWriter.COLUMN_LABELS.items():
                if self.excelWorkSheet.write(self.line, v, k):
                    raise RuntimeError(f'Could not add column: "{k}", line: {self.line}')
        else:
            if self.excelWorkSheet.write_string(self.line, 1, 'no approved pr\'s'):
                raise RuntimeError(f'Could not add column: "{1}", line: {self.line}')

        self.line = self.line + 1 

    def add_new_pullrequest(self, pr: PullRequest):
        ws = self.excelWorkSheet
        cl = PRExcelWriter.COLUMN_LABELS

        # write info about author, date and state
        print('writing author: ', 
            end=f"{  ws.write(self.line, cl['author'], pr.author)   }\n")
        print('writing pr date: ', 
            end=f"{ ws.write_datetime(self.line, cl['created_at'], pr.createdAt, self.date_format)   }\n")
        print('writing state: ', 
            end=f"{     ws.write_string(self.line, cl['state'], pr.state)   }\n")

        # write first review information
        if pr.firstReview != None:
            print('writing first approved review date: ', 
                end=f"{ ws.write_string(self.line, cl['first_approved_by'], pr.firstReview.author) }\n")
            print('writing first approved review date: ', 
                end=f"{ ws.write_datetime(self.line, cl['first_approved_review_created_at'], pr.firstReview.createdAt, self.date_format) }\n")
        else:
            print('writing NULL first approved review date: ', 
                end=f"{ ws.write_string(self.line, cl['first_approved_by'], _empty_excel_cell) }\n")
            print('writing NULL first approved review date: ', 
                end=f"{ ws.write_string(self.line, cl['first_approved_review_created_at'], _empty_excel_cell) }\n")

        # write info about merging
        if pr.mergedAt != None:
            print('writing merge author: ', 
                end=f"{ ws.write_string(self.line, cl['merged_by'], pr.mergedBy) }\n")
            print('writing merge date: ', 
                end=f"{ ws.write_datetime(self.line, cl['merged_at'], pr.mergedAt, self.date_format) }\n")
        else:
            print('writing NULL merge author: ', 
                end=f"{ ws.write_string(self.line, cl['merged_by'], _empty_excel_cell) }\n")
            print('writing NULL merge date: ', 
                end=f"{ ws.write_string(self.line, cl['merged_at'], _empty_excel_cell) }\n")

        # write boolean=pr is closed and write pr title
        print('writing if pr is closed: ',
            end=f"{ ws.write_boolean(self.line, cl['is_closed'], pr.closed) }\n")
        print('writing pr title: ',
            end=f"{ ws.write_string(self.line, cl['title'], pr.title) }\n")

        self.line = self.line + 1
