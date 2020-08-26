#!/bin/sh
python3 -m pip install xlsxwriter
python3 ../main.py -repos "Oleh-Dmytrash/Lv-490" "graphql/express-graphql" -api_token "./token_file" -pr_n "100"
