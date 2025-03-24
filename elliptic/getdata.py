api_key = '4c4f37b303910b88c0b1ceb9f936d207'
api_secret = 'f8b9ae80f123229127dc18f0d546dc4f'


import os
from elliptic import AML

# Retrieve your Elliptic API credentials from environment variables
# api_key = os.getenv("API_KEY")
# api_secret = os.getenv("API_SECRET")

# Initialize the AML client with your API key and secret
aml = AML(key=api_key, secret=api_secret)

def list_analyses():
    """
    Retrieves a list of analyses with default parameters.
    """
    params = {
        "expand": "customer_reference",  # Allowed values: blockchain_info, contributions, risk_rules, customer_reference
        "customer_reference": "DEFAULT",
        "sort": "created_at",
        "page": 1,
        "per_page": 20,
        "subject_type": "transaction"
    }
    response = aml.client.get("/v2/analyses", params=params)
    return response.text

def get_analysis(mc_analysis_id):
    """
    Retrieves details for a single analysis given its mc_analysis_id.
    """
    endpoint = f"/v2/analyses/{mc_analysis_id}"
    response = aml.client.get(endpoint)
    return response.text

def list_analyses_for_date(date_str):
    """
    Retrieves analyses that were analysed on a specific date.

    Constructs ISO8601 timestamps for the start and end of the day.
    For example, for date_str "2025-03-03", it will use:
      - analysed_at_after: "2025-03-03T00:00:00Z"
      - analysed_at_before: "2025-03-03T23:59:59Z"
    
    :param date_str: A string representing the date in YYYY-MM-DD format.
    :return: The API response text.
    """
    start_of_day = f"{date_str}T00:00:00Z"
    end_of_day = f"{date_str}T23:59:59Z"
    
    params = {
        "expand": "customer_reference",
        "customer_reference": "DEFAULT",
        "sort": "created_at",
        "page": 1,
        "per_page": 10,
        "subject_type": "transaction",
        "analysed_at_after": start_of_day,
        "analysed_at_before": end_of_day
    }
    response = aml.client.get("/v2/analyses", params=params)
    return response.text

# Example usage:
if __name__ == "__main__":
    # List analyses using default parameters
    print("List of analyses:")
    print(list_analyses())
    
    # List analyses for March 3, 2025
    date_to_filter = "2024-03-15"
    print(f"\nList of analyses for {date_to_filter}:")
    print(list_analyses_for_date(date_to_filter))
    
    # Retrieve a single analysis by its id (replace with a valid analysis id)
    analysis_id = "9d6c5237-12a2-4aa8-a5dc-6cf6a3eb30f6"
    #analysis_id = "7d727101-0f2a-4e23-bd2f-7d18380c029a"
    print(f"\nDetails for analysis {analysis_id}:")
    print(get_analysis(analysis_id))