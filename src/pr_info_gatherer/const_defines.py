class Defines:
    """ 'Constant' variables used in this module """

    DEFAULT_API_ENDPOINT = "https://api.github.com/graphql"
    TOKEN_LENGTH = len(
        (DEFAULT_TOKEN := "0000000000000000000000000000000000000000"))
    TOKEN_FILE_ENCODING = 'utf-8'
    DEFAULT_OUTPUT_EXCEL = './pr_info.xlsx'
    DEFAULT_DATE_STR = "0001-01-01T00:00:00Z"

    DEFAULT_FILE_NAME = 'merged_approved_pull_requests'

    XLSX_DATE_TIME_FORMAT = 'hh:mm dd/mm/yy'
    XLSX_TIME_ELAPSED_FORMAT = 'd'
    XLSX_EMPTY_CELL = 'N/A'
    XLSX_COLUMN_WIDTH = 17
    XLSX_SMALL_COLUMN_WIDTH = 5
    XLSX_FILE_EXTENSION = '.xlsx'
    XLSX_SHEET_NAME_CHAR_LIMIT = 31

    PR_MERGED_STATE = 'MERGED'
    PR_APPROVED_STATE = 'APPROVED'
    PR_CLOSED_STATE = 'CLOSED'

    FILE_MODE_SINGLE = "single"
    FILE_MODE_SPLIT_AUTO = "split_auto"
