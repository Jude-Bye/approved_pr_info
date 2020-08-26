import json
import traceback
import pr_to_excel
import sys

def main(): 
    print("App started!")
    try:
        pr_to_excel.generate_excel(sys.argv #+ [
            #'-repos', 'Oleh-Dmytrash/Lv-490', 'slicknode/graphql-query-complexity',
            #'-api_token', './token_file',
            #'-pr_n', '100' ]
        )
    except Exception as error:
        print(error)
        traceback.print_exc()
        exit(1)
    print("App finished")

if __name__ == "__main__":
    main()

