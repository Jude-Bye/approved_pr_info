from typing import List, Tuple, Optional, Type, Callable, Any, Union
from types import TracebackType
import traceback
import xlsxwriter
from enum import IntEnum
from pr_info_gatherer.const_defines import Defines
from pr_info_gatherer.cli_args import RepoCLArg, ApiTokenCLArg, FileModeCLArg, FileMode
from pr_info_gatherer.pull_request import PullRequest, PullRequestQueryJson, fetch_json
from pr_info_gatherer.cli_parser import parse_cli_args


def generate_excel(argv: Tuple[str]):
    inputDict = parse_cli_args(argv)
    headers = {'Authorization': f'token {inputDict[ApiTokenCLArg.CLI_TEXT]}'}

    with PRExcelManager(*inputDict[FileModeCLArg.CLI_TEXT]) as excelFile:
        for repoPath in inputDict[RepoCLArg.CLI_TEXT]:
            resultJson: PullRequestQueryJson  = fetch_json(repoPath, inputDict, headers)
            resultList: List[PullRequest]     = PullRequest.create_list_of_approved_or_merged(resultJson)

            print(f'\n-- Writing pr\'s for repo: [ {repoPath} ]--', end='')
            excelFile.add_new_repo(repoPath, len(resultList))
            print(f'\n-- Number of merged|approved pull requests: [ {len(resultList)} ]--')
            for pr in resultList:
                print(f'\n-- Writing new merged|approved pull request: [ {pr.title} ] --')
                excelFile.add_new_pull_request(pr)


####################################
### Excel writer class
####################################


class PRExcelWriter:
    """ Class that is used to write PullRequest objects into the .xlsx files """

    class Columns(IntEnum):
        author = 0
        created_at = 1
        state = 2

        days_until_first_approved = 3
        days_until_merged = 4
        days_from_approve_to_merge = 5

        first_approved_review_created_at = 6
        first_approved_by = 7

        merged_at = 8
        merged_by = 9

        is_closed = 10
        title = 11

    SMALL_COLUMNS = frozenset([
        'days_until_first_approved',
        'days_until_merged',
        'days_from_approve_to_merge',
        'is_closed'
    ])

    def __init__(self, filename: str):
        self.__excelWb = xlsxwriter.Workbook(filename=filename)
        self.__excelWorkSheet: Optional[xlsxwriter.Workbook.worksheet_class] = None
        self.__line = 0

        self.__date_format = self.__excelWb.add_format({'num_format': Defines.XLSX_DATE_TIME_FORMAT})
        self.__time_elapse_format = self.__excelWb.add_format({'num_format': Defines.XLSX_TIME_ELAPSED_FORMAT})

    @property
    def worksheet(self):
        return self.__excelWorkSheet

    @property
    def line(self):
        return self.__line

    def increment_line(self, by: int = 1) -> int:
        self.__line += by
        return self.__line

    def add_worksheet(self, sheetName: str) -> None:
        self.__excelWorkSheet = self.__excelWb.add_worksheet(sheetName)
        self.__excelWorkSheet.remove_timezone = True
        for col in PRExcelWriter.Columns:
            if col.name in PRExcelWriter.SMALL_COLUMNS:
                widthVal = Defines.XLSX_SMALL_COLUMN_WIDTH
            else:
                widthVal = Defines.XLSX_COLUMN_WIDTH
            self.__excelWorkSheet.set_column(col.value, col.value, widthVal)
        self.__line = 0

    def close(self):
        return self.__excelWb.close()

    def write_pull_request(self, pr: PullRequest) -> None:
        ws = self.__excelWorkSheet
        cl = PRExcelWriter.Columns

        # write info about author, date and state
        print('writing author: ',
              end=f"{ws.write(self.__line, cl.author.value, pr.author)}\n")
        print('writing pr date: ',
              end=f"{ws.write_datetime(self.__line, cl.created_at.value, pr.createdAt, self.__date_format)}\n")
        print('writing state: ',
              end=f"{ws.write_string(self.__line, cl.state.value, ','.join(pr.state))}\n")

        # write first review information
        PRExcelWriter.write_cells_cond(ws, pr.firstReview, self.__line, [
            [cl.first_approved_by, lambda r, c: ws.write_string(r, c, pr.firstReview.author)],
            [cl.first_approved_review_created_at, lambda r, c: ws.write_datetime(r, c, pr.firstReview.createdAt, self.__date_format)],
            [cl.days_until_first_approved, lambda r, c: ws.write_number(r, c, pr.firstReview.sincePRCreated.days)]
        ])
        # write info about merging
        PRExcelWriter.write_cells_cond(ws, pr.mergeInfo, self.__line, [
            [cl.merged_by, lambda r, c: ws.write_string(r, c, pr.mergeInfo.byWhom)],
            [cl.merged_at, lambda r, c: ws.write_datetime(r, c, pr.mergeInfo.mergedAt, self.__date_format)],
            [cl.days_until_merged, lambda r, c: ws.write_number(r, c, pr.mergeInfo.sincePRCreated.days)]
        ])
        # write days from being approved to merged
        PRExcelWriter.write_cells_cond(ws, pr.from_approve_to_merge, self.__line, [
            [cl.days_from_approve_to_merge, lambda r, c: ws.write_number(r, c, pr.from_approve_to_merge.days)]
        ])

        # write boolean=pr is closed and write pr title
        print('writing if pr is closed: ',
              end=f"{ ws.write_boolean(self.__line, cl.is_closed.value, pr.closed) }\n")
        print('writing pr title: ',
              end=f"{ ws.write_string(self.__line, cl.title.value, pr.title) }\n")

        self.increment_line()

    @staticmethod
    def write_cells_cond(ws: xlsxwriter.Workbook.worksheet_class, cond: Optional[Any], row: int,
                         args: List[List[Union[IntEnum, Callable[[int, int], int]]]]):
        if cond is not None:
            for t in args:
                print(f'writing {t[0].name}: ', end=f'{t[1](row, t[0].value)}\n')
        else:
            for t in args:
                print(f'writing NULL {t[0].name}: ', end=f'{ws.write_string(row, t[0].value, Defines.XLSX_EMPTY_CELL)}\n')


