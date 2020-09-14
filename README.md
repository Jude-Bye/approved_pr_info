### Fetches information about pull requests that have at least one approved review and/or are merged
	--
	Obligatory arguments:
	--
	
		-repos: list of strings       			
			* list of repository paths like "repo_owner/repo_name1" "repo_owner/repo_name2" ...
			
		-api_token: string   		    
			* token or path to binary token file"
	--
	Optional arguments:
	--
	
		-pr_n: int 		 			
			* number of fethced pull_requests in query
		
		-file_mode: list of strings   
			* structure - <filemode> <optional: rest of arguments>. currently avaliable file modes:
				* single        <filename>     : writes all repo's pull requests into a single file  
				* single_sheets <filename>     : same as 'single' but splits each repo between sheets name like "repoOwner--repoName"
				* split_auto    <no arguments> : writes each repo's pull requests into a separate file, named like "repoOwner--repoName"
				
		-api_endpoint: string		 			
			* specifies github graphql api endpoint
