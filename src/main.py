import traceback
from pr_info_gatherer import output_formats
import sys


def main() -> int:
    print("App started!")
    try:
        output_formats.to_excel.generate_excel(tuple(sys.argv))
    except Exception as error:
        print(error)
        traceback.print_exc()
        return 1

    print("App finished")
    return 0


if __name__ == "__main__":
    exit(main())

