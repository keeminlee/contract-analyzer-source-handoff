import logging
import boto3
import mysql.connector
import json
from datetime import datetime
logger = logging.getLogger(__name__)

# from dotenv import load_dotenv
import os

# load_dotenv()


class PageOperations:

    # def __init__(self):
    #     self.conn = self._get_connection()
    #     self.cur = self.conn.cursor(dictionary=True)

    # def _get_connection(self) -> mysql.connector.MySQLConnection:
    #     conn = mysql.connector.connect(
    #         host=os.getenv("host"),
    #         port=int(os.getenv("port", 3306)),
    #         user=os.getenv("user"),
    #         database=os.getenv("database"),
    #         password=os.getenv("password"),
    #         allow_local_infile=True,
    #         use_pure=True,
    #     )
    #     return conn
    
    def __init__(self):
        self.secret_name = "/application/aid/dev//application/aid/dev/aida-app-secret"
        self.region = "us-east-1"
        self.secrets = self._load_secrets()
        self.conn = self._get_connection()
        self.cur = self.conn.cursor(dictionary=True)

        
        
    def _load_secrets(self) -> dict:
        secret_name = self.secret_name
        region = self.region
        client = boto3.client("secretsmanager", region_name=region,verify=False)
        response = client.get_secret_value(SecretId=secret_name)
        return json.loads(response["SecretString"])
 

    def _get_connection(self) -> mysql.connector.MySQLConnection:
        conn = mysql.connector.connect(
            host = self.secrets["singlestore_host"],
            port = int(self.secrets.get("singlestore_port", 3306)),
            user = self.secrets["singlestore_user"],
            database = self.secrets["singlestore_db"],
            password = self.secrets["singlestore_pwd"],
            allow_local_infile=True,
            use_pure=True,
        )
        return conn

    def get_homepage_lobs_and_agents(self, user_id=None):
        """
        Returns hardcoded LOB -> Agents (Chat Workflows) data for the frontend.
        """
        return [
            {
                "lob_id": "lob-0",
                "lob_name": "Operations",
                "agents": [
                    {
                        "agent_id": "cwkf-67",
                        "name": "Chat with Metadata",
                        "description": "Chat with Metadata is an intelligent conversational agent designed to interact with and extract insights from syndicated loan data, commercial loan portfolios, and loan operations metadata. It enables users to ask natural-language questions and receive accurate, context-aware responses grounded in structured and unstructured financial data",
                        "owner": "Raja",
                        "link": "https://aida-dev.mufgamericas.com/login",
                        "status":"live",
                        "department":"ITA",
                        "release_date":"2026-04-30",
                    },
                    {
                        "agent_id": "cwkf-69",
                        "name": "Chat with Data",
                        "description": "This agent is a chatbot that helps you analyze data by converting natural language questions into SQL queries and analyzing their results. Starburst Agent can generate and execute SQL queries and provide metadata about available datasets.",
                        "owner": "Raja",
                        "link": "https://aida-dev.mufgamericas.com/login",
                        "status":"coming-soon",
                        "department":"ITA",
                        "release_date":"2026-04-30",
                    }
                ]
            },
            {
                "lob_id": "lob-1",
                "lob_name": "Global Corporate & Investment Banking",
                "lob_description": "Global Corporate & Investment Banking provides financial services to large corporations, institutions, \nand governments. It focuses on corporate lending, investment banking (such as mergers and acquisitions advisory),\ncapital raising, and treasury solutions. The goal is to support clients with complex financial needs on a global scale.",
                "agents": [
                    {
                        "agent_id": "cwkf-1",
                        "name": "Contract Analyzer",
                        "description": "Analyzes loan, bond, credit, and draft contracts by extracting key clauses, terms, covenants, and obligations. Highlights similarities and differences against prior or standard agreements and provides traceable, evidence-backed insights to support credit analysis and risk assessment.",
                        "owner": "Keemin",
                        "status":"coming-soon",
                        "department":"GCIB",
                        "release_date":"2026-05-15",
                    },
                    {
                        "agent_id": "cwkf-2",
                        "name": "Asset Locator",
                        "description": " Helps GCIB teams find and analyze asset information for credit decisions and portfolio management.",
                        "status":"coming-soon",
                        "department":"GCIB",
                        "release_date":"2026-04-30",
                    }
                ]
            }
        ]
    
    def get_user_profile(self, user_identifier: str):
        """
        Fetch user profile from SingleStore reference tables.

        Lookup  : user_identifier (e.g. 'N001')
        Role    : derived from AD group name — 'analyst' if 'DEV' is present
        LOB     : hardcoded to 'ITA'
        Department       : hardcoded to 'Loan Services'
        Product/Services : hardcoded to ['CLO (Commercial Loan Operations)', 'Syndicated Loans']
        """
        # --- Core user details ---
        # --- OLD CODE (commented out) ---
        # user_sql = """
        #     SELECT
        #         identifier          AS user_pk,
        #         user_identifier     AS user_id,
        #         user_name,
        #         full_name,
        #         email_identifier    AS email_id,
        #         valid_from          AS user_created_at,
        #         active_indicator    AS active
        #     FROM reference_user
        #     WHERE user_identifier = %s
        #       AND active_indicator = 1
        #     LIMIT 1
        # """
        # --- NEW CODE (3rd April schema) ---
        user_sql = """
            SELECT
                UNIQUE_IDENTIFIER       AS user_pk,
                USER_IDENTIFIER         AS user_id,
                USER_NAME               AS user_name,
                FULL_NAME               AS full_name,
                EMAIL_IDENTIFIER        AS email_id,
                EFFECTIVE_FROM_TIMESTAMP AS user_created_at,
                ACTIVE_INDICATOR        AS active
            FROM REF_USER
            WHERE USER_IDENTIFIER = %s
              AND ACTIVE_INDICATOR = 1
            LIMIT 1
        """
        self.cur.execute(user_sql, (user_identifier,))
        user_row = self.cur.fetchone()

        if not user_row:
            return None

        # Convert datetimes
        for k, v in user_row.items():
            if isinstance(v, datetime):
                user_row[k] = v.isoformat()

        # --- AD groups for the user ---
        # --- OLD CODE (commented out) ---
        # ad_sql = """
        #     SELECT
        #         ag.ad_group_identifier,
        #         ag.ad_group_name,
        #         ag.lob_name
        #     FROM reference_user_ad ua
        #     JOIN reference_ad_group ag
        #         ON ag.ad_group_identifier = ua.ad_group_identifier
        #        AND ag.active_indicator = 1
        #     WHERE ua.user_identifier = %s
        #       AND ua.active_indicator = 1
        # """
        # --- NEW CODE (3rd April schema) ---
        ad_sql = """
            SELECT
                ag.AD_GROUP_IDENTIFIER,
                ag.AD_GROUP_NAME,
                ag.LOB_NAME
            FROM REF_USER_AD ua
            JOIN REF_AD_GROUP ag
                ON ag.AD_GROUP_IDENTIFIER = ua.AD_GROUP_IDENTIFIER
               AND ag.ACTIVE_INDICATOR = 1
            WHERE ua.USER_IDENTIFIER = %s
              AND ua.ACTIVE_INDICATOR = 1
        """
        self.cur.execute(ad_sql, (user_identifier,))
        ad_rows = self.cur.fetchall()

        # --- OLD CODE (commented out) ---
        # ad_groups = [
        #     {
        #         "ad_group_id":   r["ad_group_identifier"],
        #         "ad_group_name": r["ad_group_name"],
        #         "lob_name":      r["lob_name"],
        #     }
        #     for r in ad_rows
        # ]
        # --- NEW CODE (3rd April schema) ---
        ad_groups = [
            {
                "ad_group_id":   r["AD_GROUP_IDENTIFIER"],
                "ad_group_name": r["AD_GROUP_NAME"],
                "lob_name":      r["LOB_NAME"],
            }
            for r in ad_rows
        ]

        # --- Derive role from AD group names ---
        persona = "analyst"  # default
        # --- OLD CODE (commented out) ---
        # for r in ad_rows:
        #     if "DEV" in (r["ad_group_name"] or "").upper():
        #         persona = "analyst"
        #         break
        # --- NEW CODE (3rd April schema) ---
        for r in ad_rows:
            if "DEV" in (r["AD_GROUP_NAME"] or "").upper():
                persona = "analyst"
                break

        return {
            **user_row,
            # "ad_groups":          ad_groups,
            "persona":            persona,
            "lob_id":             ad_groups[0]["lob_name"] if ad_groups else "ITA",  # default to ITA if no AD groups or lob_name is missing
            "department":         "Loan Services",
            "product_and_services": [
                "CLO (Commercial Loan Operations)",
                "Syndicated Loans",
            ],
        }
    

    def get_domains_with_products(self):
        """
        Returns JSON of Data Domains -> Data Products.

        Sources
        -------
        REF_STARBURST_DATA_DOMAIN    domain master
        REF_STARBURST_DATA_PRODUCT  product master (joined on DATA_DOMAIN_ID)

        Return format (unchanged for frontend compatibility)
        -----------------------------------------------------
        {
          "domains": [
            {
              "id": ..., "data_domain_id": ..., "name": ...,
              "description": ..., "created_at": ...,
              "data_products": [
                { "id", "data_product_id", "data_domain_id", "name",
                  "catalog", "schema_name", "description", "created_by",
                  "updated_at", "published_at", "user_data",
                  "matched_trino_def", "book_mark_count", "created_at",
                  "dp_technical_name" }
              ]
            }, ...
          ]
        }
        """
        sql = """
            SELECT
                dd.UNIQUE_IDENTIFIER            AS domain_pk,
                dd.DATA_DOMAIN_IDENTIFIER       AS data_domain_id,
                dd.DATA_DOMAIN_NAME             AS domain_name,
                dd.DATA_DOMAIN_DESCRIPTION      AS domain_description,
                dd.EFFECTIVE_FROM_TIMESTAMP     AS domain_created_at,
                dp.UNIQUE_IDENTIFIER            AS dp_pk,
                dp.DATA_PRODUCT_IDENTIFIER      AS data_product_id,
                dp.DATA_PRODUCT_NAME            AS dp_name,
                dp.DATA_PRODUCT_CATALOG_NAME    AS catalog,
                dp.DATA_PRODUCT_SCHEMA_NAME     AS schema_name,
                dp.DATA_PRODUCT_DESCRIPTION     AS dp_description,
                dp.CREATED_BY_STARBURST_SOURCE  AS created_by,
                dp.UPDATED_BY_STARBURST_SOURCE  AS updated_at,
                dp.PUBLISHED_BY_STARBURST_SOURCE AS published_at,
                dp.USER_DATA_TEXT               AS user_data,
                dp.MATCHED_TRINO_DEFINITION     AS matched_trino_def,
                dp.BOOK_MARK_COUNT_NUMBER       AS book_mark_count,
                dp.EFFECTIVE_FROM_TIMESTAMP     AS dp_created_at
            FROM REF_STARBURST_DATA_DOMAIN dd
            LEFT JOIN REF_STARBURST_DATA_PRODUCT dp
                ON dd.DATA_DOMAIN_IDENTIFIER = dp.DATA_DOMAIN_IDENTIFIER
            WHERE dd.ACTIVE_INDICATOR = 1
            ORDER BY dd.DATA_DOMAIN_IDENTIFIER, dp.DATA_PRODUCT_IDENTIFIER
        """
        self.cur.execute(sql)
        rows = self.cur.fetchall()

        domains: dict = {}
        seen_products: dict = {}  # d_id -> set of seen data_product_ids
        for row in rows:
            d_id = row["data_domain_id"]

            if d_id not in domains:
                created_at = row["domain_created_at"]
                if isinstance(created_at, datetime):
                    created_at = created_at.isoformat()

                domains[d_id] = {
                    "id": row["domain_pk"],
                    "data_domain_id": d_id,
                    "name": row["domain_name"],
                    "description": row["domain_description"],
                    "created_at": created_at,
                    "data_products": [],
                }
                seen_products[d_id] = set()

            # skip NULL product rows (LEFT JOIN with no matching product)
            if row["dp_pk"] is None:
                continue

            # skip duplicate products
            dp_id = row["data_product_id"]
            if dp_id in seen_products[d_id]:
                continue
            seen_products[d_id].add(dp_id)

            updated_at = row["updated_at"]
            if isinstance(updated_at, datetime):
                updated_at = updated_at.isoformat()

            dp_created_at = row["dp_created_at"]
            if isinstance(dp_created_at, datetime):
                dp_created_at = dp_created_at.isoformat()

            user_data = row["user_data"]
            if isinstance(user_data, str):
                try:
                    user_data = json.loads(user_data)
                except Exception:
                    pass

            domains[d_id]["data_products"].append({
                "id": row["dp_pk"],
                "data_product_id": row["data_product_id"],
                "data_domain_id": d_id,
                "name": row["dp_name"],
                "catalog": row["catalog"],
                "schema_name": row["schema_name"],
                "description": row["dp_description"],
                "created_by": row["created_by"],
                "updated_at": updated_at,
                "published_at": row["published_at"],
                "user_data": user_data,
                "matched_trino_def": row["matched_trino_def"],
                "book_mark_count": row["book_mark_count"],
                "created_at": dp_created_at,
                "dp_technical_name": row["schema_name"],  # closest equivalent
            })

        return {"domains": list(domains.values())}

    def close(self):
        self.cur.close()
        self.conn.close()


# ------------------------------
# TEST
# ------------------------------
if __name__ == "__main__":
    po = PageOperations()

    # print("----- USER PROFILE -----")
    logger.info(" ".join(map(str, ["----- USER PROFILE -----"])))
    profile = po.get_user_profile("N001")
    # print(json.dumps(profile, indent=4, default=str))
    logger.info(" ".join(map(str, [json.dumps(profile, indent=4, default=str)])))

    # print("\n----- DOMAINS WITH PRODUCTS -----")
    logger.info(" ".join(map(str, ["\n----- DOMAINS WITH PRODUCTS -----"])))
    domains_products = po.get_domains_with_products()
    # print(json.dumps(domains_products, indent=4, default=str))
    logger.info(" ".join(map(str, [json.dumps(domains_products, indent=4, default=str)])))

    po.close()
