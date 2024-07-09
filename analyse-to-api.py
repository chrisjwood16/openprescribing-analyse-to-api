import streamlit as st
import pandas as pd
import requests
from urllib.parse import urlparse, parse_qs
import base64

# Constants
API_CALL_LIMIT = 100

def parse_url(url):
    # Parse URL
    parsed_url = urlparse(url)
    
    # Extract query components
    query_components = parse_qs(parsed_url.fragment)
    
    return query_components

def calculate_api_calls(org_ids, num_ids):
    return len(num_ids) + (len(org_ids) * len(num_ids))

def fetch_name_for_num_id(num_id):
    # Make the GET request to fetch the name for num_id
    api_url = f"https://openprescribing.net/api/1.0/bnf_code/?exact=true&format=json&q={num_id}"
    response = requests.get(api_url)
    data = response.json()
    
    if data:
        return data[0].get('name', '')
    else:
        return ''

def check_for_mixed_code_types(codes):
    has_vmp = False
    has_shorter_code = False

    for code in codes:
        if len(code) == 15:
            has_vmp = True
        elif len(code) < 15:
            has_shorter_code = True

    if has_vmp and has_shorter_code:
        return True
    else:
        return False

def extract_data(org, org_ids, num_ids):
    # Calculate number of API calls
    api_calls = calculate_api_calls(org_ids, num_ids)
    
    if api_calls > API_CALL_LIMIT:
        st.write(f"Search too complex - this would require too many API calls. ({api_calls} needed).")
        st.write("Reduce number of organisations or number of medication codes.")
    else:
        # Display org, orgIds, and numIds
        st.write(f"Select organisation type: {org}")
        st.write(f"Selected organisations: {org_ids}")
        st.write(f"Selected products: {num_ids}")
        st.write(f"Number of API calls needed: {api_calls}")

        # Fetch names for each num_id
        num_id_names = []
        total_calls = len(num_ids) + len(org_ids) * len(num_ids)
        call_count = 0
        progress_text = st.empty()
        progress_bar = st.progress(0)
        for num_id in num_ids:
            call_count += 1
            name = fetch_name_for_num_id(num_id)
            num_id_names.append({'num_id': num_id, 'name': name})
            
            # Update progress bar
            progress = int((call_count / total_calls) * 100)
            progress_bar.progress(progress)
            progress_text.text(f"Fetching data from API - API call {call_count}/{total_calls} ({progress}%)")

        num_id_df = pd.DataFrame(num_id_names)

        # List to store dataframes
        dataframes = []

        # Loop through each orgId and numId
        for org_id in org_ids:
            for num_id in num_ids:
                call_count += 1
                # Make the GET request
                api_url = f"https://openprescribing.net/api/1.0/spending_by_org/?code={num_id}&format=json&org={org_id}&org_type={org}"
                response = requests.get(api_url)
                data = response.json()

                # Load into a pandas dataframe
                df = pd.DataFrame(data)

                # Add a column with num_id
                df['num_id'] = num_id

                # Append the dataframe to the list
                dataframes.append(df)

                # Update progress bar
                progress = int((call_count / total_calls) * 100)
                progress_bar.progress(progress)
                progress_text.text(f"Fetching data from API - API call {call_count}/{total_calls} ({progress}%)")

        st.write("---")  # Add a horizontal divider
        st.write("### Results:")

        # Concatenate all dataframes
        if dataframes:
            final_df = pd.concat(dataframes, ignore_index=True)
            # Merge with num_id names
            final_df = final_df.merge(num_id_df, on='num_id', how='left')

            # Move items, quantity, and actual_cost to the last columns
            cols = list(final_df.columns)
            for col in ['items', 'quantity', 'actual_cost']:
                if col in cols:
                    cols.append(cols.pop(cols.index(col)))
            final_df = final_df[cols]

            # Display the final dataframe
            st.dataframe(final_df)
            
            # Provide download link for the dataframe
            csv = final_df.to_csv(index=False)
            b64 = base64.b64encode(csv.encode()).decode()  # B64 encode
            href = f'<a href="data:file/csv;base64,{b64}" download="result.csv" style="font-size: 20px; color: white; background-color: #4CAF50; padding: 10px 20px; text-align: center; text-decoration: none; display: inline-block; border-radius: 5px;"><i class="fas fa-download"></i> Download CSV file</a>'
            st.markdown(href, unsafe_allow_html=True)
        else:
            st.write("No data returned from API calls.")

# Streamlit app
st.title("OpenPrescribing Individual Product Extractor")

# Description
st.write(f"""
    This app takes an <a href="https://openprescribing.net/analyse/">OpenPrescribing analyse URL</a> and uses the 
    <a href="https://openprescribing.net/api/">OpenPrescribing API</a> to extract data on the specified chemical, presentation 
    or BNF section for the selected organisations. Results can be downloaded as a CSV file for further analysis. 
    Please note this tool does not currently support requests that contain a denominator and all requests must include an organisation. 
    To prevent performance issues the app is limited to {API_CALL_LIMIT} calls to the API. If your request exceeds this limit 
    you may need to split your query into separate requests.
""", unsafe_allow_html=True)

# Note for users
st.write("**Note: This tool is currently in testing, so please treat any results with caution.**")

# Input box for the URL
url = st.text_input("Paste the URL here:")

# Button to run the extraction
if st.button("Get individual product data"):
    if url:
        # Parse URL
        query_components = parse_url(url)
        
        # Extract org and check for denomIds
        org = query_components.get('org', [''])[0]

        # Extract orgIds and numIds
        org_ids = query_components.get('orgIds', [])[0].split(',') if 'orgIds' in query_components else []
        num_ids = query_components.get('numIds', [])[0].split(',') if 'numIds' in query_components else []

        error_raised = False
        # Check if orgIds is empty
        if 'denomIds' in query_components:
            error_raised = True
            st.error('Denominators not currently supported. Please remove the denominators and try again.', icon="🚨")
        if not org_ids:
            error_raised = True
            st.error('Queries without organisation(s) are not currently supported. Please select an organisation and try again.', icon="🚨")
        elif check_for_mixed_code_types(num_ids):
            st.warning('There may be a mixture of types of codes used in your query (e.g. VMP, VTM), this may give unexpected results e.g. double counting if there is overlap. Please check your query carefully.', icon="⚠️")
        if not error_raised:
            extract_data(org, org_ids, num_ids) 