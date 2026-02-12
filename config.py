import urllib.parse

# 1. Supabase Transaction Pooler Credentials
# USER: postgres.[PROJECT-ID]
DB_USER = "postgres.bpdllbjzliujpuclsedh"
# PASS: Your encoded password
DB_PASS = "B6ATH2#Fqb8pHx?"
# HOST: Correct Pooler Address (aws-1)
DB_HOST = "aws-1-eu-central-1.pooler.supabase.com"
# PORT: Pooler standard port
DB_PORT = "6543"
DB_NAME = "postgres"

# 2. Safely encode password
encoded_pass = urllib.parse.quote_plus(DB_PASS)

# 3. Construct Connection String
DB_CONNECTION_STRING = f"postgresql://{DB_USER}:{encoded_pass}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
