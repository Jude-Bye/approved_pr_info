from pr_info_gatherer.const_defines import Defines
from pr_info_gatherer.common import parse_iso_date, run_query
from pr_info_gatherer.cli_args import NumberOfRequestsCLArg, ApiEndpointCLArg
from typing import List, TypedDict, Generic, TypeVar, Optional
from datetime import datetime
import traceback

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
    """ Class that is used to parse pull requests json into python object """

    class Review:
        def __init__(self, author: str, createdAt: datetime, prCreatedAt: datetime):
            self.author = author
            self.createdAt = createdAt
            self.sincePRCreated = self.createdAt - prCreatedAt

    class MergeInfo:
        def __init__(self, byWhom: str, mergedAt: datetime, prCreatedAt: datetime):
            self.byWhom = byWhom
            self.mergedAt = mergedAt
            self.sincePRCreated = self.mergedAt - prCreatedAt

    def __init__(self, prJson: PullRequestJson):
        self.author: str            = prJson['author']['login']
        self.createdAt: datetime    = parse_iso_date(prJson['createdAt'])[0]
        self.title: str             = prJson['title']
        self.closed: bool           = prJson['closed']
        self.state: List[str]       = [prJson['state']]
        self.firstReview: Optional[PullRequest.Review]
        self.mergeInfo: Optional[PullRequest.MergeInfo]
        self.from_approve_to_merge: Optional[datetime]

        if prJson['approvedReviews']['totalCount'] == 0:
            self.firstReview        = None
        else:
            reviewNode = prJson['approvedReviews']['edges'][0]['node']

            self.firstReview: PullRequest.Review = PullRequest.Review(reviewNode['author']['login'],
                                                                      parse_iso_date(reviewNode['createdAt'])[0],
                                                                      self.createdAt)
            self.state.append(Defines.PR_APPROVED_STATE)

        if prJson['mergedAt'] is None:
            self.mergeInfo = None
        else:
            self.mergeInfo = PullRequest.MergeInfo(prJson['mergedBy']['login'],
                                                   parse_iso_date(prJson['mergedAt'])[0],
                                                   self.createdAt)

        if self.firstReview is not None and self.mergeInfo is not None:
            self.from_approve_to_merge = self.mergeInfo.mergedAt - self.firstReview.createdAt
        else:
            self.from_approve_to_merge = None

        self.title = prJson['title']

    @staticmethod
    def create_if_approved_or_merged(prJson: PullRequestJson):
        if prJson['state'] == Defines.PR_MERGED_STATE or prJson['approvedReviews']['totalCount'] > 0:
            return PullRequest(prJson)
        else:
            return None

    @staticmethod
    def create_list_of_approved_or_merged(queryJson: PullRequestQueryJson):
        prJsonList: GraphQlListJson[PullRequestJson] = \
            queryJson['data']['repositoryOwner']['repository']['pullRequests']
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
            approvedReviews: reviews(last: 1, states: [APPROVED]) {
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
    "pr_n": {inputDict[NumberOfRequestsCLArg.CLI_TEXT]}
}}
"""
    print(f'Variables for next query: {variables}')
    try:
        print('-- Sending api request... --')
        result = run_query(_fetch_json_query, variables, headers, inputDict[ApiEndpointCLArg.CLI_TEXT])
        print('-- Success --')
        return result
    except Exception as err:
        print('-- http request function has thrown an error! --')
        raise err
