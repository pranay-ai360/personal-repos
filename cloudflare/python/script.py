import CloudFlare

# Initialize the Cloudflare client using an API token
API_TOKEN = '2be1be98e6d38c0856c6a3403dad9d8ce5ad1'
cf = CloudFlare.CloudFlare(token=API_TOKEN)

# Define the zone name and the types of DNS records to delete
zone_name = 'kolossus.com.au'
record_types_to_delete = ['A', 'CNAME']

# Get the zone ID for the given domain
def get_zone_id(zone_name):
    try:
        zones = cf.zones.get(params={'name': zone_name})
        if zones:
            return zones[0]['id']
        else:
            print(f'No zone found for domain {zone_name}')
            return None
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        print(f'Error fetching zone ID: {e}')
        return None

# Get DNS records for the zone
def get_dns_records(zone_id):
    try:
        dns_records = cf.zones.dns_records.get(zone_id)
        return dns_records
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        print(f'Error fetching DNS records: {e}')
        return []

# Delete a DNS record
def delete_dns_record(zone_id, record_id):
    try:
        cf.zones.dns_records.delete(zone_id, record_id)
        print(f'Successfully deleted record ID: {record_id}')
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        print(f'Error deleting record ID {record_id}: {e}')

# Main function
def main():
    zone_id = get_zone_id(zone_name)
    if not zone_id:
        return

    dns_records = get_dns_records(zone_id)
    for record in dns_records:
        if record['type'] in record_types_to_delete:
            delete_dns_record(zone_id, record['id'])

if __name__ == '__main__':
    main()
