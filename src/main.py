import traceback
from pr_info_gatherer import output_formats, UserInputError
import sys


def main() -> int:
    # print("App started!")

    try:
        output_formats.to_excel.generate_excel(tuple(sys.argv))
    except UserInputError as userError:
        print(f'Invalid input: {userError}!')
        return 1

    # print("App finished")
    return 0


if __name__ == "__main__":
    exit(main())