class PRExcelManager:
    """ Class that is managing how ExcelWriter class writes PullRequests into the .xlsx files """

    DEFAULT_WORKSHEET_NAME = 'Merged|Approved pull requests'

    def __init__(self, *args):
        self.filemode: FileMode = args[0]
        self.writer: Optional[PRExcelWriter]

        if self.filemode not in FileMode or self.filemode == FileMode.placeholder:
            raise RuntimeError(f'Invalid filemode value was given to PRExcelManager: {self.filemode}')

        if self.filemode == FileMode.split_auto:
            self.writer = None
        else:
            self.writer = PRExcelWriter(args[1])
            if self.filemode == FileMode.single:
                self.writer.add_worksheet(PRExcelManager.DEFAULT_WORKSHEET_NAME)

    def __enter__(self):
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException],
                 exc_trace: Optional[TracebackType]) -> None:
        if exc_val is not None:
            print(f'PRWriterError: {exc_val}')
            traceback.print_exc()
        self.close()

    def close(self):
        if self.writer is not None:
            self.writer.close()

    def add_new_repo(self, repo_path: str, nOfApprovedPrs: int) -> None:
        if self.filemode == FileMode.single:
            # FileMode.single
            if self.writer.line != 0:
                self.writer.increment_line(2)

            if self.writer.worksheet.write(self.writer.line, 0, repo_path) == -1:
                raise RuntimeError(f'Could not add repo_path: "{repo_path}", line: {self.writer.line}')

            self.writer.increment_line()
        elif self.filemode == FileMode.single_sheets:
            # FileMode.single_sheets
            self.writer.add_worksheet(PRExcelManager.repo_path_to_name(repo_path))
        else:
            # FileMode.split_auto
            self.close()
            self.writer = PRExcelWriter(f'{PRExcelManager.repo_path_to_name(repo_path)}{Defines.XLSX_FILE_EXTENSION}')
            self.writer.add_worksheet(PRExcelManager.DEFAULT_WORKSHEET_NAME)

        if nOfApprovedPrs > 0:
            for col in PRExcelWriter.Columns:
                if self.writer.worksheet.write(self.writer.line, col.value, col.name):
                    raise RuntimeError(f'Could not add column: "{col.name}", line: {self.writer.line}')
        else:
            if self.writer.worksheet.write_string(self.writer.line, 1, 'no approved pr\'s'):
                raise RuntimeError(f'Could not add column: "{1}", line: {self.writer.line}')

        self.writer.increment_line()

    def add_new_pull_request(self, pr: PullRequest) -> None:
        self.writer.write_pull_request(pr)

    @staticmethod
    def repo_path_to_name(repoPath: str) -> str:
        return repoPath.replace("/", "--")[0:Defines.XLSX_SHEET_NAME_CHAR_LIMIT]
