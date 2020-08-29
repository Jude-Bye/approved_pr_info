#!/bin/sh
python3 ../src/main.py\
 -repos "Oleh-Dmytrash/Lv-490" "slicknode/graphql-query-complexity" "graphql/express-graphql"\
 -api_token "./token_file"\
 -pr_n "100"\
 -file_mode "single" "test_bash.xlsx"\
 -api_endpoint "https://api.github.com/graphql"
